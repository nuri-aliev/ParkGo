"""Validate sensor input and race it against a real booking transaction."""
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor
import threading
import time
import unittest
from unittest.mock import patch
import test_bookings as bookings
park = bookings.park


class SensorTests(unittest.TestCase):
    setUp = bookings.BookingTests.setUp

    def send(self, data, token=None):
        return park.app.test_client().post('/api/sensor', json=data,
            headers={'X-Sensor-Token': park.SENSOR_TOKEN if token is None else token})

    def test_malformed_json_and_token_are_client_errors(self):
        for value in [[], [1], 'wrong', 1, None]:
            self.assertEqual(self.send(value).status_code, 400)
        self.assertEqual(self.send({'spot_id': 1, 'status': 'Available'}, 'неверный').status_code, 401)
        for value in [{}, {'spot_id': 'wrong', 'status': 'Occupied'}, {'spot_id': 1, 'status': 'Reserved'}]:
            self.assertEqual(self.send(value).status_code, 400)

    def test_sensor_cannot_overwrite_a_concurrent_reservation(self):
        read = threading.Event()
        release = threading.Event()
        original_database = park.database

        class PausingConnection:
            def __init__(self, con): self.con = con
            @property
            def row_factory(self): return self.con.row_factory
            @row_factory.setter
            def row_factory(self, value): self.con.row_factory = value
            def execute(self, sql, *args):
                result = self.con.execute(sql, *args)
                if sql == 'SELECT status FROM parking_spots WHERE id = ?':
                    read.set()
                    if not release.wait(3): raise RuntimeError('Test coordination timeout')
                return result
            def __getattr__(self, name): return getattr(self.con, name)

        @contextmanager
        def paused_database():
            with original_database() as con:
                yield PausingConnection(con)

        with patch.object(park, 'database', paused_database), ThreadPoolExecutor(2) as pool:
            sensor = pool.submit(self.send, {'spot_id': 1, 'status': 'Available'})
            self.assertTrue(read.wait(3))
            booking = pool.submit(bookings.BookingTests.book, self, 1)
            # Give the booking a chance to run while the sensor holds its read.
            time.sleep(.15)
            release.set()
            self.assertEqual(sensor.result().status_code, 200)
            self.assertEqual(booking.result().status_code, 200)
        with original_database() as con:
            self.assertEqual(con.execute('SELECT status FROM parking_spots WHERE id=1').fetchone()[0], 'Reserved')
        self.assertEqual(self.send({'spot_id': 1, 'status': 'Available'}).status_code, 409)
