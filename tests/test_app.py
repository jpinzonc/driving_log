import os
import unittest
os.environ['SECRET_KEY'] = 'test-only'
os.environ['DATABASE_URL'] = 'sqlite://'
from app import app, db, Student, Drive

class LogTests(unittest.TestCase):
    def setUp(self):
        app.config['TESTING'] = True
        self.ctx = app.app_context()
        self.ctx.push()
        db.create_all()
        db.session.add(Student(id=1, name='Test Driver', permit='123'))
        db.session.commit()
        self.client = app.test_client()
        self.client.get('/')
        with self.client.session_transaction() as s:
            self.token = s['csrf']

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.ctx.pop()

    def data(self, **kwargs):
        return dict(csrf=self.token, date='2026-01-01', time='18:30', topic='0', day='30', night='30',
                    initials='AB', license='123456', notes='Evening practice', **kwargs)

    def test_session_summary_edit_export_delete(self):
        payload = self.data()
        self.assertEqual(self.client.post('/sessions/new', data=payload).status_code, 302)
        row = db.session.query(Drive).one()
        self.assertEqual(row.day + row.night, 60)
        self.assertIn(b'29 <small>hrs', self.client.get('/').data)
        self.assertIn(b'9.5 nighttime hours remaining', self.client.get('/').data)
        payload.update(day='60', notes='=SUM(1,2)')
        self.assertEqual(self.client.post(f'/sessions/{row.id}/edit', data=payload).status_code, 302)
        csv = self.client.get('/download.csv')
        self.assertIn(b"'=SUM(1,2)", csv.data)
        self.assertIn(b'1.5000', csv.data)
        self.assertIn('attachment', csv.headers['Content-Disposition'])
        self.assertEqual(self.client.post(f'/sessions/{row.id}/delete', data={'csrf':self.token}).status_code, 302)
        self.assertEqual(db.session.query(Drive).count(), 0)

    def test_daily_cap_and_validation(self):
        payload = self.data()
        payload.update(day='90', night='30')
        self.assertEqual(self.client.post('/sessions/new', data=payload).status_code, 302)
        self.assertEqual(self.client.post('/sessions/new', data=self.data()).status_code, 400)
        row = db.session.query(Drive).one()
        self.assertEqual(self.client.post(f'/sessions/{row.id}/edit', data=payload).status_code, 302)
        for change in [{'day':'-1'}, {'night':'NaN'}, {'day':'0.5'}, {'date':'2999-01-01'}, {'topic':'10'}, {'initials':''}, {'day':'0','night':'0'}]:
            invalid = self.data()
            invalid.update(change)
            self.assertEqual(self.client.post('/sessions/new', data=invalid).status_code, 400)
        self.assertEqual(db.session.query(Drive).count(), 1)

    def test_csrf_and_empty_export(self):
        self.assertEqual(self.client.post('/sessions/new', data={}).status_code, 400)
        self.assertEqual(len(self.client.get('/download.csv').data.decode('utf-8-sig').splitlines()), 1)
        self.assertEqual(self.client.get('/health').status_code, 200)

if __name__ == '__main__':
    unittest.main()
