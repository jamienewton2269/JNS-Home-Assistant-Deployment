#!/usr/bin/env python3
"""Add-only guarded Welcome Home package staging for HA-General VM905."""
from pathlib import Path
import base64,datetime,hashlib,json,os,sys,tempfile,yaml
root=Path('/config'); dest=root/'packages/jns_welcome_home.yaml'
blob=base64.b64decode(WELCOME_PACKAGE_B64)
obj=yaml.safe_load(blob)
if not isinstance(obj,dict) or not obj.get('automation') or not obj.get('script'):
 raise SystemExit('JNS_WELCOME_BLOCKED package structure')
if obj['input_boolean']['jns_welcome_home_enabled'].get('initial') is not False:
 raise SystemExit('JNS_WELCOME_BLOCKED package not default disabled')
if dest.exists():
 raise SystemExit('JNS_WELCOME_BLOCKED package target exists')
registry=json.loads((root/'.storage/core.entity_registry').read_text())['data']['entities']
ids={a.get('unique_id') for a in registry if a.get('platform')=='automation'}
aliases={a.get('id') for a in obj['automation']}
if aliases & ids:
 raise SystemExit('JNS_WELCOME_BLOCKED automation ID collision')
config=(root/'configuration.yaml').read_text()
if 'packages:' not in config:
 raise SystemExit('JNS_WELCOME_BLOCKED packages not enabled')
sha=lambda b:hashlib.sha256(b).hexdigest()
print('JNS_WELCOME_PLAN '+json.dumps({'status':'ready','package_sha256':sha(blob),'path':str(dest),'enabled_initial':False,'automations':len(obj['automation'])},sort_keys=True),flush=True)
if '--apply' not in sys.argv:raise SystemExit(0)
stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
b=root/'.jns-backups'/('welcome-home-'+stamp)
b.mkdir(parents=True,exist_ok=False)
(b/'jns_welcome_home.yaml').write_bytes(blob)
if sha((b/'jns_welcome_home.yaml').read_bytes())!=sha(blob):raise SystemExit('JNS_WELCOME_BLOCKED backup checksum')
if dest.exists():raise SystemExit('JNS_WELCOME_BLOCKED concurrent package appeared')
fd,tmp=tempfile.mkstemp(dir=str(dest.parent),prefix='.jns-welcome-')
try:
 with os.fdopen(fd,'wb') as f:
  f.write(blob);f.flush();os.fsync(f.fileno())
 os.chmod(tmp,0o644)
 os.replace(tmp,dest)
finally:
 if os.path.exists(tmp):os.unlink(tmp)
print('JNS_WELCOME_APPLIED '+json.dumps({'status':'applied','backup':str(b),'path':str(dest),'sha256':sha(blob),'initially_enabled':False}),flush=True)
