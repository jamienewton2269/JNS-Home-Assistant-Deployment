#!/usr/bin/env python3
import subprocess,shlex,base64,pathlib,time,json,sys
def remote(host,args,capture=False):
 r=subprocess.run(['ssh','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','root@'+host,shlex.join(args)],capture_output=capture,text=True)
 if r.returncode:raise RuntimeError('Identity operation failed on '+host)
 return r.stdout
def py(host,ct,source,capture=False):
 # Suppress source/argument tracebacks so reset links cannot enter logs.
 wrapper='import base64,sys\ntry:exec(compile(base64.b64decode('+repr(base64.b64encode(source.encode()).decode())+'),"identity-operation","exec"))\nexcept Exception as exc:print(type(exc).__name__+": private operation failed",file=sys.stderr);sys.exit(1)'
 return remote(host,['pct','exec',str(ct),'--','python3','-c',wrapper],capture)
def upload(host,ct,target,source):
 code='import pathlib,base64;p=pathlib.Path('+repr(target)+');p.write_bytes(base64.b64decode('+repr(base64.b64encode(source).decode())+'));p.chmod(0o700)'
 py(host,ct,code)
try:
 backup_key=remote('nodea.home.arpa',['python3','-c',"import pathlib,json;print(json.loads(pathlib.Path('/root/jns-identity/bootstrap.json').read_text())['backup_key'])"],True).strip()
 for host,ct,name in [('nodea.home.arpa',251,'auth-a'),('nodeb.home.arpa',252,'auth-b')]:
  py(host,ct,"import pathlib,json;p=pathlib.Path('/root/identity/bootstrap.json');d=json.loads(p.read_text());d['backup_key']="+repr(backup_key)+";p.write_text(json.dumps(d));p.chmod(0o600)")
  upload(host,ct,'/root/identity/maintenance.py',pathlib.Path('identity/maintenance.py').read_bytes())
  py(host,ct,pathlib.Path('identity/verify_backup.py').read_text())
  remote(host,['/usr/local/sbin/identity-backup',str(ct),name])
 subprocess.run(['python3','identity/failover.py'],check=True)
 source=pathlib.Path('identity/web_test_guest.py').read_text()
 py('nodea.home.arpa',251,source+'\nstart()\n')
 uid=json.loads(py('nodea.home.arpa',251,"print((__import__('pathlib').Path('/root/identity/web-test.json')).read_text())",True))['uid']
 url=''
 for attempt in range(12):
  # Read only commissioning mail matching the disposable UID. Never log message data.
  scan='''import pathlib,email,re,html,json
from email import policy
uid='''+repr(uid)+'''
found=''
for folder in ['new','cur']:
 for p in pathlib.Path('/var/vmail/jnsystems.xyz/jamie/Maildir',folder).glob('*'):
  if __import__('time').time()-p.stat().st_mtime>600:continue
  raw=p.read_bytes()
  msg=email.message_from_bytes(raw,policy=policy.default)
  text=' '.join(part.get_content() for part in msg.walk() if part.get_content_type() in ['text/plain','text/html'])
  if uid not in text:continue
  for candidate in re.findall(r'https://auth-a\\.home\\.arpa/password/[^\\s<>]+',html.unescape(text)):
   candidate=candidate.rstrip(chr(34)+chr(39))
   if 'token=' in candidate:found=candidate
print(json.dumps({'url':found}))
'''
  result=json.loads(py('nodea.home.arpa',250,scan,True));url=result['url']
  if url:break
  time.sleep(5)
 if not url:raise AssertionError('No recovery message reached Jamie within one minute')
 py('nodea.home.arpa',251,source+'\nfinish('+repr(url)+')\n')
 py('nodea.home.arpa',251,source+'\ncleanup()\n')
 print('OPERATIONAL ACCEPTANCE COMPLETE')
except Exception as exc:
 print(type(exc).__name__+': operational acceptance incomplete; no credentials or reset tokens printed',file=sys.stderr);sys.exit(1)
