"""HTTPS-to-Postgres simulation, with real WebAuthn crypto.
NEVER point at live club_manager. Simulated approvals are restricted to
club_manager_simtest; they do not constitute independent human authorisation.
"""
import hashlib
import os
import pwd
import http.client
import json
import socket
import ssl
import sys
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from uuid import UUID
sys.path[:0] = ['/opt/jns-club-beta/beta','/opt/jns-club-beta/auth','/opt/jns-club-beta/simtests']
from test_virtual_authenticators import VirtualDevice
from server import Handler, validate_origin
from officer_controller import OfficerController
from read_api import ReadOnlyBetaAPI
from pg_webauthn_store import PostgreSQLWebAuthnStore
from webauthn_flow import WebAuthnFlow
import psycopg2
from psycopg2.extras import register_uuid
register_uuid()

RP='club-manager-dev.home.arpa'
ORIGIN='https://'+RP
TEST_DB='club_manager_simtest'
ids={
 'ITAdmin1':UUID('d520f340-3954-4420-bca9-d0345690ab4b'),
 'ITAdmin2':UUID('3c139e41-8084-45d1-a133-e891884b534f')
}
def connect():
    return psycopg2.connect('dbname='+TEST_DB+' user=clubbeta')
assert TEST_DB != 'club_manager'
class TestHandler(Handler):
    controller=OfficerController(WebAuthnFlow(RP,ORIGIN,PostgreSQLWebAuthnStore(connect)),connect,ReadOnlyBetaAPI(connect))
    expected_host=RP
    expected_origin=ORIGIN

server=ThreadingHTTPServer(('127.0.0.1',0),TestHandler)
tls=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
tls.load_cert_chain('/etc/jns-club-beta/tls/club-beta.crt','/etc/jns-club-beta/tls/club-beta.key')
clienttls=ssl.create_default_context(cafile='/etc/jns-club-beta/tls/club-beta-ca.crt')
# Root reads the existing TLS key, then permanently drops privileges.
identity=pwd.getpwnam('clubbeta')
os.setgroups([])
os.setgid(identity.pw_gid)
os.setuid(identity.pw_uid)
with connect() as connection:
    with connection.cursor() as cursor:
        cursor.execute("SELECT current_database()")
        assert cursor.fetchone()[0] == TEST_DB
server.socket=tls.wrap_socket(server.socket,server_side=True)
port=server.server_address[1]
thread=threading.Thread(target=server.serve_forever,daemon=True)
thread.start()

class LocalHTTPS(http.client.HTTPSConnection):
    def connect(self):
        raw=socket.create_connection(('127.0.0.1',port),timeout=8)
        self.sock=self._context.wrap_socket(raw,server_hostname=RP)

def req(path,method='GET',data=None,cookie=None,origin=None):
    h={'Host':RP,'Accept':'application/json'}
    if method=='POST':
        h['Origin']=ORIGIN if origin is None else origin
        h['Content-Type']='application/json'
    if cookie:h['Cookie']=cookie
    c=LocalHTTPS(RP,port,context=clienttls,timeout=8)
    c.request(method,path,body=json.dumps(data) if data is not None else None,headers=h)
    r=c.getresponse()
    body=r.read()
    result=r.status,dict(r.getheaders()),json.loads(body) if body and r.getheader('Content-Type','').startswith('application/json') else body
    c.close()
    return result

def require_status(case,expected,actual):
    assert actual==expected, f'{case}: expected {expected}, got {actual}'
    print('PASS',case,actual,flush=True)

try:
    require_status('TLS login',200,req('/login')[0])
    require_status('unauth API',401,req('/api/v1/members')[0])
    require_status('unapproved other UUID',403,req('/auth/webauthn/enrol/begin','POST',{'officer_id':str(UUID(int=0)),'name':'Unknown','display_name':'Unknown'})[0])
    devices={}
    sessions={}
    for label,account in ids.items():
        dev=VirtualDevice()
        devices[label]=dev
        status,_,body=req('/auth/webauthn/enrol/begin','POST',{'officer_id':str(account),'name':label,'display_name':label+' Simulated'})
        require_status(label+' enrol-begin',200,status)
        registration=dev.register(body['options'])
        status,_,answer=req('/auth/webauthn/enrol/complete','POST',{'officer_id':str(account),'challenge_id':body['challenge_id'],'response':registration})
        require_status(label+' enrol-complete',200,status)
        assert answer['enrolled'] is True
        status,_,body=req('/auth/webauthn/begin','POST',{'officer_id':str(account)})
        require_status(label+' login-begin',200,status)
        assertion=dev.authenticate(body['options'])
        status,headers,answer=req('/auth/webauthn/complete','POST',{'officer_id':str(account),'challenge_id':body['challenge_id'],'response':assertion})
        require_status(label+' signed-login',200,status)
        cookie=headers.get('Set-Cookie','').split(';',1)[0]
        assert cookie.startswith('__Host-club_session=')
        assert 'Secure' in headers.get('Set-Cookie','')
        assert 'HttpOnly' in headers.get('Set-Cookie','')
        sessions[label]=cookie
        require_status(label+' consumed challenge replay',403,req('/auth/webauthn/complete','POST',{'officer_id':str(account),'challenge_id':body['challenge_id'],'response':assertion})[0])
    for section in ('dashboard','members','moorings','clubhouse','renewals','committee','security'):
        status,_,body=req('/api/v1/'+section,cookie=sessions['ITAdmin1'])
        require_status('ITAdmin1 '+section,200,status)
        assert isinstance(body,(dict,list)),section
        if section=='members':
            assert any('Sample Member Alpha'==row.get('display_name') for row in body)
            print('PASS synthetic member propagated through HTTP to PostgreSQL',flush=True)
    require_status('ITAdmin2 members allowed',200,req('/api/v1/members',cookie=sessions['ITAdmin2'])[0])
    require_status('ITAdmin2 security prohibited',403,req('/api/v1/security',cookie=sessions['ITAdmin2'])[0])
    require_status('ITAdmin2 committee prohibited',403,req('/api/v1/committee',cookie=sessions['ITAdmin2'])[0])
    require_status('ITAdmin1 logout',200,req('/auth/logout','POST',{},cookie=sessions['ITAdmin1'])[0])
    require_status('ITAdmin1 revoked cookie',403,req('/api/v1/members',cookie=sessions['ITAdmin1'])[0])
    require_status('ITAdmin2 logout',200,req('/auth/logout','POST',{},cookie=sessions['ITAdmin2'])[0])
    require_status('ITAdmin2 revoked cookie',403,req('/api/v1/members',cookie=sessions['ITAdmin2'])[0])
    print('RESULT: ALL HTTPS+POSTGRES SIMULATION CHECKS PASSED',flush=True)
finally:
    server.shutdown()
    server.server_close()
