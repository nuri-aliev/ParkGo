import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from urllib.error import URLError
from urllib.request import urlopen


class StartupTests(unittest.TestCase):
    def test_server_uses_configured_port_from_another_directory(self):
        root = Path(__file__).resolve().parents[1]
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
        with tempfile.TemporaryDirectory() as tmp:
            env = dict(os.environ, PARKGO_DB=str(Path(tmp) / 'parking.db'),
                       PARKGO_HOST='127.0.0.1', PARKGO_PORT=str(port))
            with tempfile.TemporaryFile() as log:
                process = subprocess.Popen([sys.executable, str(root / 'app.py')],
                                           cwd=tmp, env=env, stdout=log, stderr=log)
                try:
                    deadline = time.monotonic() + 6
                    while time.monotonic() < deadline and process.poll() is None:
                        try:
                            with urlopen(f'http://127.0.0.1:{port}/login', timeout=.5) as response:
                                self.assertEqual(response.status, 200)
                                self.assertIn(b'ParkGo', response.read())
                            self.assertTrue((Path(tmp) / 'parking.db').exists())
                            return
                        except (URLError, TimeoutError):
                            time.sleep(.1)
                    self.fail('Сервер не запустился на PARKGO_PORT')
                finally:
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
