#!/usr/bin/env python3
"""Append Boiler Usage to the live Testing YAML; preserve every existing view."""
import sys,os,json,urllib.request
sys.path.insert(0,'gateway/boiler_monitor')
from deploy import core
PATCH=r"""
import pathlib,yaml,copy,json,hashlib,os,tempfile,shutil,stat,sys
root=pathlib.Path('/config')
target=root/'dashboards/testing.yaml'
source=root/'dashboards/jns_boiler_monitor.yaml'
assert target.is_file() and not target.is_symlink()
assert source.is_file() and not source.is_symlink()
# Confirm this is the configured Testing dashboard, not an unused template.
lines=(root/'configuration.yaml').read_text().splitlines()
start=next(i for i,l in enumerate(lines) if l.startswith('lovelace:'))
end=next((i for i in range(start+1,len(lines)) if lines[i] and not lines[i][0].isspace() and not lines[i].startswith('#')),len(lines))
ll=yaml.safe_load('\n'.join(lines[start:end]))['lovelace']
entry=ll['dashboards']['testing-dashboard']
assert entry['mode']=='yaml' and entry['filename']=='dashboards/testing.yaml'
original=target.read_bytes()
text=original.decode()
doc=yaml.safe_load(text)
assert isinstance(doc,dict) and isinstance(doc.get('views'),list) and doc['views']
before=copy.deepcopy(doc)
src=yaml.safe_load(source.read_text())
view=copy.deepcopy(src['views'][0])
view.update(title='Boiler Usage',path='boiler-usage',icon='mdi:radiator')
view.pop('subview',None)
existing=[v for v in doc['views'] if v.get('path')=='boiler-usage']
if existing:
 assert len(existing)==1 and existing[0]==view,'Existing boiler view conflict'
 print('TESTING_BOILER_ALREADY_PRESENT')
 raise SystemExit(0)
node=yaml.compose(text)
views=next(value for key,value in node.value if key.value=='views')
indent=views.value[0].start_mark.column
addition=yaml.safe_dump([view],allow_unicode=True,sort_keys=False)
addition=''.join(' '*indent+line if line.strip() else line for line in addition.splitlines(keepends=True))
pos=views.end_mark.index
proposed=text[:pos].rstrip('\n')+'\n'+addition+text[pos:]
expected=copy.deepcopy(doc);expected['views'].append(view)
assert yaml.safe_load(proposed)==expected,'Existing dashboard content changed'
backup=root/'.jns-backups'/('boiler-testing-tab-'+sys.argv[1])
backup.mkdir(parents=True,exist_ok=False)
shutil.copy2(target,backup/'testing.yaml')
oldsha=hashlib.sha256(original).hexdigest()
newsha=hashlib.sha256(proposed.encode()).hexdigest()
(backup/'manifest.json').write_text(json.dumps({'target':str(target),'before_sha256':oldsha,'after_sha256':newsha,'operation':'append Boiler Usage view'},indent=2))
assert target.read_bytes()==original,'Concurrent dashboard edit'
s=target.stat()
fd,tmp=tempfile.mkstemp(prefix='.jns-boiler-tab-',dir=str(target.parent))
try:
 with os.fdopen(fd,'w') as f:
  f.write(proposed);f.flush();os.fsync(f.fileno())
 os.chown(tmp,s.st_uid,s.st_gid);os.chmod(tmp,stat.S_IMODE(s.st_mode))
 assert target.read_bytes()==original,'Concurrent edit before rename'
 os.replace(tmp,target)
finally:
 if os.path.exists(tmp):os.unlink(tmp)
try:
 live=yaml.safe_load(target.read_text())
 assert live==expected and live['views'][:-1]==before['views']
 assert hashlib.sha256(target.read_bytes()).hexdigest()==newsha
except Exception:
 if hashlib.sha256(target.read_bytes()).hexdigest()==newsha:shutil.copy2(backup/'testing.yaml',target)
 raise
print('TESTING_BOILER_TAB_VERIFIED',json.dumps({'views_before':len(before['views']),'views_after':len(live['views']),'path':'/testing-dashboard/boiler-usage','backup':str(backup),'existing_views_preserved':True,'restart_required':False,'after_sha256':newsha}))
"""
runid=os.environ['GITHUB_RUN_ID']
assert runid.isdecimal()
print(core(PATCH,runid),flush=True)
with urllib.request.urlopen('http://ha-general.home.arpa/testing-dashboard/boiler-usage',timeout=10) as response:
 assert response.status==200
 print('TESTING_BOILER_HTTP',response.status,flush=True)
