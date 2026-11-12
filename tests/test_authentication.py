"""Registration and SMTP regression tests. No real messages are sent."""
import hashlib
import os
import unittest
from urllib.parse import urlsplit
from unittest.mock import patch, MagicMock
from test_bookings import park


class AuthenticationTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {
            'PARKGO_REGISTRATION_MODE': 'verified', 'PARKGO_SMTP_HOST': 'smtp.example.test',
            'PARKGO_SMTP_FROM': 'parkgo@example.test', 'PARKGO_SMTP_PORT': '587',
            'PARKGO_SMTP_SECURITY': 'starttls', 'PARKGO_SMTP_USER': 'sender',
            'PARKGO_SMTP_PASSWORD': 'test-only', 'PARKGO_PUBLIC_URL': 'https://parkgo.example.test',
        })
        self.env.start()
        self.addCleanup(self.env.stop)
        park.FAILS.clear()
        with park.database() as con:
            con.execute('DELETE FROM pending_registrations')
            con.execute("DELETE FROM users WHERE email LIKE 'auth-%'")
        self.client = park.app.test_client()
        self.client.get('/login')
        with self.client.session_transaction() as session:
            self.csrf = session['csrf_token']
        self.form = dict(email='auth-new@astanait.edu.kz', full_name='Auth <Test>',
                         password='test-password', csrf_token=self.csrf, next='/?pane=promos')

    def register(self, **changes):
        return self.client.post('/register', data={**self.form, **changes})

    def test_missing_configuration_preserves_form_and_explains_in_russian(self):
        with patch.dict(os.environ, {'PARKGO_SMTP_HOST': ''}), patch.object(park, 'send_verification_email') as send:
            response = self.register()
        self.assertEqual(response.status_code, 503)
        send.assert_not_called()
        self.assertIn('Отправка писем не настроена', response.text)
        self.assertIn('value="auth-new@astanait.edu.kz"', response.text)
        self.assertIn('value="Auth &lt;Test&gt;"', response.text)
        self.assertNotIn('test-password', response.text)
        self.assertEqual(self.client.get('/api/reservations').status_code, 401)

    def test_delivery_failure_removes_pending_registration(self):
        with patch.object(park, 'send_verification_email', side_effect=OSError('offline')):
            self.assertEqual(self.register().status_code, 503)
        with park.database() as con:
            self.assertEqual(con.execute('SELECT COUNT(*) FROM pending_registrations').fetchone()[0], 0)
        self.assertEqual(self.client.get('/api/reservations').status_code, 401)

    def test_opaque_one_time_link_and_success_status(self):
        with patch.object(park, 'send_verification_email') as send:
            response = self.register()
        self.assertEqual(response.status_code, 200)
        self.assertIn('class="err success"', response.text)
        self.assertIn('role="status"', response.text)
        link = send.call_args.args[1]
        self.assertTrue(link.startswith('https://parkgo.example.test/verify-email/'))
        token = link.rsplit('/', 1)[1]
        self.assertRegex(token, r'^[A-Za-z0-9_-]{43}$')
        with park.database() as con:
            row = con.execute('SELECT token_hash, password_hash FROM pending_registrations').fetchone()
        self.assertEqual(row[0], hashlib.sha256(token.encode()).hexdigest())
        self.assertNotIn(row[1], link)
        self.assertEqual(self.client.get('/api/reservations').status_code, 401)
        verified = self.client.get(urlsplit(link).path)
        self.assertEqual(verified.status_code, 302)
        self.assertEqual(verified.location, '/?pane=promos')
        self.assertEqual(self.client.get('/api/reservations').status_code, 200)
        self.assertEqual(park.app.test_client().get(link).status_code, 400)
        with park.database() as con:
            self.assertEqual(con.execute('SELECT COUNT(*) FROM pending_registrations').fetchone()[0], 0)

    def test_expired_and_forged_links_do_not_create_accounts(self):
        with patch.object(park, 'send_verification_email') as send:
            self.register()
        link = send.call_args.args[1]
        self.assertEqual(self.client.get(link + 'wrong').status_code, 400)
        with park.database() as con:
            con.execute('UPDATE pending_registrations SET expires_at=1')
        self.assertEqual(self.client.get(link).status_code, 400)
        self.assertEqual(self.client.get('/api/reservations').status_code, 401)

    def test_demo_requires_explicit_opt_in_and_does_not_send_mail(self):
        with patch.dict(os.environ, {'PARKGO_REGISTRATION_MODE': 'demo', 'PARKGO_SMTP_HOST': ''}), patch.object(park, 'send_verification_email') as send:
            self.assertIn('Demo mode: email ownership is not verified.', self.client.get('/login').text)
            self.assertEqual(self.register().status_code, 302)
        send.assert_not_called()
        self.assertEqual(self.client.get('/api/reservations').status_code, 200)
        with park.database() as con:
            password_hash = con.execute('SELECT password_hash FROM users WHERE email=?', (self.form['email'],)).fetchone()[0]
        self.assertTrue(park.check_password_hash(password_hash, self.form['password']))

    def test_smtp_465_uses_verified_ssl_without_starttls(self):
        connection = MagicMock()
        with patch.dict(os.environ, {'PARKGO_SMTP_PORT': '465', 'PARKGO_SMTP_SECURITY': 'ssl'}), patch.object(park.smtplib, 'SMTP_SSL', return_value=connection) as smtp:
            park.send_verification_email('student@astanait.edu.kz', 'https://example.test/verify')
        self.assertEqual(smtp.call_args.args, ('smtp.example.test', 465))
        self.assertTrue(smtp.call_args.kwargs['context'].check_hostname)
        connection.__enter__.return_value.starttls.assert_not_called()
        connection.__enter__.return_value.send_message.assert_called_once()

    def test_smtp_587_uses_starttls_and_authentication(self):
        connection = MagicMock()
        with patch.object(park.smtplib, 'SMTP', return_value=connection):
            park.send_verification_email('student@astanait.edu.kz', 'https://example.test/verify')
        smtp = connection.__enter__.return_value
        smtp.starttls.assert_called_once()
        smtp.login.assert_called_once_with('sender', 'test-only')
        smtp.send_message.assert_called_once()

    def test_invalid_configuration_is_handled_without_server_error(self):
        for values in ({'PARKGO_SMTP_PORT': 'bad'}, {'PARKGO_SMTP_SECURITY': 'none'},
                       {'PARKGO_REGISTRATION_MODE': 'typo'}, {'PARKGO_PUBLIC_URL': 'https://host/path'}):
            with self.subTest(values=values), patch.dict(os.environ, values), patch.object(park, 'send_verification_email') as send:
                self.assertEqual(self.register().status_code, 503)
                send.assert_not_called()

    def test_local_redirect_only(self):
        for value in ['//evil.test', '/\\evil.test', '/\nevil.test', 'https://evil.test']:
            self.assertEqual(park.safe_next(value), '/')
        self.assertEqual(park.safe_next('/?pane=promos'), '/?pane=promos')

    def test_successful_login_resets_previous_failures(self):
        with patch.dict(os.environ, {'PARKGO_REGISTRATION_MODE': 'demo'}):
            self.register()
        self.client.get('/logout')
        self.client.get('/login')
        with self.client.session_transaction() as session:
            csrf = session['csrf_token']
        key = self.form['email'] + '|127.0.0.1'
        park.FAILS[key] = [park.time.time()] * 4
        response = self.client.post('/login', data={'email': self.form['email'], 'password': self.form['password'], 'csrf_token': csrf})
        self.assertEqual(response.status_code, 302)
        self.assertNotIn(key, park.FAILS)

    def test_unicode_csrf_returns_forbidden_not_server_error(self):
        response = self.register(csrf_token='неверный')
        self.assertEqual(response.status_code, 403)
