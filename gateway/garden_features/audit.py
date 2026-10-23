#!/usr/bin/env python3
"""JNS garden water feature + Tuya back-door sensor audit. Read-only. Node C runner."""
import base64,json,time,sys
sys.path.insert(0,'gateway/arrival_lighting')
from readiness_probe import ssh_host
CODE=r'''
from pathlib import Path
import json,re,yaml
root=Path('/config'); store=root/'.storage'
def load(n,k):
    return json.loads((store/n).read_text())['data'][k]
entities=load('core.entity_registry','entities')
devices={d.get('id'):d for d in load('core.device_registry','devices')}
labels={l.get('label_id') or l.get('id'):l.get('name') for l in load('core.label_registry','labels')}
print('=== CANDIDATE BACK DOOR + GARDEN WATER FEATURE ENTITIES ===')
match=re.compile(r'(back.?door|rear.?door|water.?feature|fountain|garden.?ornament|dog.?run|garage.?security|tuya)',re.I)
for e in entities:
  eid=e.get('entity_id','')
  name=e.get('name') or e.get('original_name') or ''
  d=devices.get(e.get('device_id'),{})
  dn=d.get('name_by_user') or d.get('name') or ''
  if match.search(' '.join([eid,str(name),str(dn)])) or eid in ('switch.0x84fd27fffe9ce438',):
    if eid.startswith(('binary_sensor.','sensor.','switch.','light.','input_boolean.','timer.','button.')):
      print(json.dumps({'entity':eid,'name':name,'device':dn,'platform':e.get('platform'),
                        'disabled_by':e.get('disabled_by'),'labels':[labels.get(k,k) for k in e.get('labels',[])]},ensure_ascii=False))
print('=== AUTOMATION MATCHES ===')
source=root/'automations.yaml'
data=yaml.safe_load(source.read_text()) or []
for p in [source,*sorted((root/'packages').rglob('*.yaml'))]:
  try: v=yaml.safe_load(p.read_text())
  except Exception: continue
  arr=v if isinstance(v,list) else (v.get('automation',[]) if isinstance(v,dict) else [])
  if isinstance(arr,dict): arr=[arr]
  for a in arr:
    if not isinstance(a,dict):continue
    name=str(a.get('alias',''))
    dump=yaml.safe_dump(a,sort_keys=False,allow_unicode=True)
    if re.search(r'(water feature|back.?door|rear.?door|dog.?run|garage security|exterior lights|garden fountain)',name,re.I) or (
      re.search(r'water_feature|fountain',dump,re.I) and ('garden' in dump.lower())):
      print(json.dumps({'path':str(p.relative_to(root)),'id':a.get('id'),'alias':name,'yaml':dump[:12500]},ensure_ascii=False))
print('=== DASHBOARD MATCHING LINES ===')
for p in [root/'dashboards/testing.yaml',*sorted((root/'dashboards').glob('*.yaml'))]:
    if not p.exists():continue
    lines=p.read_text().splitlines()
    print('DASHBOARD',str(p.relative_to(root)),'lines',len(lines))
    indices=[i for i,x in enumerate(lines) if re.search(r'(water.feature|fountain|lighting.settings|maintenance|dog.?run|back.?door|garden|features|general.controls)',x,re.I)]
    for i in sorted(set(j for k in indices[:70] for j in range(max(0,k-2),min(len(lines),k+4)))):
        print(f'{i+1}: {lines[i][:240]}')
print('=== DASHBOARD VIEW DETAILS ===')
p=root/'dashboards/testing.yaml'
lines=p.read_text().splitlines()
for start,end in [(1,45),(270,296),(730,795),(1140,1182)]:
  print('region',start,end)
  for j in range(start-1,min(end,len(lines))):
    print(str(j+1)+': '+lines[j][:230])
print('=== GARDEN CONTROLS CONTEXT ===')
p=root/'dashboards/testing.yaml';lines=p.read_text().splitlines()
for start,end in [(175,215),(282,334),(335,365)]:
 print('REGION',start,end)
 for j in range(start-1,min(end,len(lines))):
  print(str(j+1)+': '+lines[j][:190])
print('=== DOORBELL RELEASE CONDITIONAL ===')
p=root/'packages/jns_doorbell_security_lighting.yaml';d=yaml.safe_load(p.read_text())
for a in d.get('automation',[]):
 if a.get('id')=='jns_doorbell_security_release_20261020':
  print(yaml.safe_dump(a,sort_keys=False)[:9500])
print('=== EXISTING HELPER NAMES ===')
for p in sorted((root/'packages').glob('*.yaml')):
   try: d=yaml.safe_load(p.read_text())
   except Exception:continue
   if not isinstance(d,dict):continue
   for typ in ['input_boolean','input_number','timer','input_text']:
      for key in (d.get(typ,{}) or {}):
         if re.search(r'water|fountain|garden|security|door|maintenance|dogs',key,re.I):
           print(str(p.relative_to(root)),typ,key)
'''
def inspect():
    arg="exec(__import__('base64').b64decode('"+base64.b64encode(CODE.encode()).decode()+"'))"
    cmd=['qm','guest','exec','905','--','docker','exec','homeassistant','python3','-c',arg]
    response=json.loads(ssh_host('nodeb',cmd))
    pid=response.get('pid')
    for i in range(45):
        if response.get('exited'):break
        if not isinstance(pid,int): raise RuntimeError('guest_agent_initial_pid_missing')
        time.sleep(1)
        response=json.loads(ssh_host('nodeb',['qm','guest','exec-status','905',str(pid)]))
    if not response.get('exited') or response.get('exitcode')!=0:
        raise RuntimeError('guest_audit_failed:'+str(response.get('err-data',''))[:300])
    print(response.get('out-data','')[:90000],flush=True)
if __name__=='__main__':inspect()
