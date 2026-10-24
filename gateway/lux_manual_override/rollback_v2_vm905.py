#!/usr/bin/env python3
"""Restore only verified JNS Lux V2 files from on-VM905 backups."""
import hashlib,json,os,sys,tempfile
from pathlib import Path
root=Path('/config')
backup=Path(sys.argv[1]); hashes=json.loads(sys.argv[2])
files=[(root/'automations.yaml',backup/'automations.yaml'),
       (root/'packages/jns_lux_manual_off_v1.yaml',backup/'jns_lux_manual_off_v1.yaml'),
       (root/'dashboards/testing.yaml',backup/'testing.yaml')]
assert str(backup).startswith('/config/.jns-backups/lux-manual-off-v2-')
assert backup.is_dir()
def digest(data):return hashlib.sha256(data).hexdigest()
# Preflight every file before touching any, fail closed on concurrent modification.
for path,stored in files:
 assert path.is_file() and stored.is_file()
 assert digest(path.read_bytes())==hashes[str(path)],"Concurrent edit to "+str(path)
for path,stored in files:
 b=stored.read_bytes()
 fd,tmp=tempfile.mkstemp(prefix='.jns-lux-v2-restore-',dir=path.parent)
 try:
  with os.fdopen(fd,'wb') as f:f.write(b);f.flush();os.fsync(f.fileno())
  st=path.stat();os.chown(tmp,st.st_uid,st.st_gid);os.chmod(tmp,st.st_mode & 0o777)
  os.replace(tmp,path)
 finally:
  if os.path.exists(tmp):os.unlink(tmp)
 print('RESTORED',str(path),digest(b),flush=True)
print('JNS_LUX_V2_ROLLBACK_COMPLETE',flush=True)
