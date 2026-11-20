"""Isolated Kobo import checks; no real Kobo account or device data is read."""
import json
import os
from pathlib import Path
import subprocess
import unittest
from datetime import date

ROOT=Path(__file__).resolve().parents[1]
os.environ.update(DATABASE_URL='sqlite:///'+str(ROOT/'tests/test_kobo.db').replace('\\','/'),BACKGROUND_JOBS='false')
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, select
from app.main import app
from app.db import engine
from app.auth import hash_password
from app.models import Category, CollectionEntry, User, Work
from app import kobo


class KoboTests(unittest.TestCase):
    def setUp(self):
        SQLModel.metadata.drop_all(engine); SQLModel.metadata.create_all(engine)
        self.client=TestClient(app,follow_redirects=False)
        with Session(engine) as s:
            u=User(username='kobo_test',display_name='Test',birth_date=date(2000,1,1),password_hash=hash_password('test-only-123'))
            s.add(u);s.commit();s.refresh(u);self.uid=u.id
        self.client.post('/login',data={'username':'kobo_test','password':'test-only-123'})

    def tearDown(self): self.client.close()

    def post(self, rows):
        return self.client.post('/me/kobo/import',data={'payload':json.dumps({'format':'yodo-kobo-v1','books':rows},ensure_ascii=False)})

    def test_private_review_and_repeat(self):
        rows=[{'title':'小王子','author':'Saint-Exupéry','status':'read','isbn':'9781234567897'}, {'title':'另一書','status':'reading'}]
        r=self.post(rows);self.assertEqual(r.status_code,303);self.assertEqual(r.headers['location'],'/me/review/book')
        with Session(engine) as s:
            entries=s.exec(select(CollectionEntry)).all();self.assertEqual(len(entries),2)
            self.assertTrue(all(e.pending_review for e in entries));eid=entries[0].id
            self.assertEqual(entries[0].status,'read')
        profile=self.client.get('/u/kobo_test');self.assertNotIn('小王子',profile.text)
        review=self.client.get('/me/review/book');self.assertIn('讀完',review.text)
        self.client.post('/me/review/book',data={'publish':str(eid)})
        self.assertIn('小王子',self.client.get('/u/kobo_test').text)
        self.post(rows)
        with Session(engine) as s:
            entries=s.exec(select(CollectionEntry)).all();self.assertEqual(len(entries),2)
            self.assertEqual(sum(e.hidden for e in entries),1)
            self.assertTrue(all(not e.pending_review for e in entries))

    def test_reuse_exact_existing_and_preserve(self):
        with Session(engine) as s:
            w=Work(category=Category.book,source='googlebooks',external_id='one',title='小王子',creator='作者',cover_url='https://example.invalid/cover')
            s.add(w);s.flush();s.add(CollectionEntry(user_id=self.uid,work_id=w.id,status='want',tier='great',hidden=True));s.commit()
        self.post([{'title':' 小王子 ','author':'作者','status':'read'}])
        with Session(engine) as s:
            self.assertEqual(len(s.exec(select(Work)).all()),1)
            e=s.exec(select(CollectionEntry)).one();self.assertEqual(e.status,'want');self.assertTrue(e.hidden);self.assertEqual(e.tier,'great')

    def test_validation_and_text(self):
        for payload in ['[]','broken',json.dumps({'format':'yodo-kobo-v1','books':[{'title':'x','status':[]} ]})]:
            self.assertEqual(self.client.post('/me/kobo/import',data={'payload':payload}).status_code,400)
        r=self.client.post('/me/kobo/import',data={'text':'小王子\t作者\n另一書','status':'reading'})
        self.assertEqual(r.status_code,303)
        self.assertEqual(len(kobo.parse_text('小王子\t作者\n 小王子 \t作者','reading')),1)
        with self.assertRaises(kobo.KoboFormatError):kobo.parse_metadata('x'*900001)
        with self.assertRaises(kobo.KoboFormatError):kobo.parse_metadata(json.dumps({'format':'yodo-kobo-v1','books':[{'title':'a'}]*5001}))

    def test_auth_and_entry(self):
        self.assertEqual(TestClient(app,follow_redirects=False).post('/me/kobo/import',data={'text':'a'}).status_code,303)
        self.assertIn('從 Kobo 匯入書單',self.client.get('/me/collection#book').text)
        page=self.client.get('/me/kobo');self.assertEqual(page.status_code,200)
        self.assertNotIn('type="password"',page.text)
        self.assertIn('id="kobo-file"',page.text)
        self.assertNotIn('name="file"',page.text)

    def test_user_isolation_and_details(self):
        self.post([{'title':'隱私書籍','status':'read'}])
        with Session(engine) as s:
            w=s.exec(select(Work)).one();wid=w.id
            u=User(username='second',display_name='Second',birth_date=date(2000,1,1),password_hash=hash_password('test-only-123'))
            s.add(u);s.commit()
        self.client.post('/logout')
        self.client.post('/login',data={'username':'second','password':'test-only-123'})
        self.assertNotIn('隱私書籍',self.client.get('/me/review/book').text)
        self.assertNotIn('隱私書籍',self.client.get('/u/kobo_test').text)
        self.client.post('/logout')
        self.client.post('/login',data={'username':'kobo_test','password':'test-only-123'})
        self.assertEqual(self.client.get(f'/u/kobo_test/w/{wid}').status_code,404)
        with Session(engine) as s:eid=s.exec(select(CollectionEntry.id)).one()
        self.client.post('/me/review/book',data={'publish':str(eid)})
        self.assertEqual(self.client.get(f'/u/kobo_test/w/{wid}').status_code,200)

    def test_browser_sqlite(self):
        result=subprocess.run(['node',str(ROOT/'tests/kobo_reader.cjs')],capture_output=True,text=True,encoding='utf-8')
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)


if __name__=='__main__':unittest.main()
