#!/usr/bin/env python3
"""Read-only VM905 dusk/lux controller architecture audit, sanitised."""
import base64,json,sys,time
sys.path.insert(0,'gateway/arrival_lighting')
from readiness_probe import ssh_host
SCAN=r"""
import pathlib,yaml,json,re
root=pathlib.Path('/config')
paths=[root/'automations.yaml']+sorted((root/'packages').glob('*.yaml'))
for p in paths:
 try: data=yaml.safe_load(p.read_text())
 except Exception: continue
 if isinstance(data,dict):
  for typ in ('automation','input_boolean','input_text','input_number','timer','script','template'):
   v=data.get(typ)
   if isinstance(v,dict) and typ not in ('automation','template'):
    relevant={k:x for k,x in v.items() if re.search('lux|dusk|lighting|override|manual',k,re.I)}
    if relevant:print('JNS_LUX_HELPERS',p.name,typ,list(relevant),flush=True)
   if typ=='automation':
    arr=v if isinstance(v,list) else list(v.values()) if isinstance(v,dict) else []
    for a in arr:
     if not isinstance(a,dict):continue
     name=str(a.get('alias',''))
     if re.search('lux|dusk|light.*control|light.*monitor',name,re.I):
      print('JNS_LUX_AUTOMATION',p.name,yaml.safe_dump(a,sort_keys=False,allow_unicode=True,width=160)[:18000],flush=True)
 if isinstance(data,list):
  for a in data:
   if not isinstance(a,dict):continue
   name=str(a.get('alias',''))
   if re.search('lux|dusk|light.*control|light.*monitor',name,re.I):
    print('JNS_LUX_AUTOMATION',p.name,yaml.safe_dump(a,sort_keys=False,allow_unicode=True,width=160)[:18000],flush=True)
print('JNS_LUX_EXTRA_FILES')
for p in sorted(root.rglob('*lux*')):
 if p.is_file() and len(p.parts)<9: print(str(p.relative_to(root)),flush=True)
"""
cmd="exec(__import__('base64').b64decode('"+base64.b64encode(SCAN.encode()).decode()+"'))"
r=json.loads(ssh_host('nodeb',['qm','guest','exec','905','--','docker','exec','homeassistant','python3','-c',cmd]))
pid=r.get('pid')
for _ in range(60):
 if r.get('exited'):break
 if not isinstance(pid,int):raise RuntimeError('guest exec returned no initial pid')
 time.sleep(1)
 r=json.loads(ssh_host('nodeb',['qm','guest','exec-status','905',str(pid)]))
if not r.get('exited') or r.get('exitcode')!=0:raise RuntimeError(str(r.get('err-data',''))[-700:])
print(r.get('out-data','')[:100000],flush=True)
