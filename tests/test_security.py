import unittest
import os
from unittest.mock import patch
from test_bookings import park, BookingTests

class SecurityTests(BookingTests):
    def setUp(self):
        super().setUp()
        env = patch.dict(os.environ, {
            'PARKGO_REGISTRATION_MODE': 'verified', 'PARKGO_SMTP_HOST': 'smtp.example.test',
            'PARKGO_SMTP_FROM': 'parkgo@example.test', 'PARKGO_SMTP_PORT': '587',
            'PARKGO_SMTP_SECURITY': 'starttls', 'PARKGO_PUBLIC_URL': ''})
        env.start()
        self.addCleanup(env.stop)

    def test_cross_site_post_is_rejected(self):
        response = self.client.post('/cancel/1', headers={'X-CSRF-Token': '', 'Origin': 'https://evil.example'})
        self.assertEqual(response.status_code, 403)

    def test_registration_unavailable_without_mail_does_not_create_user(self):
        client = park.app.test_client()
        client.get('/login')
        with client.session_transaction() as sess: token = sess['csrf_token']
        with patch.object(park, 'send_verification_email', side_effect=OSError('offline')):
            response = client.post('/register', data={'csrf_token': token, 'email': 'offline@astanait.edu.kz', 'password': 'password123'})
        self.assertEqual(response.status_code, 503)
        with park.database() as con:
            self.assertIsNone(con.execute("SELECT id FROM users WHERE email = 'offline@astanait.edu.kz'").fetchone())

    def test_registration_requires_verified_email(self):
        client = park.app.test_client()
        client.get('/login')
        with client.session_transaction() as sess: token = sess['csrf_token']
        with patch.object(park, 'send_verification_email') as send:
            response = client.post('/register', data={'csrf_token':token,'email':'new@astanait.edu.kz','password':'password123','full_name':'New'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(client.get('/api/reservations').status_code, 401)
        link = send.call_args.args[1]
        self.assertEqual(client.get(link).status_code, 302)
        self.assertEqual(client.get('/api/reservations').status_code, 200)
