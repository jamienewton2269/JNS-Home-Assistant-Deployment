import base64
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch
from uuid import uuid4

module_path = Path(__file__).resolve().parents[1] / "auth" / "webauthn_flow.py"
spec = importlib.util.spec_from_file_location("club_webauthn_flow", module_path)
import sys
flow_module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = flow_module
spec.loader.exec_module(flow_module)

def b64(b):
    return base64.urlsafe_b64encode(b).decode().rstrip("=")

class SyntheticStore:
    def __init__(self):
        self.active=True
        self.approved=False
        self.creds=[]
        self.challenges={}
        self.counter_calls=[]
    def enrolment_approved(self, account):
        return self.approved and self.active
    def officer_active(self, account):
        return self.active
    def credentials_for(self, account):
        return list(self.creds)
    def save_challenge(self, account, purpose, digest, challenge):
        import hashlib
        assert hashlib.sha256(challenge).digest()==digest
        key=uuid4()
        self.challenges[key]=(account,purpose,challenge)
        return key
    def claim_challenge(self, key, account, purpose):
        item=self.challenges.pop(key,None)
        if item is None or item[0:2] != (account,purpose):
            return None
        return item[2]
    def add_credential(self, account, cred):
        if any(c.id==cred.id for c in self.creds):
            raise ValueError("Duplicate credential")
        self.creds.append(cred)
    def commit_counter(self, account, credential_id, count):
        self.counter_calls.append((account,credential_id,count))
        for i,c in enumerate(self.creds):
            if c.id==credential_id and self.active and (count>c.sign_count or count==c.sign_count==0):
                self.creds[i]=flow_module.Credential(c.id,c.public_key,count)
                return True
        return False

class WebAuthnFlowTests(TestCase):
    def setUp(self):
        self.store=SyntheticStore()
        self.account=uuid4()
        self.flow=flow_module.WebAuthnFlow("club.example.invalid","https://club.example.invalid",self.store)

    def test_https_origin_is_mandatory(self):
        for origin in ("http://club.example.invalid","https://other.example.invalid","https://club.example.invalid/path"):
            with self.assertRaises(ValueError):
                flow_module.WebAuthnFlow("club.example.invalid",origin,self.store)

    def test_registration_requires_independent_enrolment_approval(self):
        with self.assertRaises(PermissionError):
            self.flow.begin_enrolment(self.account,"synthetic@example.invalid","Synthetic Officer")
        self.assertFalse(self.store.challenges)

    def test_registration_verifies_challenge_origin_rp_and_uv(self):
        self.store.approved=True
        cid, options=self.flow.begin_enrolment(self.account,"synthetic@example.invalid","Synthetic Officer")
        self.assertTrue(json.loads(options)["challenge"])
        mock_result=SimpleNamespace(credential_id=b"test-credential-id-012345",credential_public_key=b"public-key-test-only",sign_count=0)
        with patch.object(flow_module,"verify_registration_response",return_value=mock_result) as verify:
            result=self.flow.finish_enrolment(self.account,cid,{"id":"placeholder"})
            self.assertEqual(result.id,mock_result.credential_id)
            self.assertEqual(verify.call_args.kwargs["expected_origin"],"https://club.example.invalid")
            self.assertEqual(verify.call_args.kwargs["expected_rp_id"],"club.example.invalid")
            self.assertTrue(verify.call_args.kwargs["require_user_verification"])
            with self.assertRaises(PermissionError):
                self.flow.finish_enrolment(self.account,cid,{"id":"placeholder"})
            self.assertEqual(verify.call_count,1)

    def test_login_is_owner_bound_and_requires_verified_counter(self):
        credential=flow_module.Credential(b"test-credential-id-012345",b"public-key-test-only",3)
        self.store.creds.append(credential)
        cid,options=self.flow.begin_login(self.account)
        self.assertTrue(json.loads(options)["challenge"])
        result=SimpleNamespace(new_sign_count=4)
        with patch.object(flow_module,"verify_authentication_response",return_value=result) as verify:
            account=self.flow.finish_login(self.account,cid,{"id":b64(credential.id)})
            self.assertEqual(account,self.account)
            self.assertEqual(self.store.creds[0].sign_count,4)
            self.assertEqual(verify.call_args.kwargs["expected_origin"],"https://club.example.invalid")
            self.assertTrue(verify.call_args.kwargs["require_user_verification"])
            with self.assertRaises(PermissionError):
                self.flow.finish_login(self.account,cid,{"id":b64(credential.id)})
            self.assertEqual(verify.call_count,1)

    def test_invalid_claimed_key_never_calls_signature_verifier(self):
        self.store.creds.append(flow_module.Credential(b"registered-key-0001",b"key",0))
        cid,_=self.flow.begin_login(self.account)
        with patch.object(flow_module,"verify_authentication_response") as verify:
            with self.assertRaises(PermissionError):
                self.flow.finish_login(self.account,cid,{"id":b64(b"unregistered-key")})
            verify.assert_not_called()

    def test_suspended_officer_cannot_begin_or_complete_login(self):
        self.store.creds.append(flow_module.Credential(b"registered-key-0001",b"key",0))
        cid,_=self.flow.begin_login(self.account)
        self.store.active=False
        with self.assertRaises(PermissionError):
            self.flow.finish_login(self.account,cid,{"id":b64(b"registered-key-0001")})
        with self.assertRaises(PermissionError):
            self.flow.begin_login(self.account)

    def test_invalid_counter_never_emits_officer_identity(self):
        credential=flow_module.Credential(b"registered-key-0001",b"key",9)
        self.store.creds.append(credential)
        cid,_=self.flow.begin_login(self.account)
        with patch.object(flow_module,"verify_authentication_response",return_value=SimpleNamespace(new_sign_count=5)):
            with self.assertRaises(PermissionError):
                self.flow.finish_login(self.account,cid,{"id":b64(credential.id)})
