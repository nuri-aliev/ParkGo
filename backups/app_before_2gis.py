from flask import Flask, render_template, request, redirect, jsonify
import sqlite3

app = Flask(__name__)
DB = "parking.db"


def init_db():
    with sqlite3.connect(DB) as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS parking_spots (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                location TEXT NOT NULL,
                price REAL NOT NULL,
                status TEXT NOT NULL DEFAULT 'Available'
            )
        """)

        con.execute("""
            CREATE TABLE IF NOT EXISTS reservations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                spot_id INTEGER NOT NULL,
                customer_name TEXT NOT NULL,
                car_number TEXT NOT NULL,
                FOREIGN KEY (spot_id) REFERENCES parking_spots(id)
            )
        """)

        count = con.execute(
            "SELECT COUNT(*) FROM parking_spots"
        ).fetchone()[0]

        if count == 0:
            spots = [
                ("A01", "Campus North", 500, "Available"),
                ("A02", "Campus North", 500, "Available"),
                ("B01", "Campus South", 400, "Available"),
                ("B02", "Campus South", 400, "Available"),
                ("C01", "Main Building", 600, "Available"),
            ]
            con.executemany(
                """INSERT INTO parking_spots
                   (name, location, price, status)
                   VALUES (?, ?, ?, ?)""",
                spots,
            )


@app.route("/")
def home():
    with sqlite3.connect(DB) as con:
        con.row_factory = sqlite3.Row
        spots = con.execute(
            "SELECT * FROM parking_spots ORDER BY id"
        ).fetchall()

    return render_template("index.html", spots=spots)


@app.route("/book/<int:spot_id>", methods=["POST"])
def book(spot_id):
    name = request.form.get("customer_name", "").strip()
    car = request.form.get("car_number", "").strip()

    if not name or not car:
        return "Please enter your name and car number.", 400

    with sqlite3.connect(DB) as con:
        con.execute("PRAGMA foreign_keys = ON")
        spot = con.execute(
            "SELECT status FROM parking_spots WHERE id = ?",
            (spot_id,),
        ).fetchone()

        if spot is None:
            return "Parking spot not found.", 404

        if spot[0] != "Available":
            return "This parking spot is already booked.", 409

        cur = con.execute(
            """INSERT INTO reservations
               (spot_id, customer_name, car_number)
               VALUES (?, ?, ?)""",
            (spot_id, name, car),
        )
        reservation_id = cur.lastrowid
        con.execute(
            "UPDATE parking_spots SET status = 'Reserved' WHERE id = ?",
            (spot_id,),
        )

    if request.headers.get("X-Requested-With") == "fetch":
        return jsonify(ok=True, reservation_id=reservation_id)
    return redirect("/")


@app.route("/cancel/<int:reservation_id>", methods=["POST"])
def cancel(reservation_id):
    with sqlite3.connect(DB) as con:
        row = con.execute(
            "SELECT spot_id FROM reservations WHERE id = ?",
            (reservation_id,),
        ).fetchone()
        if row is None:
            return "Reservation not found.", 404
        con.execute("DELETE FROM reservations WHERE id = ?", (reservation_id,))
        con.execute(
            "UPDATE parking_spots SET status = 'Available' WHERE id = ?",
            (row[0],),
        )
    return jsonify(ok=True)


init_db()

if __name__ == "__main__":
    app.run(debug=True,host="0.0.0.0")
