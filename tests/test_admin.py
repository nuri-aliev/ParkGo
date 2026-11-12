import unittest
import test_bookings as bookings
park = bookings.park

class AdminTests(unittest.TestCase):
    def setUp(self):
        bookings.BookingTests.setUp(self)
        with park.database() as con:
            uid = con.execute("SELECT id FROM users WHERE role='admin'").fetchone()[0]
        with self.client.session_transaction() as session:
            session['uid'] = uid

    def test_promo_validation_and_duplicate_does_not_replace_limit(self):
        form = dict(code='ADMIN25', kind='percent', value=25, duration_hours=1, max_uses=2)
        self.assertEqual(self.client.post('/admin/promos', data=form).status_code, 303)
        self.client.post('/admin/promos', data={**form, 'max_uses': 100})
        self.client.post('/admin/promos', data={**form, 'code': 'INVALID', 'value': 101})
        with park.database() as con:
            self.assertEqual(con.execute("SELECT max_uses FROM promo_codes WHERE code='ADMIN25'").fetchone()[0], 2)
            self.assertIsNone(con.execute("SELECT code FROM promo_codes WHERE code='INVALID'").fetchone())

    def test_report_resolution_rejects_missing_report(self):
        response = self.client.post('/support', data={'message': 'Admin test', 'category': 'chat'})
        rid = response.json['id']
        self.assertEqual(self.client.post(f'/admin/report/{rid}/resolve').status_code, 200)
        self.assertEqual(self.client.post('/admin/report/999999/resolve').status_code, 404)
        with park.database() as con:
            self.assertEqual(con.execute('SELECT status FROM support_reports WHERE id=?', (rid,)).fetchone()[0], 'resolved')

    def test_charging_marker_validation(self):
        self.assertEqual(self.client.post('/admin/charging', data={'lot': 'unknown', 'enabled': '1'}).status_code, 400)
        for value in ['1', '0']:
            self.assertEqual(self.client.post('/admin/charging', data={'lot': 'Campus North', 'enabled': value}).status_code, 303)
            spots = self.client.get('/api/spots').json
            self.assertEqual(next(s for s in spots if s['loc'] == 'Campus North')['ev_charging'], value == '1')
