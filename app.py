from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from functools import wraps
from io import BytesIO
import os
import re
import secrets
import sqlite3
import sys
import time
import math
import smtplib
import ssl
import hashlib
from urllib.parse import urlsplit
from email.message import EmailMessage
from contextlib import contextmanager
import urllib.request
import xml.etree.ElementTree as ET
from zoneinfo import ZoneInfo

import qrcode
from qrcode.image.svg import SvgPathFillImage
from flask import (Flask, abort, flash, render_template, request, redirect,
                   jsonify, send_file, session, url_for)
from werkzeug.security import generate_password_hash, check_password_hash

BASE = os.path.dirname(os.path.abspath(__file__))
DB = os.environ.get("PARKGO_DB", os.path.join(BASE, "parking.db"))
STARTED = time.time()

# --- настройки -------------------------------------------------------------
# Регистрация только по университетской почте. Пустой кортеж () = любая почта.
ALLOWED_DOMAINS = ("astanait.edu.kz",)
# Секрет датчиков: симулятор шлёт его в заголовке X-Sensor-Token.
SENSOR_TOKEN = os.environ.get("PARKGO_SENSOR_TOKEN", "parkgo-sensor-demo")

# Наземные парковки: точки внутри контуров 2ГИС, проверены по снимкам местности.
# source_id: https://2gis.kz/astana/geo/{source_id}; геометрия в tests/fixtures/parking-areas.json.
# Ключи сохраняются для совместимости с существующими местами и бронями.
LOTS = {
    "Campus North":    {"xy": [71.420883, 51.092044], "source_id": "70030076312309318", "label": {"ru": "EXPO · северная парковка", "en": "EXPO · north parking"}, "price": 500, "spots": ["A01", "A02"]},
    "Campus South":    {"xy": [71.421644, 51.089128], "source_id": "70030076143497874", "label": {"ru": "EXPO · южная парковка", "en": "EXPO · south parking"}, "price": 400, "spots": ["B01", "B02"]},
    "Main Building":   {"xy": [71.420460, 51.090950], "source_id": "70030076137949766", "label": {"ru": "Парковка у AITU", "en": "Parking near AITU"}, "price": 600, "spots": ["C01"]},
    "EXPO East":       {"xy": [71.422401, 51.091081], "source_id": "70030076137949766", "label": {"ru": "EXPO · восточная парковка", "en": "EXPO · east parking"}, "price": 450, "spots": ["E01", "E02", "E03", "E04"]},
    "Mega Silk Way":   {"xy": [71.411137, 51.087372], "source_id": "70030076132619133", "label": {"ru": "MEGA Silk Way", "en": "MEGA Silk Way"}, "price": 600, "spots": ["M01", "M02", "M03", "M04"]},
    "AITU Gate":       {"xy": [71.421279, 51.090759], "source_id": "70030077039973779", "label": {"ru": "Парковка напротив AITU", "en": "Parking opposite AITU"}, "price": 350, "spots": ["G01", "G02", "G03", "G04"]},
    "Botanical Garden": {"xy": [71.417435, 51.101900], "source_id": "70030076199165565", "label": {"ru": "Ботанический сад · парковка 1370", "en": "Botanical garden · parking 1370"}, "price": 300, "spots": ["T01", "T02", "T03", "T04"]},
}

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PROMO_CODE_RE = re.compile(r"[A-Z0-9][A-Z0-9-]{2,31}")
PROMO_LIMITS = {"percent": 100, "fixed": 100000, "minutes": 240}
EXPO_CHARGING = "https://edrive.kz/maps/?city=1&local=0"
FAILS = {}  # защита входа от подбора пароля: {ключ: [время неудачных попыток]}
AUTH_RU = {
    "Enter a valid email.": "Введите корректный адрес почты.",
    "Use your university email: @astanait.edu.kz": "Используйте университетскую почту @astanait.edu.kz.",
    "Password must have at least 8 characters.": "Пароль должен содержать минимум 8 символов.",
    "This email is already registered.": "Эта почта уже зарегистрирована. Войдите в аккаунт.",
    "Too many attempts. Try again in 5 minutes.": "Слишком много попыток. Попробуйте через 5 минут.",
    "Wrong email or password.": "Неверная почта или пароль.",
    "Email verification is not configured. Please contact the administrator.": "Отправка писем не настроена. Обратитесь к администратору ParkGo.",
    "Could not send the verification email. Please try again or contact the administrator.": "Не удалось отправить письмо. Попробуйте ещё раз или обратитесь к администратору ParkGo.",
    "Check your email for a verification link.": "Письмо отправлено. Откройте ссылку для подтверждения почты; проверьте также папку «Спам».",
    "Verification link is invalid or expired.": "Ссылка недействительна или срок её действия истёк. Пройдите регистрацию ещё раз.",
}


