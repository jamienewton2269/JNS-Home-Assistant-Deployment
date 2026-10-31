#!/usr/bin/env python3
"""Small, SHA/structure-guarded VM905 Testing card update. No Core restart."""
import base64,importlib.util,json,os,pathlib,re
spec=importlib.util.spec_from_file_location("jns_heating_bridge",pathlib.Path("gateway/heating_presence/deploy.py"))
bridge=importlib.util.module_from_spec(spec);spec.loader.exec_module(bridge)
INNER=r"""
import copy,hashlib,json,os,pathlib,re,stat,sys,tempfile,yaml
p=pathlib.Path('/config/dashboards/testing.yaml')
assert p.is_file() and not p.is_symlink()
original=p.read_bytes()
data=yaml.safe_load(original)
views=data.get('views',[])
assert 17<=len(views)<=30,'Unexpected Testing view count'
matched=[v for v in views if v.get('path')=='house-temperature']
assert len(matched)==1,'House Temperature view not unique'
cards=matched[0].get('cards',[])
target=[c for c in cards if c.get('title')=='JNS Heating - Predictive Schedule and Bedtime Learning']
assert len(target)==1 and target[0].get('type')=='entities','Target heating card differs'
ids=[x.get('entity') if isinstance(x,dict) else x for x in target[0].get('entities',[])]
existing='input_boolean.jns_heating_automatic_override'
new=['sensor.jns_heating_active_requested_target','input_boolean.jns_heating_manual_setpoint_hold']
assert existing in ids,'Expected existing heating control absent'
assert not any(x in ids for x in new),'Manual target status card already installed'
text=original.decode('utf8')
needle=r'(?m)^(?P<indent>[ \t]*)- entity: input_boolean\.jns_heating_automatic_override[ \t]*$'
matches=list(re.finditer(needle,text))
# There can be a controls view and a house view containing this entity.
assert len(matches)>=1
viewstart=re.search(r'(?m)^- title:.*\n  path: house-temperature[ \t]*$',text)
assert viewstart is not None,'House Temp view literal header missing'
i=viewstart.end()
nextview=text.find('\n- title:',i)
if nextview<0:nextview=len(text)
inside=[m for m in matches if viewstart.start()<=m.start()<=nextview]
assert len(inside)==1,'Target heating entity not unique in view'
m=inside[0];pad=m.group('indent')
extra=(pad+'- entity: sensor.jns_heating_active_requested_target\n'+
       pad+'  name: Active requested temperature\n'+
       pad+'- entity: input_boolean.jns_heating_manual_setpoint_hold\n'+
       pad+'  name: User-selected temperature protection\n')
modified=(text[:m.start()]+extra+text[m.start():]).encode()
parsed=yaml.safe_load(modified)
assert parsed['views'][:views.index(matched[0])]==views[:views.index(matched[0])]
assert parsed['views'][views.index(matched[0])+1:]==views[views.index(matched[0])+1:]
newcards=parsed['views'][views.index(matched[0])]['cards']
assert len(newcards)==len(cards) and all(n==o for n,o in zip(newcards[1:],cards[1:]))
assert all(x in [item.get('entity') for item in newcards[0]['entities']] for x in new)
h=lambda b:hashlib.sha256(b).hexdigest()
print('JNS_MANUAL_HEATING_DASHBOARD_PLAN '+json.dumps({
 'before_sha':h(original),'after_sha':h(modified),'views_preserved':len(views),
 'heating_card_only':True,'core_restart':False},sort_keys=True),flush=True)
if '--apply' not in sys.argv:sys.exit(0)
runid=sys.argv[-1]
assert runid.isdecimal()
bdir=pathlib.Path('/config/.jns-backups')/('manual-heating-dashboard-'+runid)
bdir.mkdir(mode=0o700,parents=True,exist_ok=False)
backup=bdir/'testing.yaml'
backup.write_bytes(original);backup.chmod(0o600)
assert h(backup.read_bytes())==h(original)
assert p.read_bytes()==original
st=p.stat();fd,tmp=tempfile.mkstemp(prefix='.jns-manual-dashboard-',dir=str(p.parent))
try:
 with os.fdopen(fd,'wb') as f:f.write(modified);f.flush();os.fsync(f.fileno())
 os.chown(tmp,st.st_uid,st.st_gid);os.chmod(tmp,stat.S_IMODE(st.st_mode))
 assert p.read_bytes()==original,'Concurrent dashboard edit detected'
 os.replace(tmp,p)
finally:
 if os.path.exists(tmp):os.unlink(tmp)
assert h(p.read_bytes())==h(modified)
print('JNS_MANUAL_HEATING_DASHBOARD_APPLIED '+json.dumps({
 'views_preserved':len(views),'new_sha':h(modified),'backup_verified':True,
 'only_heating_card_changed':True,'no_core_restart':True
},sort_keys=True),flush=True)
"""
def main():
 if not os.getenv('GITHUB_RUN_ID','').isdecimal():raise RuntimeError('Runner identity required')
 out=bridge.core(INNER,['--apply',os.environ['GITHUB_RUN_ID']],seconds=110)
 if out.get('exitcode')!=0:
  raise RuntimeError('Dashboard release rejected; main heating system unchanged')
 text=out.get('out-data') or ''
 for line in text.splitlines():
  if line.startswith(('JNS_MANUAL_HEATING_DASHBOARD_PLAN ',
                      'JNS_MANUAL_HEATING_DASHBOARD_APPLIED ')):
   print(line,flush=True)
 if 'JNS_MANUAL_HEATING_DASHBOARD_APPLIED ' not in text:
  raise RuntimeError('Dashboard update not verified')
if __name__=='__main__':
 try:main()
 except Exception as e:
  print('JNS_MANUAL_HEATING_DASHBOARD_FAILED '+type(e).__name__+': '+str(e)[:200],flush=True)
  raise
