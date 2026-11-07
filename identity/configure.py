#!/usr/bin/env python3
"""Configure standard OpenLDAP and packaged web applications. No secrets in git."""
import os,pathlib,json,subprocess,base64,shlex,time,sys
NODES=[('nodea.home.arpa',251,'auth-a',1),('nodeb.home.arpa',252,'auth-b',2)]
def remote(host,args,capture=False):
    r=subprocess.run(['ssh','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','root@'+host,shlex.join(args)],capture_output=capture,text=True)
    if r.returncode: raise RuntimeError('Remote operation failed on '+host+'; see private logs if applicable')
    return r.stdout if capture else ''
def py(host,ct,source,capture=False):
    code='import base64;exec(compile(base64.b64decode('+repr(base64.b64encode(source.encode()).decode())+'),"identity-configure","exec"))'
    args=['python3','-c',code]
    if ct:args=['pct','exec',str(ct),'--']+args
    return remote(host,args,capture)
def put(host,ct,path,data,mode=0o600):
    encoded=base64.b64encode(data if isinstance(data,bytes) else data.encode()).decode()
    py(host,ct,f'import pathlib,base64; p=pathlib.Path({path!r}); p.parent.mkdir(parents=True,exist_ok=True); p.write_bytes(base64.b64decode({encoded!r})); p.chmod({mode})')

bootstrap=r'''
import pathlib,secrets,subprocess,json,os
os.umask(0o077)
r=pathlib.Path('/root/jns-identity');r.mkdir(mode=0o700,exist_ok=True)
state=r/'bootstrap.json'
if not state.exists():
 d={k:secrets.token_urlsafe(32) for k in ['admin','replicator','reset','reader','jamie','jamie-admin','keyphrase','lam-config']}
 def run(args):subprocess.run(args,check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
 run(['openssl','req','-x509','-newkey','ec','-pkeyopt','ec_paramgen_curve:P-256','-nodes','-keyout',str(r/'ca.key'),'-out',str(r/'ca.crt'),'-days','3650','-subj','/CN=JNSystems Identity Root CA','-addext','basicConstraints=critical,CA:TRUE','-addext','keyUsage=critical,keyCertSign,cRLSign'])
 d['ca']=(r/'ca.crt').read_text()
 for name in ['auth-a','auth-b']:
  run(['openssl','req','-new','-newkey','ec','-pkeyopt','ec_paramgen_curve:P-256','-nodes','-keyout',str(r/(name+'.key')),'-out',str(r/(name+'.csr')),'-subj','/CN='+name+'.home.arpa'])
  (r/'ext').write_text('subjectAltName=DNS:'+name+'.home.arpa,DNS:'+name+'\nbasicConstraints=CA:FALSE\nkeyUsage=digitalSignature\nextendedKeyUsage=serverAuth\n')
  run(['openssl','x509','-req','-in',str(r/(name+'.csr')),'-CA',str(r/'ca.crt'),'-CAkey',str(r/'ca.key'),'-CAcreateserial','-out',str(r/(name+'.crt')),'-days','365','-extfile',str(r/'ext')])
  d[name+'_key']=(r/(name+'.key')).read_text();d[name+'_crt']=(r/(name+'.crt')).read_text()
 state.write_text(json.dumps(d));state.chmod(0o600)
print(state.read_text())
'''
try:
    bundle=json.loads(py('nodea.home.arpa',None,bootstrap,True))
    # Reuse the already working SMTP2GO relay credential, privately in memory.
    smtp=py('nodea.home.arpa',250,"import pathlib;print(pathlib.Path('/etc/postfix/smtp2go_passwd').read_text().strip())",True).strip()
    bundle['smtp_user'],bundle['smtp_password']=smtp.split(' ',1)[1].split(':',1)
    for host,ct,name,sid in NODES:
        peer='auth-b' if sid==1 else 'auth-a'
        state={k:v for k,v in bundle.items() if not k.endswith('_key') and not k.endswith('_crt')}
        state.update(name=name,peer=peer,sid=sid,certificate=bundle[name+'_crt'],private_key=bundle[name+'_key'])
        put(host,ct,'/root/identity/bootstrap.json',json.dumps(state))
        put(host,ct,'/root/identity/guest_configure.py',pathlib.Path('identity/guest_configure.py').read_bytes(),0o700)
        put(host,ct,'/root/identity/health.py',pathlib.Path('identity/health.py').read_bytes(),0o700)
        put(host,ct,'/var/www/identity/index.html',pathlib.Path('identity/index.html').read_bytes(),0o644)
        # Run private configuration logs: neither exceptions nor shell tracing expose secrets.
        remote(host,['pct','exec',str(ct),'--','bash','-c','python3 /root/identity/guest_configure.py > /root/identity/configure.log 2>&1 || { echo "Identity configuration failed; private log: /root/identity/configure.log"; exit 1; }'])
        print('CONFIGURED',name,flush=True)
except Exception as exc:
    print(type(exc).__name__+': identity stage failed; credentials were not printed',file=sys.stderr);sys.exit(1)
