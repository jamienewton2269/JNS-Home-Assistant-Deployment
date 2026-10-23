#!/usr/bin/env python3
"""Restore JNS Garden Features backup if the post-install Core check fails.

Checks the exact new hashes before restoring the three original files and
removing the newly added package. Refuses to overwrite subsequent edits.
"""
from pathlib import Path
import hashlib,json,os,sys,tempfile
ROOT=Path('/config')
folder=Path(sys.argv[1])
hashes=json.loads(sys.argv[2])
if folder.parent!=ROOT/'.jns-backups' or not folder.name.startswith('garden-features-'):
    raise SystemExit('ROLLBACK_BLOCKED backup path')
mapping={
 'automations.yaml':(ROOT/'automations.yaml',folder/'automations.yaml'),
 'jns_doorbell_security_lighting.yaml':(ROOT/'packages/jns_doorbell_security_lighting.yaml',folder/'doorbell.yaml'),
 'testing.yaml':(ROOT/'dashboards/testing.yaml',folder/'testing.yaml'),
 'jns_garden_features_backdoor.yaml':(ROOT/'packages/jns_garden_features_backdoor.yaml',None)
}
def sha(b):return hashlib.sha256(b).hexdigest()
for name,(path,backup) in mapping.items():
    if not path.is_file() or sha(path.read_bytes())!=hashes.get(name):
        raise SystemExit('ROLLBACK_BLOCKED live file modified: '+name)
    if backup is not None and not backup.is_file():
        raise SystemExit('ROLLBACK_BLOCKED missing backup: '+name)
for name,(path,backup) in mapping.items():
    if backup is None:
        path.unlink()
    else:
        data=backup.read_bytes()
        fd,tmp=tempfile.mkstemp(prefix='.jns-rollback-',dir=str(path.parent))
        try:
            with os.fdopen(fd,'wb') as f:
                f.write(data);f.flush();os.fsync(f.fileno())
            st=path.stat()
            os.chmod(tmp,st.st_mode&0o777)
            os.chown(tmp,st.st_uid,st.st_gid)
            os.replace(tmp,path)
        finally:
            if os.path.exists(tmp):os.unlink(tmp)
print('JNS_GARDEN_ROLLBACK_OK')
