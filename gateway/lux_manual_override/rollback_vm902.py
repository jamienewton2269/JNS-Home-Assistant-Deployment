#!/usr/bin/env python3
"""Hash-guarded HA-Primary lighting launcher rollback; never touches .storage."""
from pathlib import Path
import sys,hashlib,tempfile,os
root=Path('/config')
backup=Path(sys.argv[1])
expected_config=sys.argv[2]
expected_dashboard=sys.argv[3]
cfg=root/'configuration.yaml'
dash=root/'dashboards/jns_evening_lighting.yaml'
def sha(data):return hashlib.sha256(data).hexdigest()
if backup.parent.parent!=root/'.jns-backups' or not backup.parent.name.startswith('lux-primary-panel-') or backup.name!='configuration.yaml':
 raise SystemExit('PRIMARY_ROLLBACK_BLOCKED path mismatch')
if not backup.is_file() or not cfg.is_file() or not dash.is_file():raise SystemExit('PRIMARY_ROLLBACK_BLOCKED missing file')
if sha(cfg.read_bytes())!=expected_config or sha(dash.read_bytes())!=expected_dashboard:
 raise SystemExit('PRIMARY_ROLLBACK_BLOCKED changed live file')
content=backup.read_bytes()
fd,tmp=tempfile.mkstemp(prefix='.jns-primary-rollback-',dir=str(cfg.parent))
try:
 with os.fdopen(fd,'wb') as f:f.write(content);f.flush();os.fsync(f.fileno())
 st=cfg.stat();os.chown(tmp,st.st_uid,st.st_gid);os.chmod(tmp,st.st_mode&0o777)
 os.replace(tmp,cfg)
finally:
 if os.path.exists(tmp):os.unlink(tmp)
dash.unlink()
print('JNS_PRIMARY_LUX_ROLLBACK_OK',flush=True)
