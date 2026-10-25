#!/usr/bin/env python3
import sys,json
sys.path.insert(0,'gateway/boiler_monitor')
from deploy import guest,core
r=guest(['docker','inspect','--format','{{.State.StartedAt}} {{.State.Status}}','homeassistant'])
print('CORE_CONTAINER_STATE',r.get('exitcode'),r.get('out-data','').strip(),flush=True)
P="\nimport pathlib,json,sqlite3,time,datetime\nroot=pathlib.Path('/config')\nids=['binary_sensor.jns_boiler_heating_demand','binary_sensor.jns_boiler_monitoring_available','sensor.jns_boiler_runtime_rate','sensor.jns_boiler_runtime_total','sensor.jns_boiler_runtime_today','sensor.jns_boiler_runtime_this_month']\nreg=json.loads((root/'.storage/core.entity_registry').read_text())['data']['entities']\nregistered={e['entity_id'] for e in reg if not e.get('disabled_by')}\nassert set(ids)<=registered, 'Expected boiler entities not registered'\ncon=sqlite3.connect('file:/config/home-assistant_v2.db?mode=ro',uri=True,timeout=4)\nrows={}\nfor eid in ids:\n row=con.execute('SELECT state,shared_attrs,last_updated_ts FROM states s JOIN states_meta USING(metadata_id) LEFT JOIN state_attributes a ON s.attributes_id=a.attributes_id WHERE entity_id=? ORDER BY last_updated_ts DESC LIMIT 1',(eid,)).fetchone()\n assert row, 'Expected recorded entity missing'\n attrs=json.loads(row[1] or '{}')\n rows[eid]={'state':row[0],'unit':attrs.get('unit_of_measurement'),'state_class':attrs.get('state_class')}\n if eid.startswith('sensor.'):\n  assert row[0] not in ('unknown','unavailable'), 'Runtime sensor not active'\n  float(row[0])\n  if eid!='sensor.jns_boiler_runtime_rate':\n   assert attrs.get('unit_of_measurement')=='h','Runtime hours unit missing'\n   assert attrs.get('state_class') in ('total','total_increasing'),'Long term statistics missing'\ncon.close()\nassert (root/'dashboards/jns_boiler_monitor.yaml').is_file()\nprint('BOILER_LIVE_VERIFIED',json.dumps(rows,sort_keys=True))\n"
try:print(core(P),flush=True)
except Exception as e:print('BOILER_READONLY_VERIFICATION_PENDING',type(e).__name__,str(e)[:150],flush=True)
Q=r"""
import pathlib,re,json
p=pathlib.Path('/tmp/jns-boiler-restart-40221940397.out')
s=p.read_text() if p.exists() else ''
print('RESTART_RESPONSE',json.dumps(s[:300] if not re.search('token|secret|password|bearer',s,re.I) else '[REDACTED]'))
root=pathlib.Path('/config')
print('MONITOR_FILES_PRESENT',[(x,(root/x).is_file()) for x in ('packages/jns_boiler_monitor.yaml','dashboards/jns_boiler_monitor.yaml')])
log=root/'home-assistant.log'
if log.exists():
 lines=log.read_text(errors='replace').splitlines()[-2000:]
 print('BOILER_LOG_ERRORS',json.dumps([x[:250] for x in lines if 'boiler' in x.lower() and any(z in x for z in ('ERROR','WARNING')) and not re.search('token|secret|password|bearer',x,re.I)][-10:]))
"""
print(core(Q),flush=True)
