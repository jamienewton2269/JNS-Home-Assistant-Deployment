#!/usr/bin/env python3
"""Safely switch JNS MQTT Area receiver from preview to add-only on VM902."""
from pathlib import Path
import datetime,hashlib,json,os,sys,tempfile
p=Path('/config/configuration.yaml')
old=p.read_bytes()
pattern=b'jns_native_area_sync:\n  node: ha-primary\n  apply: false'
if old.count(pattern)!=1:raise SystemExit('JNS_AREA_APPLY_BLOCKED exact preview stanza not unique')
new=old.replace(pattern,b'jns_native_area_sync:\n  node: ha-primary\n  apply: true',1)
sha=lambda b:hashlib.sha256(b).hexdigest()
print('JNS_AREA_PROMOTION_PLAN '+json.dumps({'old_sha':sha(old),'new_sha':sha(new),'status':'ready'}),flush=True)
if '--apply' not in sys.argv:raise SystemExit(0)
now=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
backup=Path('/config/.jns-backups')/('native-area-enable-'+now+'.yaml')
backup.write_bytes(old)
if sha(backup.read_bytes())!=sha(old):raise SystemExit('JNS_AREA_APPLY_BLOCKED backup failed')
if p.read_bytes()!=old:raise SystemExit('JNS_AREA_APPLY_BLOCKED concurrent edit')
fd,tmp=tempfile.mkstemp(prefix='.jns-area-',dir=str(p.parent))
try:
 with os.fdopen(fd,'wb') as f:
  f.write(new);f.flush();os.fsync(f.fileno())
 st=p.stat();os.chown(tmp,st.st_uid,st.st_gid);os.chmod(tmp,st.st_mode&0o777)
 os.replace(tmp,p)
finally:
 if os.path.exists(tmp):os.unlink(tmp)
print('JNS_AREA_PROMOTION_APPLIED '+json.dumps({'backup':str(backup),'old_sha':sha(old),'new_sha':sha(new)}),flush=True)
