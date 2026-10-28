#!/usr/bin/env python3
"""Second read-only HA905 alarm source/dashboard introspection; no write."""
import sys,base64,json,time
sys.path.insert(0,'gateway/arrival_lighting')
from readiness_probe import ssh_host
CODE=r'''
import pathlib,re,json,yaml,sqlite3,datetime
R=pathlib.Path('/config')
out={}
out['yaml_dashboard_locations']=[]
raw_config=(R/'configuration.yaml').read_text()
out['lovelace_config_lines']=[{'line':i+1,'text':x[:210]} for i,x in enumerate(raw_config.splitlines()) if re.search(r'lovelace:|dashboards:|mode:|filename:|testing.yaml|general.yaml',x)][:25]
for p in [R/'dashboards/general.yaml',R/'dashboards/testing.yaml']:
 raw=p.read_text()
 try:v=yaml.safe_load(raw)
 except Exception as e:out.setdefault('dashboard_errors',[]).append(type(e).__name__);v={}
 views=v.get('views',[]) if isinstance(v,dict) else []
 panel=[]
 for view in views:
  title=view.get('title');path=view.get('path');cards=view.get('cards',[])
  panel.append({'title':title,'path':path,'cards':[{'type':c.get('type'),'title':c.get('title'),'entities':str(c.get('entities',[]))[:550]} for c in cards if isinstance(c,dict) and (re.search(r'heat|alarm|control|house|bedtime',str(c.get('title','')),re.I) or any(t in str(c.get('entities','')) for t in ['climate.','alarm_control_panel.','general_bedtime_mode']))][:25]})
 out['yaml_dashboard_locations'].append({'path':str(p.relative_to(R)),'views':panel[:18]})
 alarm_match=[{'line':i+1,'text':s[:230]} for i,s in enumerate(raw.splitlines()) if 'alarm_control_panel.' in s or ('Heating' in s and 'title' in s)]
 out[str(p.name)+'_alarm_hits']=alarm_match[:18]
for p in [R/'automations.yaml']:
 lines=p.read_text().splitlines()
 i=[i for i,x in enumerate(lines) if 'alarm_control_panel.home_alarm' in x]
 out['existing_away_garden_automation']=[lines[max(0,i[0]-10):i[0]+11]] if i else []
restore=R/'.storage/core.restore_state'
if restore.exists():
 try:
  data=json.loads(restore.read_text())
  records=data.get('data',{}).get('states',[])
  out['restored_alarm_states']=[{'id':x.get('state',{}).get('entity_id'),'state':x.get('state',{}).get('state'),'last_updated':x.get('state',{}).get('last_updated')} for x in records if x.get('state',{}).get('entity_id','').startswith('alarm_control_panel.')][:12]
 except Exception as e:out['restore_read_error']=type(e).__name__
p=R/'home-assistant_v2.db'
if p.exists():
 try:
  conn=sqlite3.connect('file:'+str(p)+'?mode=ro',uri=True,timeout=5)
  q="SELECT m.entity_id,s.state,s.last_updated_ts FROM states s JOIN states_meta m ON m.metadata_id=s.metadata_id WHERE m.entity_id LIKE 'alarm_control_panel.%' ORDER BY s.last_updated_ts DESC LIMIT 12"
  rows=conn.execute(q).fetchall()
  out['recorder_alarm_history']=[{'id':a,'state':b,'time_utc':datetime.datetime.fromtimestamp(t,datetime.timezone.utc).isoformat() if t else None} for a,b,t in rows]
  conn.close()
 except Exception as e:out['recorder_error']=type(e).__name__
base=R/'custom_components/jns_heating_zones'
out['heating_engine_files']=[str(p.relative_to(R)) for p in base.rglob('*.py')][:45] if base.is_dir() else []
for f in list(base.glob('*.py')) if base.is_dir() else []:
 try:lines=f.read_text().splitlines()
 except:continue
 rx=re.compile(r'climate\.set_temperature|async_call|preheat|prediction|predictive|setpoint|target_temp|schedule|lead_time|forecast|comfort|morning|learn',re.I)
 hits=[{'line':i+1,'text':x[:170]} for i,x in enumerate(lines) if rx.search(x)]
 if hits:out.setdefault('heating_engine_refs',{})[str(f.relative_to(R))]=hits[:70]
print('JNS_ALARM_DASH_DETAIL',json.dumps(out,default=str))
'''
def guest(args):
 r=json.loads(ssh_host('nodeb',['qm','guest','exec','905','--',*args]))
 for _ in range(40):
  if r.get('exited'):return r
  if not isinstance(r.get('pid'),int):raise RuntimeError('no QGA PID')
  time.sleep(1)
  r=json.loads(ssh_host('nodeb',['qm','guest','exec-status','905',str(r['pid'])]))
 raise RuntimeError('timeout')
code="exec(__import__('base64').b64decode("+repr(base64.b64encode(CODE.encode()).decode())+"))"
r=guest(['docker','exec','homeassistant','python3','-c',code])
print('JNS_ALARM_DASH_DETAIL_RESULT',(r.get('out-data') or '')[-17000:],flush=True)
if r.get('exitcode')!=0:raise RuntimeError((r.get('err-data') or '')[-400:])
