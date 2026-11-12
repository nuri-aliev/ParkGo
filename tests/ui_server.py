"""Isolated UI test server. Never opens the project's parking.db.

Run: .venv/bin/python tests/ui_server.py [--reference-layout]
"""
import os
from pathlib import Path
import sqlite3
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
temporary = tempfile.TemporaryDirectory(prefix="parkgo-ui-")
os.environ["PARKGO_DB"] = str(Path(temporary.name) / "parking.db")
import app as park
from werkzeug.security import generate_password_hash

with sqlite3.connect(park.DB) as con:
    con.execute("INSERT INTO users(email,full_name,password_hash,role,created_at) VALUES (?, ?, ?, 'user', ?)",
                ("test@astanait.edu.kz", "Test", generate_password_hash("test-password"), park.now()))
    if "--reference-layout" in sys.argv:
        con.executemany("INSERT INTO parking_spots(name,location,price,status) VALUES (?, 'Campus North', 500, 'Available')",
                        [(f"A{i:02}",) for i in range(3, 17)])
        con.executemany("UPDATE parking_spots SET status='Occupied' WHERE name=? AND location='Campus North'",
                        [(f"A{i:02}",) for i in (1, 2, 5, 6, 10, 12, 14)])

park.app.config["TEMPLATES_AUTO_RELOAD"] = True
park.app.run(host="127.0.0.1", port=int(os.environ.get("PARKGO_TEST_PORT", "5055")), debug=False)
