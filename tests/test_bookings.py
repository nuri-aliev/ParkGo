import os
import sys
import tempfile
import unittest
import sqlite3
from unittest.mock import patch
from io import BytesIO
from concurrent.futures import ThreadPoolExecutor

TMP = tempfile.TemporaryDirectory()
os.environ['PARKGO_DB'] = os.path.join(TMP.name, 'test.db')
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import app as park

class BookingTests(unittest.TestCase):
    def setUp(self):
        self.client = park.app.test_client()
        with sqlite3.connect(park.DB) as con:
            con.execute('DELETE FROM reservations')
            con.execute("UPDATE parking_spots SET status='Available'")
            for uid in [101, 102]:
                con.execute("INSERT OR IGNORE INTO users (id,email,password_hash,role,created_at) VALUES (?,?,'test','user','2026-01-01')",(uid,f'{uid}@astanait.edu.kz'))
        with self.client.session_transaction() as sess: sess['uid']=101; sess['csrf_token']='test-token'
        self.client.environ_base['HTTP_X_CSRF_TOKEN']='test-token'

    def book(self, spot, key='one', minutes=30, client=None):
        return (client or self.client).post(f'/book/{spot}', data=dict(customer_name='Test',car_number='123 ABC',minutes=minutes,request_key=key),headers={'X-Requested-With':'fetch'})

    def test_reload_multiple_cancel_and_privacy(self):
        a=self.book(1).json['reservation_id']; b=self.book(2,'two').json['reservation_id']
        self.assertEqual(len(self.client.get('/api/reservations').json),2)
        page=self.client.get('/').text
        self.assertIn('123 ABC',page)
        self.assertNotIn('class="adm"',page)
        self.assertEqual(self.client.get('/admin').status_code,403)
        other=park.app.test_client()
        with other.session_transaction() as sess: sess['uid']=102; sess['csrf_token']='test-token'
        other.environ_base['HTTP_X_CSRF_TOKEN']='test-token'
        self.assertEqual(other.get('/api/reservations').json,[])
        self.assertEqual(other.post(f'/cancel/{a}').status_code,403)
        self.assertEqual(self.client.post(f'/cancel/{a}').status_code,200)
        self.assertEqual([x['id'] for x in self.client.get('/api/reservations').json],[b])
        self.assertEqual(park.app.test_client().get('/api/reservations').status_code,401)
        with sqlite3.connect(park.DB) as con: admin=con.execute("SELECT id FROM users WHERE role='admin'").fetchone()[0]
        with other.session_transaction() as sess: sess['uid']=admin
        self.assertIn('class="adm"',other.get('/').text)
        self.assertEqual(other.get('/admin').status_code,200)

    def test_duration_expiry_legacy_and_retry(self):
        first=self.book(1,minutes=120).json['reservation_id']
        self.assertEqual(self.book(1,minutes=120).json['reservation_id'],first)
        self.assertEqual(len(self.client.get('/api/reservations').json),1)
        expiry=self.client.get('/api/reservations').json[0]['expires_at']
        self.assertAlmostEqual(expiry-park.time.time(),7200,delta=3)
        self.assertEqual(self.book(2,'bad',minutes=999).status_code,400)
        with sqlite3.connect(park.DB) as con:
            con.execute('UPDATE reservations SET expires_at=1 WHERE id=?',(first,))
        self.assertEqual(self.client.get('/api/reservations').json,[])
        self.assertTrue(next(s for s in self.client.get('/api/spots').json if s['id']==1)['free'])
        self.book(1,'legacy')
        with sqlite3.connect(park.DB) as con: con.execute('UPDATE reservations SET expires_at=NULL')
        self.assertEqual(len(self.client.get('/api/reservations').json),1)

    def test_competing_bookings(self):
        def attempt(uid):
            client=park.app.test_client()
            with client.session_transaction() as sess: sess['uid']=uid; sess['csrf_token']='test-token'
            client.environ_base['HTTP_X_CSRF_TOKEN']='test-token'
            return self.book(1,str(uid),client=client).status_code
        with ThreadPoolExecutor(2) as pool: results=list(pool.map(attempt,[101,102]))
        self.assertEqual(sorted(results),[200,409])

    def test_currency(self):
        park.FX_CACHE['checked']=0
        xml=b'<rates><item><title>USD</title><description>500</description><quant>1</quant></item></rates>'
        with patch.object(park.urllib.request,'urlopen',return_value=BytesIO(xml)):
            self.assertEqual(self.client.get('/api/exchange-rate').json['kzt_per_usd'],500)
        park.FX_CACHE['checked']=0
        with patch.object(park.urllib.request,'urlopen',side_effect=OSError()):
            self.assertEqual(self.client.get('/api/exchange-rate').status_code,503)

if __name__=='__main__': unittest.main()
