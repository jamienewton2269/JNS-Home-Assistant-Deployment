#!/usr/bin/env python3
"""Read-only independent verification of JNS VM905 Lux Priority Ladder after startup."""
import base64,json,time,sys
sys.path.insert(0,"gateway/arrival_lighting")
from readiness_probe import ssh_host
CHECK=r'''
import pathlib,json,yaml,hashlib,sqlite3,urllib.request,urllib.error
R=pathlib.Path('/config'); p=R/'packages/jns_lux_priority_ladder.yaml'
assert p.is_file()
a=yaml.safe_load((R/'automations.yaml').read_text())
x=[v for v in a if str(v.get('id'))=='1791918795028']
assert len(x)==1 and 'JNS_LUX_PRIORITY_LADDER_V1' in x[0].get('description','')
d=yaml.safe_load((R/'dashboards/testing.yaml').read_text())
view=[v for v in d['views'] if v.get('path')=='lux-priorities']
assert len(view)==1 and len(view[0]['cards'])>=3
reg=json.loads((R/'.storage/core.entity_registry').read_text())['data']['entities']
present={e.get('entity_id') for e in reg if not e.get('disabled_by')}
required=['input_boolean.jns_lux_ladder_initialized','input_number.jns_lux_ladder_stage_gap',
'binary_sensor.jns_lux_priority_bright_stable',
'automation.jns_lux_initialize_priority_ladder_only_once']
names=['hall','front','worktop','snug','radiator','tripod','living','sofa']
for n in names:required+=['input_boolean.jns_lux_include_'+n,'input_number.jns_lux_rank_'+n]
missing=[e for e in required if e not in present]
db=sqlite3.connect('file:'+str(R/'home-assistant_v2.db')+'?mode=ro',uri=True,timeout=4)
ids=required+['input_number.general_outdoor_lighting_on_lux','input_number.general_lux_priority_boost',
            'automation.general_shared_lux_progressive_control']
rows=db.execute("SELECT m.entity_id,s.state FROM states s JOIN states_meta m ON s.metadata_id=m.metadata_id WHERE m.entity_id IN ("+','.join('?'*len(ids))+") ORDER BY s.last_updated_ts DESC LIMIT 1000",ids).fetchall()
states={}
for eid,state in rows:
 if eid not in states:states[eid]=state
db.close()
initial={n:states.get('input_boolean.jns_lux_include_'+n) for n in names}
ranks={n:states.get('input_number.jns_lux_rank_'+n) for n in names}
assert states.get('input_boolean.jns_lux_ladder_initialized')=='on','One-time initialisation not completed'
assert all(initial[n]=='on' for n in names[:6]),'Existing Lux lights not enabled'
assert initial['living']=='off' and initial['sofa']=='off','Optional lights not disabled'
assert [float(ranks[n]) for n in names]==list(map(float,range(1,9))),'Rank bootstrap unexpected'
assert states.get('input_number.jns_lux_ladder_stage_gap')=='350.0','Stage gap bootstrap unexpected'
assert not missing, 'Missing registered entities '+str(missing)
try:
 with urllib.request.build_opener(urllib.request.ProxyHandler({})).open('http://127.0.0.1:80/api/',timeout=5) as r: http=r.status
except urllib.error.HTTPError as e:http=e.code
except Exception as e:http=type(e).__name__
assert http in (200,401),'Core API not ready'
print('JNS_LUX_LADDER_POSTCHECK_OK',json.dumps({'core_http':http,'config_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),
'main_controller_enabled':x[0].get('mode')=='restart','registered_count':len(required),'missing':missing,
'bootstrap':states.get('input_boolean.jns_lux_ladder_initialized'),'enabled':initial,'priorities':ranks,
'stage_gap_lux':states.get('input_number.jns_lux_ladder_stage_gap'),
'live_bright_sensor_registered':True,'dashboard_view':'Lux Priorities'},sort_keys=True))
'''
def guest(args,seconds=75):
 r=json.loads(ssh_host('nodeb',['qm','guest','exec','905','--',*args]))
 until=time.monotonic()+seconds
 while not r.get('exited'):
  if not isinstance(r.get('pid'),int):raise RuntimeError('Missing QGA PID')
  if time.monotonic()>until:raise RuntimeError('QGA read-only job timed out')
  time.sleep(2)
  r=json.loads(ssh_host('nodeb',['qm','guest','exec-status','905',str(r['pid'])]))
 return r
print('JNS_LUX_INDEPENDENT_VERIFY_VM905',ssh_host('nodeb',['qm','status','905']).strip(),flush=True)
cmd="exec(__import__('base64').b64decode("+repr(base64.b64encode(CHECK.encode()).decode())+"))"
r=guest(['docker','exec','homeassistant','python3','-c',cmd])
print('JNS_LUX_INDEPENDENT_VERIFY_RESULT',(r.get('out-data') or '')[-6500:],flush=True)
if r.get('exitcode')!=0:raise RuntimeError('Independent check failed '+(r.get('err-data') or '')[-650:])
