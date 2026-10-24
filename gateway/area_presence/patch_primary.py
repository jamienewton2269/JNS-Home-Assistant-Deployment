#!/usr/bin/env python3
"""Guarded installation for JNS MQTT presence publisher and area receiver.
Execute in VM902 Home Assistant Core. Node C injects the audited source.
Never modifies .storage, broker settings or existing Area Registry entries.
"""
from pathlib import Path
import base64,datetime,hashlib,json,os,re,sys,tempfile
import yaml
root=Path('/config')
configuration=root/'configuration.yaml'
component=root/'custom_components/jns_native_area_sync'
files={
 component/'__init__.py':base64.b64decode(COMPONENT_PY),
 component/'manifest.json':base64.b64decode(COMPONENT_JSON),
}
cfg_before=configuration.read_bytes()
snippet=base64.b64decode(CONFIG_APPEND).decode('utf-8')
def check(ok,msg):
 if not ok:raise ValueError(msg)
def sha(b):return hashlib.sha256(b).hexdigest()
check(not component.exists(),'area-sync component already exists; refuse overwrite')
for key in ['mqtt_statestream','jns_native_area_sync']:
 check(not re.search(r'(?m)^'+re.escape(key)+r':\s*',cfg_before.decode()),'config key already present: '+key)
check('mqtt_statestream:' in snippet and 'jns_native_area_sync:' in snippet,'missing staged blocks')
check(len(snippet)<2500,'oversized configuration')
try:
 import py_compile
 # Validate all the external byte buffers without installing
 for filename,contents in files.items():
  if filename.name.endswith('.json'):
   obj=json.loads(contents)
   check(obj.get('domain')=='jns_native_area_sync','wrong manifest')
  else:
   compile(contents,'<jns-area-sync>','exec')
except Exception as e:raise ValueError('invalid plugin source '+type(e).__name__)
reg=root/'.storage/core.config_entries'
entries=json.loads(reg.read_text())['data']['entries']
check(any(e.get('domain')=='mqtt' and not e.get('disabled_by') for e in entries),'MQTT integration not configured/enabled')
check(len(cfg_before)<160000,'configuration too large for guarded update')
cfg_after=cfg_before.rstrip()+b'\n\n'+snippet.encode('utf-8').rstrip()+b'\n'
# Avoid safe_load on existing file: Home Assistant !include custom YAML tags.
try:yaml.safe_load(snippet)
except Exception as e:raise ValueError('Invalid appended fragment')
print('JNS_PRESENCE_AREA_PRIMARY_PLAN '+json.dumps({
 'status':'ready','no_existing_area_registry_changes':True,
 'mqtt_entries':len([e for e in entries if e.get('domain')=='mqtt']),
 'file_count':len(files)+1,'backup_hash':sha(cfg_before),
 'configuration_sha256_after':sha(cfg_after),
 'source_hashes':{p.name:sha(data) for p,data in files.items()}},sort_keys=True),flush=True)
if '--apply' not in sys.argv:raise SystemExit(0)
stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
b=root/'.jns-backups'/('presence-areas-primary-'+stamp)
b.mkdir(parents=True,exist_ok=False)
(b/'configuration.yaml').write_bytes(cfg_before)
check((b/'configuration.yaml').read_bytes()==cfg_before,'backup error')
component.mkdir(parents=True,exist_ok=False)
changed=[]
def atomic(path,blob,expected=None):
 if expected is not None:check(path.read_bytes()==expected,'concurrent modification '+path.name)
 if expected is None:check(not path.exists(),'unexpected existing file '+path.name)
 fd, tmp=tempfile.mkstemp(dir=str(path.parent),prefix='.jns-mqtt-')
 try:
  with os.fdopen(fd,'wb') as file:
   file.write(blob);file.flush();os.fsync(file.fileno())
  if expected is not None:
   st=path.stat();os.chmod(tmp,st.st_mode&0o777);os.chown(tmp,st.st_uid,st.st_gid)
  else:os.chmod(tmp,0o644)
  os.replace(tmp,path)
 finally:
  if os.path.exists(tmp):os.unlink(tmp)
try:
 for path,contents in files.items():
  atomic(path,contents);changed.append(path)
 atomic(configuration,cfg_after,cfg_before);changed.append(configuration)
 print('JNS_PRESENCE_AREA_PRIMARY_APPLIED '+json.dumps({
  'status':'applied','backup':str(b),
  'changed_hashes':{str(path):sha(path.read_bytes()) for path in changed}},sort_keys=True),flush=True)
except BaseException:
 # Roll back only files still equal to our exact intended versions.
 for path in reversed(changed):
  expected=cfg_after if path==configuration else files[path]
  if path.exists() and sha(path.read_bytes())==sha(expected):
   if path==configuration:atomic(path,cfg_before,cfg_after)
   else:path.unlink()
 if component.exists() and not list(component.iterdir()):component.rmdir()
 raise
