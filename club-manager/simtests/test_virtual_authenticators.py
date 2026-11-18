"""Off-line cryptographic WebAuthn test: two virtual devices, no officer/session DB grants.

Run with /opt/jns-club-beta/venv/bin/python -m unittest -v
The synthetic approval in MemoryStore is intentionally confined to this process.
"""
import base64
import hashlib
import json
import os
import sys
import unittest
from dataclasses import dataclass
from uuid import uuid4
from pathlib import Path

sys.path[:0] = ["/opt/jns-club-beta/auth"]
import cbor2
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import hashes
from webauthn import base64url_to_bytes
from webauthn_flow import WebAuthnFlow, Credential

RP = "club-manager-dev.home.arpa"
ORIGIN = "https://" + RP

def b64(b):
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode("ascii")

class MemoryStore:
    def __init__(self):
        self.active = set()
        self.approved = set()
        self.keys = {}
        self.challenges = {}
        self.used = set()
    def officer_active(self, account):
        return account in self.active
    def enrolment_approved(self, account):
        return account in self.approved
    def credentials_for(self, account):
        return list(self.keys.get(account,{}).values())
    def save_challenge(self, account, purpose, digest, challenge):
        assert hashlib.sha256(challenge).digest() == digest
        ident = uuid4()
        self.challenges[ident] = (account,purpose,challenge)
        return ident
    def claim_challenge(self, ident, account, purpose):
        value = self.challenges.pop(ident,None)
        return value[2] if value and value[:2] == (account,purpose) else None
    def add_credential(self, account, credential):
        if account not in self.approved: raise PermissionError("not approved")
        self.keys.setdefault(account,{})[credential.id] = credential
    def commit_counter(self, account, cid, count):
        existing = self.keys.get(account,{}).get(cid)
        if existing is None or (existing.sign_count > 0 and count <= existing.sign_count): return False
        self.keys[account][cid] = Credential(cid,existing.public_key,count)
        return True

class VirtualDevice:
    def __init__(self):
        self.key=ec.generate_private_key(ec.SECP256R1())
        self.id=os.urandom(32)
        self.count=0
        pub=self.key.public_key().public_numbers()
        self.cose=cbor2.dumps({1:2,3:-7,-1:1,-2:pub.x.to_bytes(32,'big'),-3:pub.y.to_bytes(32,'big')})
    def client(self,typ,challenge,origin=ORIGIN):
        return json.dumps({"type":typ,"challenge":challenge,"origin":origin,"crossOrigin":False},separators=(',',':')).encode()
    def register(self,options,origin=ORIGIN):
        client=self.client("webauthn.create",options["challenge"],origin)
        data=hashlib.sha256(RP.encode()).digest()+b"\x45"+(0).to_bytes(4,"big")+bytes(16)+len(self.id).to_bytes(2,"big")+self.id+self.cose
        response={"id":b64(self.id),"rawId":b64(self.id),"type":"public-key",
          "response":{"clientDataJSON":b64(client),"attestationObject":b64(cbor2.dumps({"fmt":"none","authData":data,"attStmt":{}}))},
          "clientExtensionResults":{}}
        return response
    def authenticate(self,options,origin=ORIGIN):
        self.count+=1
        client=self.client("webauthn.get",options["challenge"],origin)
        data=hashlib.sha256(RP.encode()).digest()+b"\x05"+self.count.to_bytes(4,"big")
        signature=self.key.sign(data+hashlib.sha256(client).digest(),ec.ECDSA(hashes.SHA256()))
        return {"id":b64(self.id),"rawId":b64(self.id),"type":"public-key",
            "response":{"clientDataJSON":b64(client),"authenticatorData":b64(data),"signature":b64(signature),"userHandle":None},
            "clientExtensionResults":{}}

class Simulation(unittest.TestCase):
    def setUp(self):
        self.store=MemoryStore()
        self.flow=WebAuthnFlow(RP,ORIGIN,self.store)
        self.accounts=[uuid4(),uuid4()]
        self.devices=[VirtualDevice(),VirtualDevice()]
        self.store.active.update(self.accounts)
        self.store.approved.update(self.accounts) # mock fixture ONLY; not database approval
    def options(self,json_options):
        return json.loads(json_options)
    def enrol(self,index):
        account=self.accounts[index]
        cid,raw=self.flow.begin_enrolment(account,"ITAdmin"+str(index+1),"Simulated IT Admin")
        response=self.devices[index].register(self.options(raw))
        cred=self.flow.finish_enrolment(account,cid,response)
        self.assertEqual(cred.id,self.devices[index].id)
    def test_two_independent_software_keys_and_signed_login(self):
        for index in (0,1):
            self.enrol(index)
            account=self.accounts[index]
            challenge,raw=self.flow.begin_login(account)
            result=self.devices[index].authenticate(self.options(raw))
            self.assertEqual(self.flow.finish_login(account,challenge,result),account)
            self.assertEqual(self.store.credentials_for(account)[0].sign_count,1)
    def test_challenge_replay_rejected(self):
        self.enrol(0)
        cid,raw=self.flow.begin_login(self.accounts[0])
        assertion=self.devices[0].authenticate(self.options(raw))
        self.flow.finish_login(self.accounts[0],cid,assertion)
        with self.assertRaises(PermissionError):
            self.flow.finish_login(self.accounts[0],cid,assertion)
    def test_wrong_origin_rejected(self):
        self.enrol(0)
        cid,raw=self.flow.begin_login(self.accounts[0])
        assertion=self.devices[0].authenticate(self.options(raw),origin="https://other.invalid")
        with self.assertRaises(Exception):
            self.flow.finish_login(self.accounts[0],cid,assertion)
    def test_wrong_key_rejected(self):
        self.enrol(0)
        cid,raw=self.flow.begin_login(self.accounts[0])
        assertion=self.devices[1].authenticate(self.options(raw))
        with self.assertRaises(PermissionError):
            self.flow.finish_login(self.accounts[0],cid,assertion)
    def test_unapproved_enrolment_rejected(self):
        self.store.approved.remove(self.accounts[0])
        with self.assertRaises(PermissionError):
            self.flow.begin_enrolment(self.accounts[0],"ITAdmin1","Synthetic")

if __name__=="__main__":
    unittest.main()
