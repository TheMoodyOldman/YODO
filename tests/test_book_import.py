"""Synthetic book import + OAuth checks; never read real accounts or credentials."""
import asyncio
import base64
import hashlib
import os
from datetime import date
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse
import unittest

ROOT = Path(__file__).resolve().parents[1]
os.environ.update(DATABASE_URL='sqlite:///' + str(ROOT/'tests/test_book_import.db').replace('\\','/'),
                  BACKGROUND_JOBS='false', GOOGLE_BOOKS_CLIENT_ID='test-client',
                  GOOGLE_BOOKS_CLIENT_SECRET='test-secret', GOOGLE_BOOKS_REDIRECT_URI='http://localhost/me/google-books/callback')
import httpx
from fastapi.testclient import TestClient
from sqlmodel import SQLModel, Session, select
from app.main import app
from app.db import engine
from app.auth import hash_password
from app.config import settings
from app.models import User, Work, CollectionEntry, Category
from app.services import google_books as google

REAL_CLIENT = httpx.AsyncClient

def volume(i, title=None):
    return {'id': str(i), 'volumeInfo': {'title': title or 'Book '+str(i), 'authors': ['Author'],
            'publishedDate': '2024-02-03', 'imageLinks': {'thumbnail': 'http://example.invalid/cover'}}}

