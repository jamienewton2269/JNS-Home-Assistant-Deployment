#!/usr/bin/env python3
"""Add-only standalone Evening Lighting launcher to HA-Primary VM902.
Safe for storage-managed JNS Home. Does not touch Lovelace .storage.
"""
import base64,datetime,hashlib,json,os,re,sys,tempfile
from pathlib import Path
import yaml
ROOT=Path('/config')
CONFIG=ROOT/'configuration.yaml'
DASH=ROOT/'dashboards/jns_evening_lighting.yaml'
DASH_DATA=base64.b64decode(DASH_B64)
def sha(data):return hashlib.sha256(data).hexdigest()
def check(condition,msg):
 if not condition:raise RuntimeError(msg)
def atomic(path,data,before=None):
 if before is None:check(not path.exists(),'unexpected existing dashboard')
 else:check(path.read_bytes()==before,'concurrent config edit detected')
 fd,tmp=tempfile.mkstemp(prefix='.jns-lux-primary-',dir=str(path.parent))
 try:
  with os.fdopen(fd,'wb') as f:f.write(data);f.flush();os.fsync(f.fileno())
  if before is not None:
   st=path.stat();os.chown(tmp,st.st_uid,st.st_gid);os.chmod(tmp,st.st_mode&0o777)
  else:os.chmod(tmp,0o644)
  os.replace(tmp,path)
 finally:
  if os.path.exists(tmp):os.unlink(tmp)
def main():
 old=CONFIG.read_bytes()
 text=old.decode('utf-8')
 check(not re.search(r'(?m)^lovelace\s*:',text),'Existing lovelace config must be merged instead; refuse')
 check('jns-evening-lighting' not in text,'Primary launcher already configured')
 check(not DASH.exists(),'Primary dashboard path already exists')
 doc=yaml.safe_load(DASH_DATA)
 check(isinstance(doc,dict) and len(doc.get('views',[]))==1,'Unexpected Primary dashboard YAML')
 check('ha-general.home.arpa/testing-dashboard/evening-lighting' in DASH_DATA.decode(),'Missing HA-General destination')
 add="""# JNS manual evening lighting — additional YAML dashboard.
# Preserve existing storage-managed Home Assistant / JNS Home dashboards.
lovelace:
  mode: storage
  dashboards:
    jns-evening-lighting:
      mode: yaml
      title: Evening Lighting
      icon: mdi:lightbulb-night
      show_in_sidebar: true
      filename: dashboards/jns_evening_lighting.yaml
"""
 updated=(text.rstrip()+"\n\n"+add).encode()
 check(len(updated)>len(old),'Primary configuration did not grow')
 print('JNS_PRIMARY_LUX_PLAN '+json.dumps({'status':'ready','original_sha':sha(old),
       'new_sha':sha(updated),'dashboard_sha':sha(DASH_DATA),
       'panel_path':'jns-evening-lighting'}),flush=True)
 if '--apply' not in sys.argv:return
 stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
 folder=ROOT/'.jns-backups'/('lux-primary-panel-'+stamp)
 folder.mkdir(parents=True,exist_ok=False)
 backup=folder/'configuration.yaml';backup.write_bytes(old)
 check(sha(backup.read_bytes())==sha(old),'Primary config backup failed')
 DASH.parent.mkdir(parents=True,exist_ok=True)
 applied=[]
 try:
  atomic(DASH,DASH_DATA);applied.append(DASH)
  atomic(CONFIG,updated,old);applied.append(CONFIG)
 except BaseException:
  for path in reversed(applied):
   if path==DASH and path.read_bytes()==DASH_DATA:path.unlink()
   elif path==CONFIG and path.read_bytes()==updated:atomic(CONFIG,old,updated)
  raise
 print('JNS_PRIMARY_LUX_APPLIED '+json.dumps({'backup':str(backup),
       'configuration_sha':sha(updated),'dashboard_sha':sha(DASH_DATA)}),flush=True)
try:main()
except Exception as e:
 print('JNS_PRIMARY_LUX_BLOCKED '+type(e).__name__+': '+str(e)[:220],flush=True)
 raise SystemExit(2)