def get_secret():
    path = os.path.join(BASE, "secret.key")
    if not os.path.exists(path):
        with open(path, "w") as f:
            f.write(secrets.token_hex(32))
    with open(path) as f:
        return f.read().strip()


app = Flask(__name__)
app.secret_key = get_secret()
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax")


@contextmanager
def database():
    con = sqlite3.connect(DB)
    try:
        with con:
            yield con
    finally:
        con.close()


def csrf_token():
    return session.setdefault("csrf_token", secrets.token_urlsafe(32))

app.jinja_env.globals["csrf_token"] = csrf_token

@app.before_request
def protect_csrf():
    if request.method in ("POST", "PUT", "PATCH", "DELETE") and request.path != "/api/sensor":
        supplied = request.headers.get("X-CSRF-Token") or request.form.get("csrf_token", "")
        expected = session.get("csrf_token", "")
        if not expected or not secrets.compare_digest(expected.encode(), supplied.encode()):
            return "Invalid CSRF token.", 403

# --- база данных -----------------------------------------------------------
def init_db():
    with database() as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS parking_spots (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                location TEXT NOT NULL,
                price REAL NOT NULL,
                status TEXT NOT NULL DEFAULT 'Available'
            )""")
        con.execute("""
            CREATE TABLE IF NOT EXISTS reservations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                spot_id INTEGER NOT NULL,
                customer_name TEXT NOT NULL,
                car_number TEXT NOT NULL,
                FOREIGN KEY (spot_id) REFERENCES parking_spots(id)
            )""")
        con.execute("""
            CREATE TABLE IF NOT EXISTS support_reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category TEXT NOT NULL,
                message TEXT NOT NULL,
                contact TEXT,
                status TEXT NOT NULL DEFAULT 'open',
                created_at TEXT NOT NULL
            )""")
        con.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL UNIQUE,
                full_name TEXT,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'user' CHECK (role IN ('user', 'admin')),
                created_at TEXT NOT NULL
            )""")
        con.execute("""
            CREATE TABLE IF NOT EXISTS promo_codes (
                code TEXT PRIMARY KEY,
                kind TEXT NOT NULL CHECK (kind IN ('percent', 'fixed', 'minutes')),
                value INTEGER NOT NULL CHECK (value > 0),
                expires_at INTEGER NOT NULL,
                max_uses INTEGER NOT NULL CHECK (max_uses > 0),
                uses INTEGER NOT NULL DEFAULT 0 CHECK (uses BETWEEN 0 AND max_uses)
            )""")
        con.execute("CREATE TABLE IF NOT EXISTS ev_charging_lots (location TEXT PRIMARY KEY)")
        con.execute("""CREATE TABLE IF NOT EXISTS pending_registrations (
            token_hash TEXT PRIMARY KEY, email TEXT NOT NULL, full_name TEXT,
            password_hash TEXT NOT NULL, next_path TEXT NOT NULL, expires_at INTEGER NOT NULL
        )""")
        con.execute("BEGIN IMMEDIATE")
        columns = {row[1] for row in con.execute("PRAGMA table_info(reservations)")}
        for column in ("created_at TEXT", "user_id INTEGER", "expires_at INTEGER", "request_key TEXT",
                       "promo_code TEXT", "promo_kind TEXT", "promo_value INTEGER", "promo_total INTEGER"):
            if column.split()[0] not in columns:
                con.execute(f"ALTER TABLE reservations ADD COLUMN {column}")

        con.execute("CREATE UNIQUE INDEX IF NOT EXISTS reservation_request ON reservations(user_id, request_key)")

        # добавляем парковки, которых ещё нет (старые данные не трогаем)
        for lot, d in LOTS.items():
            exists = con.execute(
                "SELECT 1 FROM parking_spots WHERE location = ?", (lot,)
            ).fetchone()
            if not exists:
                con.executemany(
                    "INSERT INTO parking_spots (name, location, price, status) VALUES (?, ?, ?, 'Available')",
                    [(n, lot, d["price"]) for n in d["spots"]],
                )

        # первый администратор (пароль показывается один раз в консоли)
        has_admin = con.execute("SELECT 1 FROM users WHERE role = 'admin'").fetchone()
        if not has_admin:
            pwd = secrets.token_urlsafe(9)
            con.execute(
                "INSERT INTO users (email, full_name, password_hash, role, created_at) VALUES (?, ?, ?, 'admin', ?)",
                ("admin@astanait.edu.kz", "Administrator", generate_password_hash(pwd), now()),
            )
            print("\n=== ParkGo: создан администратор ===")
            print("    email:  admin@astanait.edu.kz")
            print(f"    пароль: {pwd}")
            print("    (показывается один раз; сменить: python app.py make-admin EMAIL ПАРОЛЬ)\n")


