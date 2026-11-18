"""Clearly labelled synthetic-only Club Manager operator walkthrough.
Never import into production beta server. Separate process and database.
"""
import os,sys,json,hmac,hashlib,threading,html
from pathlib import Path
from uuid import UUID
from urllib.parse import urlsplit
from time import monotonic
sys.path[:0]=['/opt/jns-club-beta/auth','/opt/jns-club-beta/beta','/opt/jns-club-beta/simtests']
from http.server import ThreadingHTTPServer
import psycopg2
from psycopg2.extras import register_uuid
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from server import Handler
from officer_controller import OfficerController
from read_api import ReadOnlyBetaAPI
from webauthn_flow import WebAuthnFlow
from pg_webauthn_store import PostgreSQLWebAuthnStore
from test_virtual_authenticators import VirtualDevice
from sim_workflow import execute as workflow_execute
from sim_payments import operate as payment_operate
from sim_treasury import operate as treasury_operate
from sim_finance import operate as finance_operate
from sim_tenders import operate as tenders_operate
from sim_ybm import operation as ybm_operate
from insurance_preflight import preflight as insurance_preflight
from sim_claims import process as claims_process
from sim_labels import png as ybm_qr_png
from contextlib import closing
def committee_reports(factory,cookie):
 from sim_workflow import session_token
 token=session_token(cookie)
 with closing(factory()) as connection:
  with connection:
   with connection.cursor() as cur:
    cur.execute('SELECT simtest.committee_report_history(%s)',(token,))
    return cur.fetchone()[0]
def ybm_insurance_reports(factory,cookie):
 from sim_workflow import session_token
 token=session_token(cookie)
 with closing(factory()) as connection:
  with connection:
   with connection.cursor() as cur:
    cur.execute('SELECT simtest.ybm_insurance_reports(%s)',(token,))
    return cur.fetchone()[0]

register_uuid()
BASE=Path('/var/lib/jns-club-beta-sim')
RP='club-manager-dev.home.arpa'
ORIGIN='https://club-manager-dev.home.arpa:8443'
ACCOUNTS={
 'ITAdmin1': UUID('d520f340-3954-4420-bca9-d0345690ab4b'),
 'ITAdmin2': UUID('3c139e41-8084-45d1-a133-e891884b534f')
}
def db():
 return psycopg2.connect('dbname=club_manager_simtest user=clubbeta')
with db() as c:
 with c.cursor() as q:
  q.execute('select current_database()')
  assert q.fetchone()[0]=='club_manager_simtest'
