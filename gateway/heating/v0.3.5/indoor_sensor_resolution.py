#!/usr/bin/env python3
"""Read-only VM905 room-temperature sensor resolution inventory; no HA writes."""
import base64,json,sys,time
sys.path.insert(0,"gateway/arrival_lighting")
from readiness_probe import ssh_host
INNER=r"""
import json,sqlite3,pathlib,datetime,re,collections
root=pathlib.Path('/config')
entities=json.loads((root/'.storage/core.entity_registry').read_text())['data']['entities']
devices=json.loads((root/'.storage/core.device_registry').read_text())['data']['devices']
areas=json.loads((root/'.storage/core.area_registry').read_text())['data']['areas']
areaname={x['id']:x.get('name') for x in areas}
devmap={d['id']:d for d in devices}
relevant=[]
for e in entities:
 eid=e.get('entity_id','')
 if not eid.startswith('sensor.'):continue
 if e.get('disabled_by'):continue
 label=' '.join(str(e.get(k) or '') for k in ('entity_id','name','original_name'))
 if not re.search(r'temperature|_temp\b',label,re.I):continue
 if re.search(r'cpu|processor|disk|ssd|battery|solar|setpoint|heating_temp_target',label,re.I):continue
 dev=devmap.get(e.get('device_id'),{})
 area=areaname.get(e.get('area_id') or dev.get('area_id'))
 relevant.append({'entity_id':eid,'device_name':dev.get('name_by_user') or dev.get('name'),
                  'area':area,'platform':e.get('platform')})
out={'total_temperature_entities':len(relevant),'candidates':[]}
db=root/'home-assistant_v2.db'
if db.is_file():
 try:
  con=sqlite3.connect('file:'+str(db)+'?mode=ro',uri=True,timeout=5)
  now=datetime.datetime.now(datetime.timezone.utc).timestamp()
  for item in relevant[:75]:
   eid=item['entity_id']
   try:
    rows=con.execute('SELECT s.state,s.last_updated_ts FROM states s JOIN states_meta m ON m.metadata_id=s.metadata_id WHERE m.entity_id=? ORDER BY s.last_updated_ts DESC LIMIT 160',(eid,)).fetchall()
   except Exception:continue
   numeric=[]
   for state,ts in rows:
    try:
     v=float(state)
     if -15<=v<=55:numeric.append((v,ts))
    except (ValueError,TypeError):pass
   if not numeric:continue
   levels=sorted(set(v for v,_ in numeric))
   diffs=[b-a for a,b in zip(levels,levels[1:]) if b>a]
   item.update({'latest_c':numeric[0][0],'latest_change_age_minutes':
          round((now-numeric[0][1])/60,1) if numeric[0][1] else None,
          'history_numeric_points':len(numeric),'distinct_history_values':len(levels),
          'resolution_c':round(min(diffs),3) if diffs else None,
          'history_span_c':round(max(levels)-min(levels),2)})
   out['candidates'].append(item)
  con.close()
 except Exception as exc:out['recorder_error']=type(exc).__name__
out['candidates'].sort(key=lambda x:(x['resolution_c'] is None or x['resolution_c']>=.5,
                                  x['latest_change_age_minutes'] or 999999))
print(json.dumps(out,sort_keys=True))
"""
expr="exec(__import__('base64').b64decode('"+base64.b64encode(INNER.encode()).decode()+"'))"
r=json.loads(ssh_host("nodeb",["qm","guest","exec","905","--","docker","exec","homeassistant","python3","-c",expr]))
limit=time.monotonic()+100
while not r.get("exited"):
 if not isinstance(r.get("pid"),int) or time.monotonic()>limit:raise RuntimeError("read-only temp inventory timeout")
 time.sleep(1);r=json.loads(ssh_host("nodeb",["qm","guest","exec-status","905",str(r["pid"])]))
if r.get("exitcode")!=0:raise RuntimeError("temperature inventory failed")
data=json.loads(r.get("out-data") or "{}")
print("JNS_HEATING_INDOOR_SENSOR_RESOLUTION",json.dumps(data,sort_keys=True))
