"""Fictional Joomla identity boundary: OFFLINE stdin only, no listening port."""
import sys,json,base64,secrets,uuid,datetime,hashlib
from pathlib import Path
from cryptography.hazmat.primitives import serialization
from cryptography.exceptions import InvalidSignature
import psycopg2
from psycopg2 import Binary
PUBLIC='/opt/jns-club-beta/simtests/fictional-issuer-public.pem'
ISSUER='joomla-fictional-test-only'
AUDIENCE='club-manager-simulation'
MEMBERS={'a1000000-0000-4000-8000-000000000001','a1000000-0000-4000-8000-000000000002'}
def accept(message):
 if not (isinstance(message,dict) and set(message)=={'payload','signature'}):
  raise ValueError('invalid_or_replayed_assertion')
 p=message['payload']
 if not (isinstance(p,dict) and set(p)=={'iss','aud','sub','jti','iat','exp'}):
  raise ValueError('invalid_or_replayed_assertion')
 if not (p['iss']==ISSUER and p['aud']==AUDIENCE):
  raise ValueError('invalid_or_replayed_assertion')
 if not (p['sub'] in MEMBERS):
  raise ValueError('invalid_or_replayed_assertion')
 ident=str(uuid.UUID(p['jti']))
 if not (ident==p['jti']):
  raise ValueError('invalid_or_replayed_assertion')
 if not (type(p['iat']) is int and type(p['exp']) is int):
  raise ValueError('invalid_or_replayed_assertion')
 now=int(datetime.datetime.now(datetime.timezone.utc).timestamp())
 if not (abs(now-p['iat'])<=30 and now<p['exp']<=now+120 and p['exp']>p['iat']):
  raise ValueError('invalid_or_replayed_assertion')
 if not (isinstance(message['signature'],str) and len(message['signature'])==128):
  raise ValueError('invalid_or_replayed_assertion')
 signed=json.dumps(p,separators=(',',':'),sort_keys=True,ensure_ascii=True).encode()
 public=serialization.load_pem_public_key(Path(PUBLIC).read_bytes())
 public.verify(bytes.fromhex(message['signature']),signed)
 token=secrets.token_urlsafe(48)
 digest=hashlib.sha256(token.encode()).digest()
 with psycopg2.connect('dbname=club_manager_simtest user=clubbridge') as conn:
  with conn.cursor() as c:
   c.execute('select simtest.issue_verified_synthetic_member_session(%s,%s,%s,%s)',
    (ident,p['sub'],Binary(digest),datetime.datetime.fromtimestamp(p['exp'],datetime.timezone.utc)))
   if not (c.fetchone()[0] is True):
    raise ValueError('invalid_or_replayed_assertion')
 return {'accepted':True,'session_token':token,'member_id':p['sub']}
def main():
 try:
  message=json.loads(sys.stdin.buffer.read(4096))
  result=accept(message)
  print(json.dumps(result))
 except Exception:
  print(json.dumps({'accepted':False,'error':'invalid_or_replayed_assertion'}))
  return 1
 return 0

if __name__ == '__main__':
 sys.exit(main())
