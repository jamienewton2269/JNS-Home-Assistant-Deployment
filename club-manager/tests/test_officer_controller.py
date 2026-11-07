"""Mocked-integration checks. Real authenticator integration remains a beta gate."""
import base64
import importlib.util
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from uuid import uuid4

p = Path(__file__).resolve().parents[1] / "beta" / "officer_controller.py"
spec = importlib.util.spec_from_file_location("club_beta_controller", p)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

class Cursor:
    def __init__(self, db): self.db=db
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def execute(self, sql, args):
        self.db.calls.append((sql,args))
    def fetchone(self): return ("synthetic-session-id",)
class DB:
    def __init__(self): self.calls=[]; self.closed=False
    def __enter__(self): return self
    def __exit__(self,*args): return False
    def cursor(self): return Cursor(self)
    def close(self): self.closed=True
class Flow:
    def __init__(self): self.fail=False
    def begin_login(self, officer): return ("challenge-id","options-json")
    def finish_login(self, officer, challenge, response):
        if self.fail: raise PermissionError("WebAuthn signature rejected")
        return officer
class Read:
    def __init__(self): self.calls=[]
    def get(self,route,token):
        self.calls.append((route,token))
        return {"synthetic":True}

class Tests(TestCase):
    def setUp(self):
        self.officer=uuid4()
        self.flow=Flow()
        self.read=Read()
        self.db=DB()
        self.controller=mod.OfficerController(self.flow, lambda:self.db,self.read)
        self.claimed_id=base64.urlsafe_b64encode(b"synthetic-key-credential-id").rstrip(b"=").decode()
    def test_good_assertion_calls_server_side_session_broker(self):
        cid,opts=self.controller.begin_passkey(self.officer)
        self.assertEqual(cid,"challenge-id")
        c=self.controller.complete_passkey(self.officer,cid,{"id":self.claimed_id})
        self.assertIn("__Host-club_session=",c)
        for required in ("Secure","HttpOnly","SameSite=Strict","Path=/","Max-Age=900"):
            self.assertIn(required.lower(),c.lower())
        self.assertEqual(len(self.db.calls),1)
        sql,args=self.db.calls[0]
        self.assertEqual(sql,"SELECT club.complete_verified_webauthn_login(%s,%s,%s)")
        self.assertEqual(args[0],self.officer)
        self.assertEqual(args[1],b"synthetic-key-credential-id")
        self.assertEqual(len(args[2]),32)
        self.assertTrue(self.db.closed)
    def test_failed_crypto_never_creates_session(self):
        self.flow.fail=True
        with self.assertRaises(PermissionError):
            self.controller.complete_passkey(self.officer,"challenge-id",{"id":self.claimed_id})
        self.assertEqual(self.db.calls,[])
    def test_read_requires_valid_cookie(self):
        with self.assertRaises(PermissionError):
            self.controller.read("/api/v1/dashboard","")
        with self.assertRaises(PermissionError):
            self.controller.read("/api/v1/dashboard","other=x")
        fake_cookie="__Host-club_session="+"a"*65
        self.assertEqual(self.controller.read("/api/v1/dashboard",fake_cookie),{"synthetic":True})
        self.assertEqual(self.read.calls,[("/api/v1/dashboard","a"*65)])
    def test_cookie_clear(self):
        c=self.controller.clear_cookie().lower()
        for v in ("max-age=0","httponly","secure","samesite=strict"):
            self.assertIn(v,c)
