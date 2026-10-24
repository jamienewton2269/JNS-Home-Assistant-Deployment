"""Rollback exact verified JNS MQTT presence + area sync primary changes."""
from pathlib import Path
import hashlib,json,os,sys,tempfile
root=Path('/config')
backup=Path(sys.argv[1])
expected=json.loads(sys.argv[2])
if backup.parent!=root/'.jns-backups' or not backup.name.startswith('presence-areas-primary-'):
 raise SystemExit('ROLLBACK_BLOCKED invalid backup path')
paths={
 'configuration.yaml':root/'configuration.yaml',
 '__init__.py':root/'custom_components/jns_native_area_sync/__init__.py',
 'manifest.json':root/'custom_components/jns_native_area_sync/manifest.json'}
def sha(x):return hashlib.sha256(x).hexdigest()
for name,p in paths.items():
 if not p.is_file() or sha(p.read_bytes())!=expected.get(str(p)):
  raise SystemExit('ROLLBACK_BLOCKED file modified after deployment: '+name)
old=(backup/'configuration.yaml').read_bytes()
p=paths['configuration.yaml']
fd,tmp=tempfile.mkstemp(prefix='.jns-primary-rollback-',dir=str(p.parent))
try:
 with os.fdopen(fd,'wb') as f:
  f.write(old);f.flush();os.fsync(f.fileno())
 st=p.stat();os.chmod(tmp,st.st_mode&0o777);os.chown(tmp,st.st_uid,st.st_gid)
 os.replace(tmp,p)
finally:
 if os.path.exists(tmp):os.unlink(tmp)
paths['__init__.py'].unlink()
paths['manifest.json'].unlink()
path=root/'custom_components/jns_native_area_sync'
if not list(path.iterdir()):path.rmdir()
print('JNS_PRIMARY_MQTT_AREA_ROLLBACK_COMPLETE',json.dumps({'config_sha256_restored':sha(old)}),flush=True)
