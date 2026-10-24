#!/usr/bin/env python3
"""Restore exact backed-up Lux manual-off configuration only if no edits followed."""
import sys,json,hashlib,tempfile,os
from pathlib import Path
root=Path('/config');folder=Path(sys.argv[1]);expected=json.loads(sys.argv[2])
if folder.parent!=root/'.jns-backups' or not folder.name.startswith('lux-manual-off-'):
    raise SystemExit('ROLLBACK_BLOCKED backup root mismatch')
mapping={
 'automations.yaml':(root/'automations.yaml',folder/'automations.yaml'),
 'testing.yaml':(root/'dashboards/testing.yaml',folder/'testing.yaml'),
 'jns_lux_manual_off_v1.yaml':(root/'packages/jns_lux_manual_off_v1.yaml',None)}
def sha(b):return hashlib.sha256(b).hexdigest()
for key,(path,bak) in mapping.items():
    if not path.exists() or sha(path.read_bytes())!=expected.get(key):
        raise SystemExit('ROLLBACK_BLOCKED: post-deploy changed file '+key)
    if bak and not bak.is_file():raise SystemExit('ROLLBACK_BLOCKED: backup missing '+key)
for key,(path,bak) in mapping.items():
    if bak is None:
        path.unlink();continue
    content=bak.read_bytes();fd,tmp=tempfile.mkstemp(prefix='.jns-lux-backout-',dir=str(path.parent))
    try:
        with os.fdopen(fd,'wb') as f:
            f.write(content);f.flush();os.fsync(f.fileno())
        st=path.stat();os.chown(tmp,st.st_uid,st.st_gid);os.chmod(tmp,st.st_mode&0o777)
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)
print('JNS_LUX_MANUAL_ROLLBACK_OK',flush=True)
