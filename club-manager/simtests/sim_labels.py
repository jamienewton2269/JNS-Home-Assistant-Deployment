"""Officer-authenticated dated QR labels: simulation database ONLY."""
from contextlib import closing
from urllib.parse import quote
import hashlib,secrets,re,subprocess
from sim_workflow import session_token
def dbquery(factory,statement,args):
 with closing(factory()) as conn:
  with conn:
   with conn.cursor() as cur:
    cur.execute(statement,args)
    return cur.fetchone()[0]
def issue(factory,cookie,registration):
 if not isinstance(registration,str) or not re.fullmatch(r'BSC-[TR]-[A-F0-9]{10}',registration):
  raise ValueError('Invalid registration')
 token=secrets.token_urlsafe(24)
 digest=hashlib.sha256(token.encode()).digest()
 result=dbquery(factory,'SELECT simtest.issue_scan_label(%s,%s,%s::bytea)',(session_token(cookie),registration,digest))
 return {'registration':registration,'expires':str(result['expires']),'scan_url':'/sim/scan?t='+quote(token)}
def lookup(factory,cookie,token):
 if not isinstance(token,str) or not re.fullmatch('[A-Za-z0-9_-]{32,64}',token):
  raise ValueError('Invalid scan code')
 return dbquery(factory,'SELECT simtest.lookup_scan_label(%s,%s::bytea)',(session_token(cookie),hashlib.sha256(token.encode()).digest()))
def png(url):
 if not url.startswith('https://club-manager-dev.home.arpa:8443/sim/scan?t=') or len(url)>270:
  raise ValueError('Invalid QR destination')
 return subprocess.run(['/usr/bin/qrencode','-o','-','-t','PNG','-s','5','-m','3',url],check=True,capture_output=True,timeout=4).stdout
