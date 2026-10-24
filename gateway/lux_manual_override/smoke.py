#!/usr/bin/env python3
"""Read-only smoke-test HA905 new Lux manual-off entities and HA902 sidebar."""
import base64,json,time,sys
sys.path.insert(0,'gateway/arrival_lighting')
from readiness_probe import ssh_host
AUDIT=r"""
from pathlib import Path
import json,yaml
base=Path('/config');entities=json.loads((base/'.storage/core.entity_registry').read_text())['data']['entities']
expected_ids=['jns_lux_record_manual_off_tonight_v1','jns_lux_release_manual_off_at_sunrise_v1']
if VM==905:
 p=base/'packages/jns_lux_manual_off_v1.yaml'
 package=yaml.safe_load(p.read_text()) if p.exists() else {}
 config=yaml.safe_load((base/'automations.yaml').read_text())
 shared=[a for a in config if str(a.get('id'))=='1791918795028']
 snug=[a for a in config if str(a.get('id'))=='1791820842687']
 result={
  'package_present':p.is_file(),
  'manual_capture_automation_registered':[e.get('entity_id') for e in entities if str(e.get('unique_id')) in expected_ids],
  'manual_hold_helpers':[e.get('entity_id') for e in entities if e.get('entity_id') in [
    'input_text.jns_lux_off_tonight_entities','input_boolean.jns_lux_manual_hold_all']],
  'shared_lux_hold_gate_installed':len(shared)==1 and 'jns_lux_off_tonight_entities' in str(shared[0]),
  'snug_lux_hold_gate_installed':len(snug)==1 and 'jns_lux_off_tonight_entities' in str(snug[0]),
  'dashboard_evening_view_installed':'  path: evening-lighting' in (base/'dashboards/testing.yaml').read_text(),
  'package_automation_ids':[a.get('id') for a in package.get('automation',[])],
 }
else:
 cfg=(base/'configuration.yaml').read_text()
 f=base/'dashboards/jns_evening_lighting.yaml'
 result={
  'new_sidebar_entry':('jns-evening-lighting:' in cfg),
  'new_yaml_dashboard_file':f.exists(),
  'preserves_storage_dashboard_mode':('mode: storage' in cfg),
  'linked_to_ha_general':f.exists() and ('ha-general.home.arpa/testing-dashboard/evening-lighting' in f.read_text()),
 }
print(json.dumps(result,sort_keys=True))
"""
for vm,node in ((905,'nodeb'),(902,'nodea')):
 try:
  source=AUDIT.replace("VM==905",str(vm)+"==905")
  arg="exec(__import__('base64').b64decode("+repr(base64.b64encode(source.encode()).decode())+"))"
  result=json.loads(ssh_host(node,['qm','guest','exec',str(vm),'--','docker','exec','homeassistant','python3','-c',arg]))
  pid=result.get('pid')
  for i in range(45):
   if result.get('exited'):break
   if not isinstance(pid,int):raise RuntimeError('QGA PID missing')
   time.sleep(1)
   result=json.loads(ssh_host(node,['qm','guest','exec-status',str(vm),str(pid)]))
  if not result.get('exited') or result.get('exitcode')!=0:raise RuntimeError('Guest verification rejected')
  print('JNS_LUX_SMOKE_VM'+str(vm)+' '+(result.get('out-data') or '')[:2600],flush=True)
 except Exception as exc:
  print('JNS_LUX_SMOKE_VM'+str(vm)+'_BLOCKED '+str(exc)[:180],flush=True)
