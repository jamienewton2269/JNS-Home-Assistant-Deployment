"""Private beta HTTP negative tests. No real officer or network exposure."""
import http.client
import importlib.util
from pathlib import Path
from threading import Thread
from http.server import ThreadingHTTPServer
from unittest import TestCase
from uuid import uuid4

import sys
p=Path(__file__).resolve().parents[1] / 'beta' / 'server.py'
spec=importlib.util.spec_from_file_location('club_beta_http',p)
server=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=server
spec.loader.exec_module(server)

class FakeController:
    def begin_passkey(self, account):
        return uuid4(), '{"challenge":"dGVzdC1jaGFsbGVuZ2U"}'
    def complete_passkey(self, account, cid, assertion):
        raise PermissionError('No valid synthetic credential')
    def read(self, path, cookie):
        if cookie != '__Host-club_session=valid_fake_test_token':
            raise PermissionError('No session')
        return {'screen':path,'synthetic':True}
    def logout(self,cookie):
        if cookie != '__Host-club_session=valid_fake_test_token':
            raise PermissionError('No session')
        return '__Host-club_session=""; Max-Age=0; Path=/; Secure; HttpOnly; SameSite=Strict'

class Tests(TestCase):
    @classmethod
    def setUpClass(cls):
        server.Handler.expected_host='club-beta.example.invalid'
        server.Handler.expected_origin='https://club-beta.example.invalid'
        server.Handler.controller=FakeController()
        cls.http=ThreadingHTTPServer(('127.0.0.1',0),server.Handler)
        cls.port=cls.http.server_port
        cls.thread=Thread(target=cls.http.serve_forever,daemon=True)
        cls.thread.start()
    @classmethod
    def tearDownClass(cls):
        cls.http.shutdown()
        cls.http.server_close()
        cls.thread.join(timeout=2)

    def request(self, method,path,body=None,headers=None):
        c=http.client.HTTPConnection('127.0.0.1',self.port,timeout=4)
        h={'Host':'club-beta.example.invalid'}
        h.update(headers or {})
        c.request(method,path,body,h)
        r=c.getresponse()
        result=(r.status,dict(r.getheaders()),r.read())
        c.close()
        return result

    def test_health_and_host_isolation(self):
        self.assertEqual(self.request('GET','/healthz')[0],200)
        self.assertEqual(self.request('GET','/login',headers={'Host':'hostile.example'})[0],421)
        self.assertEqual(self.request('GET','/login')[0],200)
        self.assertIn('script-src',self.request('GET','/login')[1]['Content-Security-Policy'])

    def test_anonymous_sensitive_pages_not_available(self):
        self.assertEqual(self.request('GET','/beta')[0],303)
        self.assertEqual(self.request('GET','/api/v1/members')[0],401)
        self.assertEqual(self.request('GET','/api/v1/unknown')[0],404)

    def test_browser_origin_required(self):
        import json
        body=json.dumps({'officer_id':str(uuid4())})
        h={'Content-Type':'application/json'}
        self.assertEqual(self.request('POST','/auth/webauthn/begin',body,h)[0],403)
        h['Origin']='https://club-beta.example.invalid'
        self.assertEqual(self.request('POST','/auth/webauthn/begin',body,h)[0],200)
        self.assertEqual(self.request('POST','/auth/invalid',body,h)[0],404)

    def test_privileged_methods_never_allowed(self):
        self.assertEqual(self.request('PUT','/api/v1/members')[0],405)
        self.assertEqual(self.request('DELETE','/api/v1/members')[0],405)
        self.assertEqual(self.request('PATCH','/api/v1/members')[0],405)

    def test_authorized_read_has_no_store(self):
        h={'Cookie':'__Host-club_session=valid_fake_test_token'}
        status,headers,body=self.request('GET','/api/v1/members',headers=h)
        self.assertEqual(status,200)
        self.assertEqual(headers['Cache-Control'],'no-store')
        self.assertIn(b'"synthetic": true',body)
        self.assertEqual(self.request('GET','/beta',headers=h)[0],200)

    def test_invalid_assertion_does_not_issue_cookie(self):
        import json
        body=json.dumps({'officer_id':str(uuid4()),'challenge_id':str(uuid4()),'response':{}})
        h={'Content-Type':'application/json','Origin':'https://club-beta.example.invalid'}
        status,headers,_=self.request('POST','/auth/webauthn/complete',body,h)
        self.assertEqual(status,403)
        self.assertNotIn('Set-Cookie',headers)

    def test_authentication_rate_limit(self):
        import json
        officer=str(uuid4())
        body=json.dumps({'officer_id':officer})
        headers={'Content-Type':'application/json',
                 'Origin':'https://club-beta.example.invalid'}
        for _ in range(8):
            self.assertEqual(self.request('POST','/auth/webauthn/begin',body,headers)[0],200)
        self.assertEqual(self.request('POST','/auth/webauthn/begin',body,headers)[0],429)