flow=WebAuthnFlow(RP,ORIGIN,PostgreSQLWebAuthnStore(db))
controller=OfficerController(flow,db,ReadOnlyBetaAPI(db))
lock=threading.Lock()
attempts={}
def software_device(label):
 p=BASE/(label+'.json')
 if not p.exists():
  d=VirtualDevice()
  content={'id':d.id.hex(),'pem':d.key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()).decode()}
  fd=os.open(str(p),os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
  with os.fdopen(fd,'w') as f: json.dump(content,f)
 else:
  content=json.loads(p.read_text())
  d=VirtualDevice.__new__(VirtualDevice)
  d.key=serialization.load_pem_private_key(content['pem'].encode(),password=None)
  d.id=bytes.fromhex(content['id'])
  d.count=0
  pub=d.key.public_key().public_numbers()
  import cbor2
  d.cose=cbor2.dumps({1:2,3:-7,-1:1,-2:pub.x.to_bytes(32,'big'),-3:pub.y.to_bytes(32,'big')})
 return d

class SimHandler(Handler):
 controller=controller
 expected_host=RP+':8443'
 expected_origin=ORIGIN
 def do_GET(self):
  path=urlsplit(self.path).path
  if not self.host_ok():return self.deny(421,'Unknown host')
  if path in ('/','/login','/sim'):
   return self.send_body(200,'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Club Manager | SIMULATION</title><link rel="stylesheet" href="/assets/style.css"></head><body><main><header><span class="brand"><img class="brand-mark" src="/assets/sailing-uk-logo-static.png" alt="" aria-hidden="true"> Club Manager</span><span class="pill">SIMULATION ONLY — SYNTHETIC DATA</span></header><article><h1>Officer interface walkthrough</h1><p>Virtual WebAuthn authenticators on CT101. Not real officer authentication. Staging simulation only; no live membership records.</p><form id="sim-form"><label>Testing officer<select id="officer"><option>ITAdmin1</option><option>ITAdmin2</option></select></label><p>Access restricted to the authorised SAGE test computer.</p><button type="submit">Enter simulated officer interface</button></form><p role="status" id="status"></p><small>Separate simulation database; 15-minute sessions; read-only administration.</small></article></main><script src="/sim.js"></script></body></html>''','text/html')
  if path=='/sim.js':
   return self.send_body(200,'''document.querySelector('#sim-form').addEventListener('submit',async e=>{e.preventDefault();const s=document.querySelector('#status');s.textContent='Verifying virtual passkey…';try{const r=await fetch('/sim/session',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:JSON.stringify({officer:document.querySelector('#officer').value})});if(!r.ok)throw Error('Access denied ('+r.status+')');location.assign(document.querySelector('#officer').value==='ITAdmin2'?'/sim/finance':'/beta')}catch(err){s.textContent='Simulation sign-in failed. Please retry, or contact the test administrator.'}});''','text/javascript')
  if path in ('/sim/committee','/sim/committee.js'):
   name='committee.html' if path=='/sim/committee' else 'committee.js'
   if path=='/sim/committee':
    try:committee_reports(db,self.headers.get('Cookie',''))
    except Exception:
     self.send_response(303);self.send_header('Location','/sim');self.end_headers();return
   return self.send_body(200,(Path(__file__).parent/name).read_text(),
                         'text/html' if name.endswith('.html') else 'text/javascript')
  if path=='/sim/committee/reports':
   try:return self.send_body(200,committee_reports(db,self.headers.get('Cookie','')))
   except PermissionError:return self.deny(401,'Officer authentication required')
   except Exception as exc:
    if getattr(exc,'pgcode',None)=='42501':return self.deny(403,'Committee reporting permission required')
    print('COMMITTEE_REPORT_ERROR',type(exc).__name__,str(exc)[:120],flush=True)
    return self.deny(503,'Committee reports unavailable')
  if path in ('/sim/claims','/sim/claims.js'):
   name='claims.html' if path=='/sim/claims' else 'claims.js'
   if path=='/sim/claims':
    try:claims_process(db,'/sim/claims/state','GET',self.headers.get('Cookie',''))
    except Exception:
     self.send_response(303);self.send_header('Location','/sim');self.end_headers();return
   return self.send_body(200,(Path(__file__).parent/name).read_text(),
       'text/html' if name.endswith('.html') else 'text/javascript')
  if path=='/sim/claims/state':
   try:return self.send_body(200,claims_process(db,path,'GET',self.headers.get('Cookie','')))
   except PermissionError:return self.deny(401,'Officer login required')
   except Exception as exc:
    if getattr(exc,'pgcode',None)=='42501':return self.deny(403,'GC authorisation required')
    return self.deny(503,'Claims register unavailable')
  if path in ('/sim/insurance/check','/sim/insurance/check.js'):
   name='insurance-check.html' if path=='/sim/insurance/check' else 'insurance-check.js'
   if path=='/sim/insurance/check':
    try:ybm_insurance_reports(db,self.headers.get('Cookie',''))
    except Exception:
     self.send_response(303);self.send_header('Location','/sim');self.end_headers();return
   return self.send_body(200,(Path(__file__).parent/name).read_text(),
                         'text/html' if name.endswith('.html') else 'text/javascript')
  if path in ('/sim/insurance','/sim/insurance.js'):
   name='insurance.html' if path=='/sim/insurance' else 'insurance.js'
   if path=='/sim/insurance':
    try:ybm_insurance_reports(db,self.headers.get('Cookie',''))
    except Exception:
     self.send_response(303);self.send_header('Location','/sim');self.end_headers();return
   return self.send_body(200,(Path(__file__).parent/name).read_text(),
                         'text/html' if name.endswith('.html') else 'text/javascript')
  if path=='/sim/insurance/reports':
   try:return self.send_body(200,ybm_insurance_reports(db,self.headers.get('Cookie','')))
   except PermissionError:return self.deny(401,'Officer authentication required')
   except Exception as exc:
    if getattr(exc,'pgcode',None)=='42501':return self.deny(403,'YBM permission required')
    print('INSURANCE_REPORT_ERROR',type(exc).__name__,str(exc)[:120],flush=True)
    return self.deny(503,'Insurance report unavailable')
  if path in ('/sim/ybm','/sim/ybm.js'):
   name='ybm.html' if path=='/sim/ybm' else 'ybm.js'
   if path=='/sim/ybm':
    try:ybm_operate(db,'/sim/ybm/assets','GET',self.headers.get('Cookie',''))
    except Exception:
     self.send_response(303);self.send_header('Location','/sim');self.end_headers();return
   return self.send_body(200,(Path(__file__).parent/name).read_text(),'text/html' if name.endswith('.html') else 'text/javascript')
  if path in ('/sim/ybm/assets','/sim/ybm/history','/sim/ybm/lookup','/sim/ybm/qr.png','/sim/scan'):
   from urllib.parse import parse_qs
   params=parse_qs(urlsplit(self.path).query)
   try:
    if path=='/sim/ybm/assets':return self.send_body(200,ybm_operate(db,path,'GET',self.headers.get('Cookie','')))
    if path=='/sim/ybm/history':
     reg=params.get('registration',[''])[0]
     return self.send_body(200,ybm_operate(db,path,'GET',self.headers.get('Cookie',''),reg))
    token=params.get('t',[''])[0]
    info=ybm_operate(db,'/sim/ybm/lookup','GET',self.headers.get('Cookie',''),token)
    if info is None:return self.deny(404,'Invalid or expired registration code')
    if path=='/sim/ybm/lookup':return self.send_body(200,info)
    if path=='/sim/ybm/qr.png':
     return self.send_body(200,ybm_qr_png(self.expected_origin+'/sim/scan?t='+token),'image/png')
    # QR inspection is never a public owner lookup.
    import html as html_mod
    def safe(v):return html_mod.escape(str(v) if v is not None else 'Unknown')
    inspection=''
    if info.get('asset_type')=='trailer':
     history=ybm_operate(db,'/sim/ybm/history','GET',self.headers.get('Cookie',''),info['registration']).get('history',[])
     inspection=('Last YBM inspection: '+safe(history[0]['inspected_at'])+
       ' — '+safe(history[0]['outcome'])+
       ' — '+safe(history[0]['inspector'])+
       ' — '+safe(history[0]['notes'])) if history else 'No inspection recorded'
    page=('<html lang="en"><head><meta charset="utf-8"><meta name="referrer" content="no-referrer">'
     '<title>Yard asset scan</title><link rel="stylesheet" href="/assets/style.css"></head><body><main><article>'
     '<h1>Authenticated club asset lookup</h1><p>Registration: '+safe(info['registration'])+'</p>'
     '<p>Type: '+safe(info['asset_type'])+' | '+safe(info['description'])+'</p>'
     '<p>Owner: '+safe(info['owner'])+'</p><p>Label: '+safe(info['label_status'])+
     ' (expires '+safe(info['expires'])+')</p><p>Fee status: '+safe(info['billing_status'])+
     '</p><p>'+inspection+'</p><a href="/sim/ybm">YBM inspections</a></article></main></body></html>')
    return self.send_body(200,page,'text/html')
   except PermissionError:
    if path=='/sim/scan':
     return self.send_body(401,'<html><head><meta charset="utf-8"></head><body><p>Authorised club officer sign-in required. Sign in and scan the QR again.</p><a href="/sim">Officer sign-in</a></body></html>','text/html')
    return self.deny(401,'Officer login required')
   except (ValueError,KeyError,TypeError):
    return self.deny(400,'Invalid QR or registration request')
   except Exception as exc:
    if getattr(exc,'pgcode',None)=='42501':return self.deny(403,'YBM permission required')
    print('YBM_SCAN_ERROR',type(exc).__name__,str(exc)[:140],flush=True)
    return self.deny(503,'Yard inspection lookup unavailable')
  if path in ('/sim/tenders','/sim/tenders.js'):
   name='tenders.html' if path=='/sim/tenders' else 'tenders.js'
   if path=='/sim/tenders':
    try:tenders_operate(db,'/sim/tenders/state','GET',self.headers.get('Cookie',''))
    except Exception:
     self.send_response(303);self.send_header('Location','/sim');self.end_headers();return
   return self.send_body(200,(Path(__file__).parent/name).read_text(),'text/html' if name.endswith('.html') else 'text/javascript')
  if path=='/sim/tenders/state':
   try:return self.send_body(200,tenders_operate(db,path,'GET',self.headers.get('Cookie','')))
   except PermissionError:return self.deny(401,'Officer session required')
   except Exception as exc:
    if getattr(exc,'pgcode',None)=='42501':return self.deny(403,'Tender permission denied')
    return self.deny(503,'Tender test data unavailable')
  if path in ('/sim/finance','/sim/finance.js'):
   name='finance.html' if path=='/sim/finance' else 'finance.js'
   if path=='/sim/finance':
    try: finance_operate(db,'/sim/finance/state','GET',self.headers.get('Cookie',''))
    except Exception:
     self.send_response(303);self.send_header('Location','/sim');self.end_headers();return
   return self.send_body(200,(Path(__file__).parent/name).read_text(),'text/html' if name.endswith('.html') else 'text/javascript')
  if path=='/sim/finance/state':
   try:return self.send_body(200,finance_operate(db,path,'GET',self.headers.get('Cookie','')))
   except PermissionError:return self.deny(401,'Officer session required')
   except Exception as exc:
    if getattr(exc,'pgcode',None)=='42501':return self.deny(403,'Finance tariff permission required')
    print('FINANCE_READ_ERROR',type(exc).__name__,str(exc)[:130],flush=True)
    return self.deny(503,'Finance data unavailable')
  if path in ('/sim/treasury','/sim/treasury.js'):
   name='treasury.html' if path=='/sim/treasury' else 'treasury.js'
   if path=='/sim/treasury':
    try: treasury_operate(db,'/sim/treasury/state','GET',self.headers.get('Cookie',''))
    except Exception:
     self.send_response(303);self.send_header('Location','/sim');self.end_headers();return
   return self.send_body(200,(Path(__file__).parent/name).read_text(),'text/html' if name.endswith('.html') else 'text/javascript')
  if path=='/sim/treasury/state':
   try: return self.send_body(200,treasury_operate(db,path,'GET',self.headers.get('Cookie','')))
   except PermissionError:return self.deny(401,'Officer session required')
   except Exception as exc:
    if getattr(exc,'pgcode',None)=='42501':return self.deny(403,'Treasurer permission denied')
    print('TREASURY_STATE_ERROR',type(exc).__name__,str(exc)[:120],flush=True)
    return self.deny(503,'Simulation ledger unavailable')
  if path=='/sim/checkout':
   from urllib.parse import parse_qs
   secret=parse_qs(urlsplit(self.path).query).get('t',[''])[0]
   try: data=treasury_operate(db,'/sim/checkout-preview','GET',payload=secret)
   except Exception:data=None
   if data is None:return self.deny(404,'Checkout link invalid')
   import html as htmlmodule
   label=htmlmodule.escape(data['description'])
   amount=f"{data['amount_pence']/100:.2f}"
   provider=htmlmodule.escape(data['provider'])
   state=htmlmodule.escape(data['status'])
   return self.send_body(200,'''<!doctype html><html lang="en"><head><meta charset="utf-8"><title>SIMULATED checkout</title><link rel="stylesheet" href="/assets/style.css"></head><body><main><article><h1>Simulation only — no real payment</h1><p>Provider: '''+provider+'''</p><p>Fee: '''+label+'''</p><p>Amount: £'''+amount+'''</p><p>Link state: '''+state+'''</p><p>No payment can be made here. Use the officer simulation to record provider events and settlements.</p></article></main></body></html>''','text/html')
  if path in ('/sim/payments','/sim/payments.js'):
   name='payments.html' if path=='/sim/payments' else 'payments.js'
   if path=='/sim/payments':
    try: payment_operate(db,'/sim/payments/state','GET',self.headers.get('Cookie',''))
    except Exception:
     self.send_response(303);self.send_header('Location','/sim');self.end_headers();return
   return self.send_body(200,(Path(__file__).parent/name).read_text(),'text/html' if name.endswith('.html') else 'text/javascript')
  if path=='/sim/payments/state':
   try: return self.send_body(200,payment_operate(db,path,'GET',self.headers.get('Cookie','')))
   except PermissionError: return self.deny(401,'Officer session required')
   except Exception as exc:
    if getattr(exc,'pgcode',None)=='42501':return self.deny(403,'Payment permission required')
    print('SIM_PAYMENT_READ_ERROR',type(exc).__name__,str(exc)[:120],flush=True)
    return self.deny(503,'Simulation payment data unavailable')
  if path in ('/sim/workflow','/sim/workflow.js','/sim/workflow.css'):
   filename={'/sim/workflow':'workflow.html','/sim/workflow.js':'workflow.js','/sim/workflow.css':'workflow.css'}[path]
   mime='text/html' if filename.endswith('.html') else ('text/javascript' if filename.endswith('.js') else 'text/css')
   if path=='/sim/workflow':
    try:
     workflow_execute(db,'/sim/api/state','GET',self.headers.get('Cookie',''))
    except Exception:
     self.send_response(303);self.send_header('Location','/sim');self.end_headers();return
   return self.send_body(200,(Path(__file__).parent/filename).read_text(),mime)
  if path=='/sim/api/state':
   try:
    return self.send_body(200,workflow_execute(db,path,'GET',self.headers.get('Cookie','')))
   except PermissionError:
    return self.deny(401,'Session required')
   except Exception as exc:
    if getattr(exc,'pgcode',None)=='42501':return self.deny(403,'Permission denied')
    return self.deny(503,'Simulation data unavailable')
  if path=='/beta':
   try:self.controller.read('/api/v1/dashboard',self.headers.get('Cookie',''))
   except Exception:
    self.send_response(303);self.send_header('Location','/sim');self.end_headers();return
   from server import HERE
   content=(HERE/'static'/'beta.html').read_text()
   content=content.replace('Private Administration','SIMULATED Administration').replace('<header>','<header><strong style="background:#ffe7a1;color:#3c2600;padding:8px">SIMULATION ONLY — NO LIVE OFFICERS OR DATA</strong>')
   content=content.replace('<nav id="sections"','<p><a href="/sim/workflow">Test member creation and weekly amenity mooring bookings</a> | <a href="/sim/payments">Test fee requests and payment reconciliation</a> | <a href="/sim/treasury">Treasurer testing</a> | <a href="/sim/finance">Finance tariff configuration (ITAdmin2)</a> | <a href="/sim/tenders">Additional tenders</a> | <a href="/sim/ybm">YBM trailer inspections &amp; QR labels</a> | <a href="/sim/insurance">Insurance renewal reports</a> | <a href="/sim/insurance/check">Policy PDF checks</a> | <a href="/sim/claims">GC claims approvals</a> | <a href="/sim/committee">General Committee reports</a></p><nav id="sections"')
   return self.send_body(200,content,'text/html')
  if path in ('/assets/style.css','/assets/browser.js','/assets/sailing-uk-logo-static.png') or path.startswith('/api/'):
   return super().do_GET()
  return self.deny(404,'Unknown simulation route')
 def do_POST(self):
  route=urlsplit(self.path).path
  if route in ('/sim/claims/request','/sim/claims/approve'):
   if not self.host_ok() or self.headers.get('Origin')!=self.expected_origin:
    return self.deny(403,'Origin rejected')
   if self.headers.get('Content-Type','').split(';')[0].strip()!='application/json':
    return self.deny(415,'JSON required')
   try:
    n=int(self.headers.get('Content-Length','0'))
    if not 2<=n<=4096:return self.deny(413,'Request rejected')
    payload=json.loads(self.rfile.read(n).decode('utf-8'))
    result=claims_process(db,route,'POST',self.headers.get('Cookie',''),payload)
    return self.send_body(200,result if isinstance(result,dict) else {'request_id':result})
   except PermissionError:return self.deny(401,'Officer login required')
   except (ValueError,KeyError,TypeError):return self.deny(400,'Invalid claim fields')
   except Exception as exc:
    if getattr(exc,'pgcode',None)=='42501':return self.deny(403,'GC permission required')
    if getattr(exc,'pgcode',None)=='22023':return self.deny(400,str(exc).splitlines()[0][:150])
    print('GC_CLAIM_ERROR',type(exc).__name__,flush=True)
    return self.deny(503,'Claims operation unavailable')
  if route=='/sim/insurance/preflight':
   if not self.host_ok() or self.headers.get('Origin')!=self.expected_origin:
    return self.deny(403,'Origin rejected')
   if self.headers.get('Content-Type','').split(';')[0].strip()!='application/json':
    return self.deny(415,'JSON required')
   try:
    # Require a valid YBM-authorised session before even parsing document bytes.
    ybm_insurance_reports(db,self.headers.get('Cookie',''))
    n=int(self.headers.get('Content-Length','0'))
    if not 2<=n<=720000:return self.deny(413,'Document too large')
    payload=json.loads(self.rfile.read(n).decode('utf-8'))
    return self.send_body(200,insurance_preflight(payload))
   except PermissionError:return self.deny(401,'Officer login required')
   except (ValueError,KeyError,TypeError) as exc:return self.deny(400,str(exc)[:160])
   except Exception as exc:
    if getattr(exc,'pgcode',None)=='42501':return self.deny(403,'YBM permission required')
    print('PDF_PREFLIGHT_FAILURE',type(exc).__name__,flush=True)
    return self.deny(503,'Document preflight unavailable')
  if route in ('/sim/ybm/issue','/sim/ybm/inspect'):
   if not self.host_ok() or self.headers.get('Origin')!=self.expected_origin:
    return self.deny(403,'Origin rejected')
   if self.headers.get('Content-Type','').split(';')[0].strip()!='application/json':
    return self.deny(415,'JSON required')
   try:
    n=int(self.headers.get('Content-Length','0'))
    if not 2<=n<=2048:return self.deny(413,'Request size rejected')
    payload=json.loads(self.rfile.read(n).decode('utf-8'))
    result=ybm_operate(db,route,'POST',self.headers.get('Cookie',''),payload)
    return self.send_body(200,result)
   except PermissionError:return self.deny(401,'Officer login required')
   except (ValueError,KeyError,TypeError):return self.deny(400,'Invalid YBM input')
   except Exception as exc:
    if getattr(exc,'pgcode',None)=='42501':return self.deny(403,'YBM permission required')
    if getattr(exc,'pgcode',None)=='22023':return self.deny(400,str(exc).splitlines()[0][:150])
    print('YBM_WRITE_ERROR',type(exc).__name__,str(exc)[:140],flush=True)
    return self.deny(503,'Inspection operation unavailable')
  if route in ('/sim/tenders/allocate','/sim/tenders/rate','/sim/tenders/invoice'):
   if not self.host_ok() or self.headers.get('Origin')!=self.expected_origin:return self.deny(403,'Origin rejected')
   if self.headers.get('Content-Type','').split(';')[0].strip()!='application/json':return self.deny(415,'JSON required')
   try:
    n=int(self.headers.get('Content-Length','0'))
    if not 2<=n<=2048:return self.deny(413,'Invalid request size')
    result=tenders_operate(db,route,'POST',self.headers.get('Cookie',''),json.loads(self.rfile.read(n).decode()))
    return self.send_body(200,{'saved':True,'result':str(result) if result is not None else None})
   except PermissionError:return self.deny(401,'Session required')
   except (ValueError,KeyError,TypeError):return self.deny(400,'Invalid tender input')
   except Exception as exc:
    code=getattr(exc,'pgcode',None)
    if code=='42501':return self.deny(403,'Tender permission denied')
    if code=='23505':return self.deny(409,'Tender already allocated or charged')
    if code=='22023':return self.deny(400,str(exc).splitlines()[0][:150])
    print('TENDER_TEST_ERROR',type(exc).__name__,str(exc)[:140],flush=True)
    return self.deny(503,'Tender operation unavailable')
  if route in ('/sim/finance/amenity','/sim/finance/membership','/sim/finance/location','/sim/finance/tender'):
   if not self.host_ok() or self.headers.get('Origin')!=self.expected_origin:
    return self.deny(403,'Browser origin rejected')
   if self.headers.get('Content-Type','').split(';')[0].strip()!='application/json':
    return self.deny(415,'JSON required')
   try:
    n=int(self.headers.get('Content-Length','0'))
    if not 2<=n<=2048:return self.deny(413,'Request size rejected')
    data=json.loads(self.rfile.read(n).decode('utf-8'))
    finance_operate(db,route,'POST',self.headers.get('Cookie',''),data)
    return self.send_body(200,{'saved':True})
   except PermissionError:return self.deny(401,'Officer session required')
   except (KeyError,ValueError,TypeError):return self.deny(400,'Invalid tariff data')
   except Exception as exc:
    code=getattr(exc,'pgcode',None)
    if code=='42501':return self.deny(403,'Finance tariff permission denied')
    if code=='22023':return self.deny(400,str(exc).splitlines()[0][:140])
    print('FINANCE_WRITE_ERROR',type(exc).__name__,str(exc)[:140],flush=True)
    return self.deny(503,'Finance tariff save failed')
  if route in ('/sim/treasury/checkout','/sim/treasury/adjust','/sim/treasury/import','/sim/treasury/import-settlements'):
   if not self.host_ok() or self.headers.get('Origin')!=self.expected_origin:
    return self.deny(403,'Browser origin rejected')
   if self.headers.get('Content-Type','').split(';')[0].strip()!='application/json':
    return self.deny(415,'JSON required')
   try:
    n=int(self.headers.get('Content-Length','0'))
    if not 2<=n<=2048:return self.deny(413,'Request size rejected')
    payload=json.loads(self.rfile.read(n).decode('utf-8'))
    result=treasury_operate(db,route,'POST',self.headers.get('Cookie',''),payload)
    return self.send_body(200,result)
   except PermissionError:return self.deny(401,'Officer session required')
   except (KeyError,ValueError,TypeError):return self.deny(400,'Invalid simulation data')
   except Exception as exc:
    code=getattr(exc,'pgcode',None)
    if code=='42501':return self.deny(403,'Treasurer permission denied')
    if code=='23505':return self.deny(409,'Duplicate provider reference')
    if code=='22023':return self.deny(400,str(exc).splitlines()[0][:140])
    print('TREASURY_WRITE_ERROR',type(exc).__name__,str(exc)[:130],flush=True)
    return self.deny(503,'Simulation event unavailable')
  if route in ('/sim/payments/issue','/sim/payments/provider','/sim/payments/reconcile'):
   if not self.host_ok() or self.headers.get('Origin')!=self.expected_origin:
    return self.deny(403,'Browser origin rejected')
   if self.headers.get('Content-Type','').split(';')[0].strip()!='application/json':
    return self.deny(415,'JSON required')
   try:
    n=int(self.headers.get('Content-Length','0'))
    if not 2<=n<=4096:return self.deny(413,'Request size rejected')
    body=json.loads(self.rfile.read(n).decode('utf-8'))
    result=payment_operate(db,route,'POST',self.headers.get('Cookie',''),body)
    return self.send_body(200,{'saved':True,'id':str(result) if result is not None else None,'matched':result if isinstance(result,bool) else None})
   except PermissionError:return self.deny(401,'Officer session required')
   except (KeyError,ValueError,TypeError):return self.deny(400,'Invalid payment fields')
   except Exception as exc:
    code=getattr(exc,'pgcode',None)
    if code=='42501':return self.deny(403,'Payment permission denied')
    if code=='23505':return self.deny(409,'Duplicate provider transaction, payout or fee request')
    if code=='22023':return self.deny(400,str(exc).splitlines()[0][:150])
    print('SIM_PAYMENT_WRITE_ERROR',type(exc).__name__,str(exc)[:140],flush=True)
    return self.deny(503,'Simulation payment operation unavailable')
  if route in ('/sim/api/member','/sim/api/rate','/sim/api/request','/sim/api/approve'):
   if not self.host_ok() or self.headers.get('Origin')!=self.expected_origin:
    return self.deny(403,'Browser origin rejected')
   if self.headers.get('Content-Type','').split(';')[0].strip()!='application/json':
    return self.deny(415,'JSON required')
   try:
    n=int(self.headers.get('Content-Length','0'))
    if n<2 or n>4096:return self.deny(413,'Request size rejected')
    body=json.loads(self.rfile.read(n).decode('utf-8'))
    result=workflow_execute(db,route,'POST',self.headers.get('Cookie',''),body)
    return self.send_body(200,{'saved':True,'id':str(result) if result is not None else None})
   except PermissionError:
    return self.deny(401,'Session required')
   except (KeyError,ValueError,TypeError):
    return self.deny(400,'Invalid form values')
   except Exception as exc:
    code=getattr(exc,'pgcode',None)
    if code=='42501':return self.deny(403,'Permission denied')
    if code=='23P01':return self.deny(409,'Booking conflicts with an existing approved allocation')
    if code=='23505':return self.deny(409,'Duplicate member or booking')
    if code=='22023':return self.deny(400,str(exc).splitlines()[0][:150])
    print('SIM_WORKFLOW_ERROR',type(exc).__name__,str(exc)[:160],flush=True)
    return self.deny(503,'Simulation write unavailable')
  if route!='/sim/session':return super().do_POST()
  if not self.host_ok() or self.headers.get('Origin')!=self.expected_origin:return self.deny(403,'Origin rejected')
  if self.headers.get('Content-Type','').split(';')[0].strip()!='application/json':return self.deny(415,'JSON required')
  try:
   n=int(self.headers.get('Content-Length','0'))
   if not 2<=n<=1024:return self.deny(413,'Invalid request size')
   data=json.loads(self.rfile.read(n).decode())
   label=data.get('officer','')
   if label not in ACCOUNTS:return self.deny(403,'Access denied')
   now=monotonic()
   with lock:
    ip=self.client_address[0]
    recent=[t for t in attempts.get(ip,[]) if now-t<600]
    if len(recent)>=10:return self.deny(429,'Too many attempts')
    recent.append(now);attempts[ip]=recent
   with lock:
    officer=ACCOUNTS[label]
    d=software_device(label)
    present=flow.store.credentials_for(officer)
    if d.id not in {c.id for c in present}:
     challenge,raw=flow.begin_enrolment(officer,label,label+' synthetic')
     flow.finish_enrolment(officer,challenge,d.register(json.loads(raw),ORIGIN))
    # Restore virtual device sign counter from the authoritative PostgreSQL
    # credential record; never reset it after a service restart.
    stored=next((c for c in flow.store.credentials_for(officer) if c.id==d.id),None)
    if stored is None: raise RuntimeError('Simulated credential not registered')
    d.count=stored.sign_count
    challenge,raw=flow.begin_login(officer)
    assertion=d.authenticate(json.loads(raw),ORIGIN)
    cookie=controller.complete_passkey(officer,challenge,assertion)
   return self.send_body(200,{'synthetic':True,'officer':label},cookie=cookie)
  except Exception as exc:
   print('SIM_ERROR:',type(exc).__name__,str(exc)[:240],flush=True)
   return self.deny(503,'Simulation failed')

if __name__=='__main__':
 ThreadingHTTPServer(('127.0.0.1',8767),SimHandler).serve_forever()
