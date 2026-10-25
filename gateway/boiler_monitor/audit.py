#!/usr/bin/env python3
"""Final read-only activation verification after confirmed Core restart."""
import sys,json,urllib.request
sys.path.insert(0,'gateway/boiler_monitor')
from deploy import guest,core
r=guest(['docker','inspect','--format','{{.State.StartedAt}} {{.State.Status}}','homeassistant'])
assert r.get('exitcode')==0 and 'running' in r.get('out-data','')
print('CORE_RUNNING',r.get('out-data','').strip(),flush=True)
P="\nimport pathlib,json,sqlite3,time,datetime\nroot=pathlib.Path('/config')\nids=['binary_sensor.jns_boiler_heating_demand','binary_sensor.jns_boiler_monitoring_available','sensor.jns_boiler_runtime_rate','sensor.jns_boiler_runtime_total','sensor.jns_boiler_runtime_today','sensor.jns_boiler_runtime_this_month']\nreg=json.loads((root/'.storage/core.entity_registry').read_text())['data']['entities']\nregistered={e['entity_id'] for e in reg if not e.get('disabled_by')}\nassert set(ids)<=registered, 'Expected boiler entities not registered'\ncon=sqlite3.connect('file:/config/home-assistant_v2.db?mode=ro',uri=True,timeout=4)\nrows={}\nfor eid in ids:\n row=con.execute('SELECT state,shared_attrs,last_updated_ts FROM states s JOIN states_meta USING(metadata_id) LEFT JOIN state_attributes a ON s.attributes_id=a.attributes_id WHERE entity_id=? ORDER BY last_updated_ts DESC LIMIT 1',(eid,)).fetchone()\n assert row, 'Expected recorded entity missing'\n attrs=json.loads(row[1] or '{}')\n rows[eid]={'state':row[0],'unit':attrs.get('unit_of_measurement'),'state_class':attrs.get('state_class')}\n if eid.startswith('sensor.'):\n  assert row[0] not in ('unknown','unavailable'), 'Runtime sensor not active'\n  float(row[0])\n  if eid!='sensor.jns_boiler_runtime_rate':\n   assert attrs.get('unit_of_measurement')=='h','Runtime hours unit missing'\n   assert attrs.get('state_class') in ('total','total_increasing'),'Long term statistics missing'\ncon.close()\nassert (root/'dashboards/jns_boiler_monitor.yaml').is_file()\nprint('BOILER_LIVE_VERIFIED',json.dumps(rows,sort_keys=True))\n"
print(core(P),flush=True)
for url in ('http://ha-general.home.arpa/','http://ha-general.home.arpa/jns-boiler/usage'):
 try:
  with urllib.request.urlopen(url,timeout=8) as response:
   print('HA_GENERAL_HTTP',url,response.status,flush=True)
 except Exception as exc:
  print('HA_GENERAL_HTTP_UNCONFIRMED',url,type(exc).__name__,flush=True)
print('BOILER_MONITOR_ACTIVATION_VERIFIED',flush=True)
