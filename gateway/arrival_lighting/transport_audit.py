#!/usr/bin/env python3
import base64,json,time
import readiness_probe as rp
CORE=r"""
from pathlib import Path
import yaml,json,re
text=Path('/config/configuration.yaml').read_text()
m=re.search(r'(?ms)^remote_homeassistant:\s*\n(.*?)(?=^[A-Za-z][\w_-]*:\s*(?:\n|$)|\Z)',text)
if not m:
 print(json.dumps({'status':'no_remote_block'}));raise SystemExit
data=yaml.load('remote_homeassistant:\n'+m.group(1),Loader=yaml.BaseLoader)
root=data.get('remote_homeassistant')
arr=root.get('instances',[]) if isinstance(root,dict) else []
res=[]
shape={'root_type':type(root).__name__,'root_keys':list(root) if isinstance(root,dict) else [],'instances_type':type(arr).__name__,'instances_count':len(arr) if hasattr(arr,'__len__') else 0,'instances_dictionary_keys':list(arr) if isinstance(arr,dict) else []}
for i in arr:
 if not isinstance(i,dict):continue
 safe={}
 for k,v in i.items():
  safe[k]={'type':type(v).__name__,
           'has_value':bool(v),
           'value_class':('secret_ref' if isinstance(v,str) and ('!secret' in v or 'secret' in v.lower()) else 'present')}
  if k in ('include','exclude') and isinstance(v,dict):
   safe[k]['nested_keys']=list(v)
 res.append(safe)
print(json.dumps({'status':'ok','shape':shape,'instances':res}))
"""
p="exec(__import__('base64').b64decode("+repr(base64.b64encode(CORE.encode()).decode())+"))"
cmd=['qm','guest','exec','905','--','docker','exec','homeassistant','python3','-c',p]
d=json.loads(rp.ssh_host('nodeb',cmd))
for _ in range(45):
 if d.get('exited'):break
 time.sleep(1);d=json.loads(rp.ssh_host('nodeb',['qm','guest','exec-status','905',str(d['pid'])]))
if d.get('exitcode')!=0: raise SystemExit("remote config inspect failed")
print("VM905_EXISTING_REMOTE_CONFIG_SHAPE",d['out-data'].strip())