class ImportTests(unittest.TestCase):
    def setUp(self):
        SQLModel.metadata.drop_all(engine); SQLModel.metadata.create_all(engine)
        self.client = TestClient(app, follow_redirects=False)
        with Session(engine) as s:
            u = User(username='book_test', display_name='Test', birth_date=date(2000,1,1), password_hash=hash_password('test-only-123'))
            s.add(u); s.commit(); s.refresh(u); self.uid = u.id
        self.client.post('/login', data={'username':'book_test','password':'test-only-123'})

    def tearDown(self): self.client.close()

    def authorize(self, **kwargs):
        r = self.client.get('/me/google-books/connect', params=kwargs)
        self.assertEqual(r.status_code, 303)
        return parse_qs(urlparse(r.headers['location']).query)

    def test_manual_import_review_and_cross_source_preservation(self):
        r = self.client.post('/me/books/import', data={'text':'小王子\t作者\n小王子\t作者','status':'read'})
        self.assertEqual(r.headers['location'], '/me/review/book')
        with Session(engine) as s:
            w = s.exec(select(Work)).one(); self.assertEqual(w.source, 'manual')
            e = s.exec(select(CollectionEntry)).one(); self.assertTrue(e.pending_review)
            e.status='want'; e.hidden=True; e.tier='great'; s.add(e); s.commit()
        self.client.post('/me/kobo/import', data={'text':'小王子\t作者','status':'read'})
        with Session(engine) as s:
            self.assertEqual(len(s.exec(select(Work)).all()), 1)
            e=s.exec(select(CollectionEntry)).one(); self.assertEqual(e.status, 'want')
            self.assertTrue(e.hidden); self.assertEqual(e.tier, 'great')
        self.assertNotIn('小王子', self.client.get('/u/book_test').text)

    def test_manual_error_and_auth(self):
        for data in ({'text':''}, {'text':'Keep me','status':'invalid'}):
            r=self.client.post('/me/books/import',data=data)
            self.assertEqual(r.status_code,400); self.assertIn('data-default="book"',r.text)
            self.assertIn('role="alert"',r.text)
        self.assertIn('Keep me',r.text)
        with TestClient(app,follow_redirects=False) as anon:
            self.assertEqual(anon.post('/me/books/import',data={'text':'Book'}).headers['location'].split('?')[0],'/login')
            for url in ('/me/google-books/connect','/me/google-books/callback'):
                self.assertEqual(anon.get(url).headers['location'].split('?')[0],'/login')

    def test_configured_and_disabled_ui(self):
        self.assertIn('登入 Google，匯入書櫃',self.client.get('/me/collection').text)
        with patch.object(settings,'google_books_client_secret',''):
            self.assertIn('disabled>Google 書櫃連結尚未開放',self.client.get('/me/collection').text)
            self.assertEqual(self.client.get('/me/google-books/connect').headers['location'],'/me/collection#book')
        with patch.object(settings,'google_books_redirect_uri','http://unsafe.invalid/callback'):
            self.assertEqual(self.client.get('/me/google-books/connect').headers['location'],'/me/collection#book')

    def test_authorization_scope_and_pkce(self):
        q=self.authorize(include_owned=1)
        self.assertEqual(q['scope'],[google.SCOPE]); self.assertEqual(q['access_type'],['online'])
        self.assertEqual(q['code_challenge_method'],['S256']); self.assertNotIn('client_secret',q)
        expected=base64.urlsafe_b64encode(hashlib.sha256(b'verifier').digest()).rstrip(b'=').decode()
        q2=parse_qs(urlparse(google.authorization_url('http://localhost','state','verifier')).query)
        self.assertEqual(q2['code_challenge'],[expected])

    def test_invalid_expired_cancelled_and_replayed(self):
        with patch.object(google,'read_library') as read:
            q=self.authorize(); self.client.get('/me/google-books/callback',params={'state':'wrong','code':'c'})
            self.client.get('/me/google-books/callback',params={'state':q['state'][0],'code':'c'})
            q=self.authorize(); self.client.get('/me/google-books/callback',params={'state':q['state'][0],'error':'access_denied'})
            q=self.authorize()
            import time
            from types import SimpleNamespace
            with patch('app.routers.book_import.time',SimpleNamespace(time=lambda:time.time()+601)):
                self.client.get('/me/google-books/callback',params={'state':q['state'][0],'code':'c'})
            q=self.authorize(); self.client.post('/logout')
            self.client.post('/login',data={'username':'book_test','password':'test-only-123'})
            self.client.get('/me/google-books/callback',params={'state':q['state'][0],'code':'c'})
            read.assert_not_called()

    def test_callback_import_and_provider_id_reuse(self):
        row={'title':'Google book','author':'Author','provider_id':'id_one','status':'read','cover_url':'https://example.invalid/cover','year':2024}
        with patch.object(google,'read_library',return_value=([row],False)) as read:
            q=self.authorize(include_owned=1)
            r=self.client.get('/me/google-books/callback',params={'state':q['state'][0],'code':'synthetic-code'})
            self.assertEqual(r.headers['location'],'/me/review/book')
            self.assertEqual(read.call_args.args[-1],True)
            self.assertNotIn('synthetic-code',r.headers.get('set-cookie',''))
            self.client.get('/me/google-books/callback',params={'state':q['state'][0],'code':'synthetic-code'})
            self.assertEqual(read.call_count,1)
        row['title']='Provider changed title'
        with patch.object(google,'read_library',return_value=([row],False)):
            q=self.authorize(); self.client.get('/me/google-books/callback',params={'state':q['state'][0],'code':'c'})
        with Session(engine) as s:
            w=s.exec(select(Work)).one(); self.assertEqual(w.source,'googlebooks'); self.assertEqual(w.external_id,'id_one')
            self.assertEqual(w.year,2024); self.assertEqual(w.cover_url,row['cover_url'])
            e=s.exec(select(CollectionEntry)).one(); self.assertTrue(e.pending_review); self.assertEqual(e.status,'read')

    def test_callback_failure_has_no_writes_or_sensitive_flash(self):
        for result in ('fail','empty'):
            kwargs={'side_effect':google.GoogleBooksError('private-token')} if result=='fail' else {'return_value':([],False)}
            with patch.object(google,'read_library',**kwargs):
                q=self.authorize(); r=self.client.get('/me/google-books/callback',params={'state':q['state'][0],'code':'c'})
                self.assertEqual(r.status_code,303); self.assertNotIn('private-token',self.client.get('/me/collection').text)
        with Session(engine) as s:self.assertEqual(len(s.exec(select(Work)).all()),0)

    def fetch(self, handler, include_owned=False):
        transport=httpx.MockTransport(handler)
        with patch.object(google.httpx,'AsyncClient',side_effect=lambda **kw:REAL_CLIENT(transport=transport,**kw)):
            return asyncio.run(google.read_library('code','http://localhost','verifier',include_owned))

    def test_api_pagination_dedup_status_and_memory_token(self):
        calls=[]
        def handler(request):
            calls.append(request)
            if request.url == google.TOKEN_URL:
                self.assertEqual(request.method,'POST'); self.assertIn(b'code_verifier=verifier',request.content)
                return httpx.Response(200,json={'access_token':'MEMORY_ONLY_TOKEN'})
            self.assertEqual(request.method,'GET'); self.assertEqual(request.headers['authorization'],'Bearer MEMORY_ONLY_TOKEN')
            shelf=request.url.path.split('/')[-2]; start=int(request.url.params['startIndex'])
            rows={('4',0):[volume('one')],('4',1):[volume('two')],('3',0):[volume('one'),volume('three')],('2',0):[volume('want')],('1',0):[volume('bought')],('7',0):[volume('ebook')]}.get((shelf,start),[])
            return httpx.Response(200,json={'totalItems':2 if shelf=='4' else len(rows),'items':rows})
        rows,truncated=self.fetch(handler,True); self.assertFalse(truncated)
        self.assertEqual({r['provider_id']:r['status'] for r in rows},{'one':'read','two':'read','three':'reading','want':'want','bought':None,'ebook':None})
        self.assertTrue(all(r['cover_url'].startswith('https:') and r['year']==2024 for r in rows))
        self.assertNotIn('MEMORY_ONLY_TOKEN',str(rows)); self.assertEqual(len(calls),7)

    def test_api_errors_and_malformed_data(self):
        for status,payload in [(401,{}),(403,{}),(429,{}),(200,{'items':'bad'}),(200,{'items':[{'id':'../bad','volumeInfo':{'title':'Bad'}}]})]:
            def handler(request):
                return httpx.Response(200,json={'access_token':'token'}) if request.url==google.TOKEN_URL else httpx.Response(status,json=payload)
            with self.assertRaises(google.GoogleBooksError):self.fetch(handler)

    def test_google_reuses_manual_and_preserves_existing_privacy(self):
        self.client.post('/me/books/import',data={'text':'Shared book\tAuthor','status':'want'})
        row={'title':'Shared book','author':'Author','provider_id':'google_shared','status':'read'}
        with patch.object(google,'read_library',return_value=([row],False)):
            q=self.authorize(); self.client.get('/me/google-books/callback',params={'state':q['state'][0],'code':'c'})
        with Session(engine) as s:
            self.assertEqual(len(s.exec(select(Work)).all()),1)
            e=s.exec(select(CollectionEntry)).one(); self.assertEqual(e.status,'want'); self.assertTrue(e.pending_review)

    def test_partial_remote_failure_does_not_import_or_store_token(self):
        def handler(request):
            if request.url==google.TOKEN_URL:return httpx.Response(200,json={'access_token':'MEMORY_ONLY_TOKEN'})
            if request.url.path.endswith('/4/volumes'):
                return httpx.Response(200,json={'totalItems':1,'items':[volume('first')]})
            return httpx.Response(429,json={'error':'rate limited'})
        with patch.object(google.httpx,'AsyncClient',side_effect=lambda **kw:REAL_CLIENT(transport=httpx.MockTransport(handler),**kw)):
            q=self.authorize(); r=self.client.get('/me/google-books/callback',params={'state':q['state'][0],'code':'c'})
        self.assertNotIn('MEMORY_ONLY_TOKEN',r.headers.get('set-cookie',''))
        with Session(engine) as s:
            self.assertEqual(len(s.exec(select(Work)).all()),0)
            self.assertEqual(len(s.exec(select(CollectionEntry)).all()),0)

    def test_api_cap_and_default_shelves(self):
        shelves=[]
        def handler(request):
            if request.url==google.TOKEN_URL:return httpx.Response(200,json={'access_token':'token'})
            shelves.append(request.url.path.split('/')[-2])
            return httpx.Response(200,json={'totalItems':100,'items':[volume('a'),volume('b'),volume('c')]})
        with patch.object(google,'LIMIT',3):
            rows,truncated=self.fetch(handler); self.assertEqual(len(rows),3); self.assertTrue(truncated)
        self.assertEqual(shelves,['4'])

if __name__=='__main__': unittest.main()
