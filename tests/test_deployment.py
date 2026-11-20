"""Validate deployment entrypoint and HTTPS cookie behavior with synthetic data."""
import os
from pathlib import Path
import unittest
from datetime import date
from scripts.serve import command

ROOT = Path(__file__).resolve().parents[1]
os.environ.update(DATABASE_URL='sqlite:///'+str(ROOT/'tests/test_deployment.db').replace('\\','/'),
                  BACKGROUND_JOBS='false', SESSION_HTTPS_ONLY='true', SECRET_KEY='synthetic-deployment-test-secret-32-characters')
from fastapi.testclient import TestClient
from sqlmodel import SQLModel, Session
from app.main import app
from app.db import engine
from app.models import User
from app.auth import hash_password

class DeploymentTests(unittest.TestCase):
    def test_weak_secret_rejected(self):
        for secret in ('','dev-secret','change-me','x'*31):
            with self.assertRaises(ValueError):command({'SECRET_KEY':secret})

    def test_port_validation(self):
        for port in ('0','65536','http','-1'):
            with self.assertRaises(ValueError):command({'SECRET_KEY':'x'*32,'PORT':port})

    def test_single_worker_port_and_oauth_log_privacy(self):
        args=command({'SECRET_KEY':'x'*32,'PORT':'8797'})
        self.assertEqual(args[args.index('--port')+1],'8797')
        self.assertEqual(args[args.index('--workers')+1],'1')
        self.assertIn('--no-access-log',args);self.assertNotIn('x'*32,' '.join(args))

    def test_https_login_and_health(self):
        SQLModel.metadata.drop_all(engine);SQLModel.metadata.create_all(engine)
        with Session(engine) as s:
            s.add(User(username='deploy_test',display_name='Test',birth_date=date(2000,1,1),password_hash=hash_password('test-only-123')));s.commit()
        with TestClient(app,base_url='https://testserver',follow_redirects=False) as client:
            self.assertEqual(client.get('/health').json(),{'status':'ok'})
            response=client.post('/login',data={'username':'deploy_test','password':'test-only-123'})
            self.assertEqual(response.status_code,303)
            cookie=response.headers['set-cookie'].lower()
            self.assertIn('secure',cookie);self.assertIn('httponly',cookie);self.assertIn('samesite=lax',cookie)
            self.assertEqual(client.get('/me/collection').status_code,200)

if __name__=='__main__':unittest.main()