def make_admin(email, password):
    email = email.strip().lower()
    with database() as con:
        row = con.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
        h = generate_password_hash(password)
        if row:
            con.execute("UPDATE users SET password_hash = ?, role = 'admin' WHERE id = ?", (h, row[0]))
        else:
            con.execute(
                "INSERT INTO users (email, full_name, password_hash, role, created_at) VALUES (?, 'Administrator', ?, 'admin', ?)",
                (email, h, now()),
            )


def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def ago(ts):
    if not ts:
        return ""
    try:
        sec = (datetime.now() - datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")).total_seconds()
    except ValueError:
        return ""
    if sec < 60:
        return "just now"
    if sec < 3600:
        return f"{int(sec // 60)} min ago"
    if sec < 86400:
        return f"{int(sec // 3600)} h ago"
    return f"{int(sec // 86400)} d ago"


# --- вход и права ----------------------------------------------------------
def current_user():
    uid = session.get("uid")
    if not uid:
        return None
    with database() as con:
        con.row_factory = sqlite3.Row
        return con.execute(
            "SELECT id, email, full_name, role FROM users WHERE id = ?", (uid,)
        ).fetchone()


def admin_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        user = current_user()
        if user is None:
            if request.method == "GET":
                return redirect(url_for("login", next=request.path))
            return "Please log in.", 401
        if user["role"] != "admin":
            return "Administrators only.", 403
        return view(*args, **kwargs)
    return wrapper


def safe_next(value):
    return value if (value and value.startswith("/") and not value.startswith("//")
                     and "\\" not in value and not any(ord(c) < 32 for c in value)) else "/"


def too_many(key):
    t = time.time()
    FAILS[key] = [x for x in FAILS.get(key, []) if t - x < 300]
    return len(FAILS[key]) >= 5


def login_page(error=None, mode="login", status=200, success=False):
    return render_template("login.html", error=error, mode=mode,
                           error_ru=AUTH_RU.get(error, error),
                           success=success, demo=registration_mode() == "demo",
                           email=request.form.get("email", "")[:254],
                           full_name=request.form.get("full_name", "")[:80],
                           next=safe_next(request.values.get("next"))), status


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        return login_page(mode=request.args.get("mode", "login"))
    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")
    key = f"{email}|{request.remote_addr}"
    if too_many(key):
        return login_page("Too many attempts. Try again in 5 minutes.", status=429)
    with database() as con:
        con.row_factory = sqlite3.Row
        row = con.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
    if row and check_password_hash(row["password_hash"], password):
        FAILS.pop(key, None)
        session.clear()
        session["uid"] = row["id"]
        return redirect(safe_next(request.form.get("next")))
    FAILS.setdefault(key, []).append(time.time())
    return login_page("Wrong email or password.", status=401)


@app.route("/register", methods=["POST"])
def register():
    email = request.form.get("email", "").strip().lower()
    name = request.form.get("full_name", "").strip()[:80]
    password = request.form.get("password", "")
    if len(email) > 254 or not EMAIL_RE.fullmatch(email):
        return login_page("Enter a valid email.", "register", 400)
    if ALLOWED_DOMAINS and email.split("@")[1] not in ALLOWED_DOMAINS:
        return login_page("Use your university email: @" + ALLOWED_DOMAINS[0], "register", 400)
    if len(password) < 8:
        return login_page("Password must have at least 8 characters.", "register", 400)
    with database() as con:
        if con.execute("SELECT 1 FROM users WHERE email = ?", (email,)).fetchone():
            return login_page("This email is already registered.", "register", 409)
    destination = safe_next(request.form.get("next"))
    password_hash = generate_password_hash(password)
    if registration_mode() == "demo":
        try:
            with database() as con:
                cur = con.execute("INSERT INTO users (email, full_name, password_hash, created_at) VALUES (?, ?, ?, ?)",
                                  (email, name, password_hash, now()))
        except sqlite3.IntegrityError:
            return login_page("This email is already registered.", "register", 409)
        session.clear()
        session["uid"] = cur.lastrowid
        return redirect(destination)
    try:
        mail_settings()
    except ValueError as exc:
        app.logger.error("Registration mail configuration: %s", exc)
        return login_page("Email verification is not configured. Please contact the administrator.", "register", 503)
    token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    link = verification_link(token)
    with database() as con:
        con.execute("DELETE FROM pending_registrations WHERE expires_at <= ?", (int(time.time()),))
        con.execute("INSERT INTO pending_registrations VALUES (?, ?, ?, ?, ?, ?)",
                    (token_hash, email, name, password_hash, destination, int(time.time()) + 3600))
    try:
        send_verification_email(email, link)
    except (OSError, smtplib.SMTPException, ValueError):
        with database() as con:
            con.execute("DELETE FROM pending_registrations WHERE token_hash = ?", (token_hash,))
        # Do not log credentials, message bodies or confirmation links.
        app.logger.error("Registration email delivery failed. Check SMTP connection, credentials and TLS mode.")
        return login_page("Could not send the verification email. Please try again or contact the administrator.", "register", 503)
    return login_page("Check your email for a verification link.", "login", success=True)


def registration_mode():
    return os.environ.get("PARKGO_REGISTRATION_MODE", "verified").strip().lower()


def mail_settings():
    if registration_mode() not in ("verified", "demo"):
        raise ValueError("PARKGO_REGISTRATION_MODE must be verified or demo")
    host = os.environ.get("PARKGO_SMTP_HOST", "").strip()
    sender = os.environ.get("PARKGO_SMTP_FROM", "").strip()
    if not host or not sender:
        raise ValueError("Set PARKGO_SMTP_HOST and PARKGO_SMTP_FROM in the server environment")
    if not EMAIL_RE.fullmatch(sender):
        raise ValueError("PARKGO_SMTP_FROM must be an email address")
    port = int(os.environ.get("PARKGO_SMTP_PORT", "587"))
    mode = os.environ.get("PARKGO_SMTP_SECURITY", "ssl" if port == 465 else "starttls").lower()
    if not 1 <= port <= 65535 or mode not in ("ssl", "starttls"):
        raise ValueError("Use SMTP port 1–65535 and PARKGO_SMTP_SECURITY=ssl or starttls")
    public_url = os.environ.get("PARKGO_PUBLIC_URL", "").rstrip("/")
    parsed = urlsplit(public_url)
    if public_url and (parsed.scheme not in ("http", "https") or not parsed.hostname
                       or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path):
        raise ValueError("PARKGO_PUBLIC_URL must be the public http(s) origin without a path")
    return host, sender, port, mode


def verification_link(token):
    base = os.environ.get("PARKGO_PUBLIC_URL", "").rstrip("/")
    return base + url_for("verify_email", token=token) if base else url_for("verify_email", token=token, _external=True)


def send_verification_email(email, link):
    host, sender, port, mode = mail_settings()
    msg = EmailMessage()
    msg["Subject"] = "ParkGo: verify your email"
    msg["From"], msg["To"] = sender, email
    msg.set_content("Verify your email using this link (valid for one hour):\n" + link)
    context = ssl.create_default_context()
    connection = (smtplib.SMTP_SSL(host, port, timeout=10, context=context) if mode == "ssl"
                  else smtplib.SMTP(host, port, timeout=10))
    with connection as smtp:
        if mode == "starttls":
            smtp.starttls(context=context)
        if os.environ.get("PARKGO_SMTP_USER"):
            smtp.login(os.environ["PARKGO_SMTP_USER"], os.environ.get("PARKGO_SMTP_PASSWORD", ""))
        smtp.send_message(msg)


@app.route("/verify-email/<token>")
def verify_email(token):
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    try:
        with database() as con:
            con.execute("BEGIN IMMEDIATE")
            data = con.execute("SELECT email, full_name, password_hash, next_path FROM pending_registrations WHERE token_hash = ? AND expires_at > ?",
                               (token_hash, int(time.time()))).fetchone()
            if data is None:
                return login_page("Verification link is invalid or expired.", "register", 400)
            cur = con.execute("INSERT INTO users (email, full_name, password_hash, created_at) VALUES (?, ?, ?, ?)",
                              (*data[:3], now()))
            con.execute("DELETE FROM pending_registrations WHERE email = ?", (data[0],))
    except sqlite3.IntegrityError:
        return login_page("This email is already registered.", "login", 409)
    session.clear()
    session["uid"] = cur.lastrowid
    return redirect(safe_next(data[3]))


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")


# --- сайт и бронирование ---------------------------------------------------
def spots_json(con):
    con.row_factory = sqlite3.Row
    rows = con.execute("""SELECT p.*, (ev.location IS NOT NULL) AS ev_charging
        FROM parking_spots p LEFT JOIN ev_charging_lots ev USING (location) ORDER BY p.id""").fetchall()
    return [{"id": r["id"], "name": r["name"], "loc": r["location"],
             "price": r["price"], "status": r["status"], "free": r["status"] == "Available",
             "ev_charging": bool(r["ev_charging"]),
             "ev_nearby": r["location"] == "EXPO East"} for r in rows]


@app.route("/")
def home():
    with database() as con:
        spots = spots_json(con)
    return render_template("index.html", spots=spots,
                           lots={k: v["xy"] for k, v in LOTS.items()},
                           lot_labels={k: v["label"] for k, v in LOTS.items()},
                           expo_charging=EXPO_CHARGING, user=current_user(), bookings=my_bookings())


def my_bookings():
    user = current_user()
    if user is None:
        return []
    with database() as con:
        con.row_factory = sqlite3.Row
        rows = con.execute("""SELECT r.*, p.name AS spot, p.location, p.price
            FROM reservations r JOIN parking_spots p ON p.id = r.spot_id
            WHERE r.user_id = ? ORDER BY r.id DESC""", (user["id"],)).fetchall()
    return [dict(r) for r in rows]


@app.before_request
def expire_bookings():
    # Old bookings have no known expiry; keep them until explicitly cancelled.
    with database() as con:
        con.execute("BEGIN IMMEDIATE")
        expired = con.execute("SELECT id, spot_id FROM reservations WHERE expires_at <= ?",
                              (int(time.time()),)).fetchall()
        for rid, spot_id in expired:
            con.execute("DELETE FROM reservations WHERE id = ?", (rid,))
            con.execute("""UPDATE parking_spots SET status = 'Available'
                WHERE id = ? AND status = 'Reserved'
                AND NOT EXISTS (SELECT 1 FROM reservations WHERE spot_id = ?)""",
                        (spot_id, spot_id))


@app.route("/api/reservations")
def api_reservations():
    if current_user() is None:
        return jsonify(error="Please log in."), 401
    response = jsonify(my_bookings())
    response.headers["Cache-Control"] = "no-store"
    return response


@app.route("/reservations/<int:reservation_id>/qr.svg")
def reservation_qr(reservation_id):
    user = current_user()
    if user is None:
        abort(401)
    with database() as con:
        booking = con.execute("SELECT 1 FROM reservations WHERE id = ? AND user_id = ?",
                              (reservation_id, user["id"])).fetchone()
    if booking is None:
        abort(404)
    image = qrcode.make(f"ParkGo booking #{reservation_id}", image_factory=SvgPathFillImage)
    data = BytesIO()
    image.save(data)
    data.seek(0)
    response = send_file(data, mimetype="image/svg+xml")
    response.headers["Cache-Control"] = "private, no-store"
    return response


def active_promo(con, code, timestamp):
    if not PROMO_CODE_RE.fullmatch(code):
        return None
    return con.execute("""SELECT code, kind, value FROM promo_codes
        WHERE code = ? AND expires_at > ? AND uses < max_uses""", (code, timestamp)).fetchone()


@app.route("/api/promo/preview", methods=["POST"])
def promo_preview():
    if current_user() is None:
        return jsonify(error="login"), 401
    code = request.form.get("code", "").strip().upper()
    with database() as con:
        promo = active_promo(con, code, int(time.time()))
    if promo is None:
        return jsonify(error="promo_unavailable"), 404
    return jsonify(code=promo[0], kind=promo[1], value=promo[2])


def promo_total(price, minutes, kind, value):
    # Store money as integer tiyn. Bonus minutes extend the reservation for free.
    hourly = int((Decimal(str(price)) * 100).to_integral_value(rounding=ROUND_HALF_UP))
    total = (hourly * minutes + 30) // 60
    if kind == "percent":
        return total - (total * value + 50) // 100
    if kind == "fixed":
        return max(0, total - value * 100)
    return total


FX_CACHE = {"checked": 0, "value": None}


@app.route("/api/exchange-rate")
def exchange_rate():
    # Dated official NBK feed. Never substitute an invented exchange rate.
    today = datetime.now(ZoneInfo("Asia/Almaty")).strftime("%d.%m.%Y")
    if time.time() - FX_CACHE["checked"] > 300 or FX_CACHE.get("date") != today:
        FX_CACHE.update(checked=time.time(), value=None, date=today)
        try:
            url = "https://nationalbank.kz/rss/get_rates.cfm?fdate=" + today
            with urllib.request.urlopen(url, timeout=4) as response:
                root = ET.fromstring(response.read(250000))
            for item in root.findall(".//item"):
                if item.findtext("title", "").strip() == "USD":
                    rate = float(item.findtext("description", "0").replace(",", "."))
                    units = float(item.findtext("quant", "1"))
                    rate /= units
                    if not math.isfinite(rate) or rate <= 0:
                        raise ValueError("Invalid rate")
                    FX_CACHE["value"] = dict(kzt_per_usd=rate, date=today, source=url)
                    break
        except (OSError, ValueError, ET.ParseError, ZeroDivisionError):
            pass
    if FX_CACHE["value"] is None:
        return jsonify(error="USD estimate unavailable"), 503
    return jsonify(FX_CACHE["value"])


@app.route("/api/spots")
def api_spots():
    """Страница опрашивает этот адрес каждые несколько секунд (обновление в реальном времени)."""
    with database() as con:
        resp = jsonify(spots_json(con))
    resp.headers["Cache-Control"] = "no-store"
    return resp


@app.route("/book/<int:spot_id>", methods=["POST"])
def book(spot_id):
    user = current_user()
    if user is None:
        return "Please log in to book a spot.", 401

    name = request.form.get("customer_name", "").strip()[:80]
    car = request.form.get("car_number", "").strip()[:20]
    if not name or not car:
        return "Please enter your name and car number.", 400

    try:
        minutes = int(request.form.get("minutes", "30"))
    except ValueError:
        return "Invalid duration.", 400
    if minutes not in (15, 30, 60, 120):
        return "Invalid duration.", 400
    request_key = request.form.get("request_key", "").strip()[:100] or None
    code = request.form.get("promo_code", "").strip().upper()

    with database() as con:
        con.execute("PRAGMA foreign_keys = ON")
        con.execute("BEGIN IMMEDIATE")
        if request_key:
            previous = con.execute("SELECT id FROM reservations WHERE user_id = ? AND request_key = ?",
                                   (user["id"], request_key)).fetchone()
            if previous:
                return jsonify(ok=True, reservation_id=previous[0])
        spot = con.execute(
            "SELECT status, price FROM parking_spots WHERE id = ?", (spot_id,)
        ).fetchone()
        if spot is None:
            return "Parking spot not found.", 404
        if spot[0] != "Available":
            return "This parking spot is no longer available.", 409

        timestamp = int(time.time())
        kind = value = total = None
        if code:
            promo = active_promo(con, code, timestamp)
            if promo is None:
                return jsonify(error="promo_unavailable"), 422
            _, kind, value = promo
            total = promo_total(spot[1], minutes, kind, value)
            con.execute("UPDATE promo_codes SET uses = uses + 1 WHERE code = ?", (code,))
        expires_at = timestamp + (minutes + (value if kind == "minutes" else 0)) * 60
        cur = con.execute(
            """INSERT INTO reservations (spot_id, customer_name, car_number, created_at, user_id,
                   expires_at, request_key, promo_code, promo_kind, promo_value, promo_total)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (spot_id, name, car, now(), user["id"], expires_at, request_key, code or None, kind, value, total),
        )
        reservation_id = cur.lastrowid
        con.execute("UPDATE parking_spots SET status = 'Reserved' WHERE id = ?", (spot_id,))

    if request.headers.get("X-Requested-With") == "fetch":
        return jsonify(ok=True, reservation_id=reservation_id)
    return redirect("/")


@app.route("/cancel/<int:reservation_id>", methods=["POST"])
def cancel(reservation_id):
    user = current_user()
    if user is None:
        return "Please log in.", 401
    with database() as con:
        con.execute("BEGIN IMMEDIATE")
        row = con.execute(
            "SELECT spot_id, user_id FROM reservations WHERE id = ?", (reservation_id,)
        ).fetchone()
        if row is None:
            return "Reservation not found.", 404
        if user["role"] != "admin" and row[1] != user["id"]:
            return "You can cancel only your own booking.", 403
        con.execute("DELETE FROM reservations WHERE id = ?", (reservation_id,))
        con.execute("UPDATE parking_spots SET status = 'Available' WHERE id = ? AND NOT EXISTS (SELECT 1 FROM reservations WHERE spot_id = ?)", (row[0], row[0]))
    return jsonify(ok=True)


@app.route("/support", methods=["POST"])
def support():
    category = request.form.get("category", "chat").strip()[:30] or "chat"
    message = request.form.get("message", "").strip()
    contact = request.form.get("contact", "").strip()[:80]
    if not message:
        return "Please describe your problem.", 400
    with database() as con:
        cur = con.execute(
            "INSERT INTO support_reports (category, message, contact, created_at) VALUES (?, ?, ?, ?)",
            (category, message[:1000], contact, now()),
        )
    return jsonify(ok=True, id=cur.lastrowid)


# --- датчики (симулятор sensor_simulator.py шлёт сюда данные) ---------------
@app.route("/api/sensor", methods=["POST"])
def sensor():
    if not secrets.compare_digest(request.headers.get("X-Sensor-Token", "").encode(), SENSOR_TOKEN.encode()):
        return jsonify(ok=False, error="bad token"), 401
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify(ok=False, error="JSON object required"), 400
    status = data.get("status")
    try:
        spot_id = int(data.get("spot_id"))
    except (TypeError, ValueError):
        return jsonify(ok=False, error="bad spot_id"), 400
    if status not in ("Occupied", "Available"):
        return jsonify(ok=False, error="status must be Occupied or Available"), 400
    with database() as con:
        con.execute("BEGIN IMMEDIATE")
        row = con.execute("SELECT status FROM parking_spots WHERE id = ?", (spot_id,)).fetchone()
        if row is None:
            return jsonify(ok=False, error="spot not found"), 404
        if row[0] == "Reserved":  # забронированное место датчик не меняет
            return jsonify(ok=False, error="spot is reserved"), 409
        con.execute("UPDATE parking_spots SET status = ? WHERE id = ?", (status, spot_id))
    return jsonify(ok=True)


# --- админка ---------------------------------------------------------------
@app.route("/admin/promos", methods=["POST"])
@admin_required
def create_promo():
    code = request.form.get("code", "").strip().upper()
    kind = request.form.get("kind", "")
    try:
        value, duration, max_uses = (int(request.form.get(field, ""))
                                     for field in ("value", "duration_hours", "max_uses"))
    except ValueError:
        value = duration = max_uses = 0
    if (not PROMO_CODE_RE.fullmatch(code) or not 1 <= value <= PROMO_LIMITS.get(kind, 0)
            or not 1 <= duration <= 8760 or not 1 <= max_uses <= 100000):
        flash("Check the promo code, benefit, validity and activation limit.", "error")
    else:
        with database() as con:
            result = con.execute("""INSERT INTO promo_codes (code, kind, value, expires_at, max_uses)
                VALUES (?, ?, ?, ?, ?) ON CONFLICT(code) DO NOTHING""",
                                 (code, kind, value, int(time.time()) + duration * 3600, max_uses))
        if result.rowcount:
            flash(f"Promo code {code} created.", "success")
        else:
            flash("This promo code already exists.", "error")
    return redirect(url_for("admin", pane="promos"), code=303)


@app.route("/admin/charging", methods=["POST"])
@admin_required
def update_charging():
    lot = request.form.get("lot", "")
    enabled = request.form.get("enabled")
    if lot not in LOTS or enabled not in ("0", "1"):
        abort(400)
    with database() as con:
        if enabled == "1":
            con.execute("INSERT OR IGNORE INTO ev_charging_lots (location) VALUES (?)", (lot,))
        else:
            con.execute("DELETE FROM ev_charging_lots WHERE location = ?", (lot,))
    flash("Charging marker updated.", "success")
    return redirect(url_for("admin", pane="park"), code=303)


@app.route("/admin/report/<int:report_id>/resolve", methods=["POST"])
@admin_required
def resolve_report(report_id):
    with database() as con:
        result = con.execute("UPDATE support_reports SET status = 'resolved' WHERE id = ?", (report_id,))
        if not result.rowcount:
            abort(404)
    return jsonify(ok=True)


@app.route("/admin")
@admin_required
def admin():
    with database() as con:
        con.row_factory = sqlite3.Row
        spots = con.execute("""
            SELECT p.*, r.id AS rid, r.customer_name, r.car_number
            FROM parking_spots p
            LEFT JOIN reservations r
              ON r.id = (SELECT MAX(id) FROM reservations WHERE spot_id = p.id)
            ORDER BY p.id
        """).fetchall()
        reports = con.execute(
            "SELECT * FROM support_reports ORDER BY (status = 'open') DESC, id DESC"
        ).fetchall()
        bookings = con.execute("""
            SELECT r.id, r.customer_name, r.created_at, p.name AS spot
            FROM reservations r JOIN parking_spots p ON p.id = r.spot_id
            ORDER BY r.id DESC LIMIT 8
        """).fetchall()
        db_ok = con.execute("SELECT 1").fetchone() is not None
        promos = con.execute("SELECT * FROM promo_codes ORDER BY rowid DESC").fetchall()
        charging_lots = {row[0] for row in con.execute("SELECT location FROM ev_charging_lots")}

    free_by_loc = {}
    for s in spots:
        free_by_loc.setdefault(s["location"], 0)
        if s["status"] == "Available":
            free_by_loc[s["location"]] += 1

    up = int(time.time() - STARTED)
    uptime = f"{up // 3600}h {up % 3600 // 60}m" if up >= 3600 else f"{up // 60}m {up % 60}s"

    activity = [
        {"title": "New booking", "text": f"Spot {b['spot']} · {b['customer_name']}",
         "ts": b["created_at"], "ago": ago(b["created_at"])} for b in bookings
    ] + [
        {"title": "Support message" + (" resolved" if r["status"] == "resolved" else ""),
         "text": f"{r['category']}: {r['message'][:60]}",
         "ts": r["created_at"], "ago": ago(r["created_at"])} for r in reports
    ]
    activity.sort(key=lambda a: a["ts"] or "", reverse=True)

    stats = {
        "locations": len(free_by_loc),
        "open_reports": sum(1 for r in reports if r["status"] == "open"),
        "unavailable": sum(1 for n in free_by_loc.values() if n == 0),
        "uptime": uptime,
    }
    return render_template("admin.html", stats=stats, spots=spots, reports=reports,
                           activity=activity[:10], db_ok=db_ok, promos=promos, lots=LOTS,
                           charging_lots=charging_lots, timestamp=int(time.time()))


init_db()

if __name__ == "__main__":
    if len(sys.argv) == 2 and sys.argv[1] == "check-mail":
        if registration_mode() == "demo":
            print("Demo registration: email ownership is NOT verified; SMTP is not used.")
        else:
            try:
                _, _, port, security = mail_settings()
            except ValueError as exc:
                print("Mail configuration error:", exc)
                sys.exit(1)
            print(f"Mail configuration valid: port {port}, {security}. Delivery has not been tested.")
        sys.exit(0)
    if len(sys.argv) == 4 and sys.argv[1] == "make-admin":
        make_admin(sys.argv[2], sys.argv[3])
        print("Администратор сохранён:", sys.argv[2].lower())
        sys.exit(0)
    app.run(host=os.environ.get("PARKGO_HOST", "127.0.0.1"),
            port=int(os.environ.get("PARKGO_PORT", "5050")), debug=False)

