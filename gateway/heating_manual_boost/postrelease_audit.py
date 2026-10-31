#!/usr/bin/env python3
"""Non-mutating post-release inspection, no API token or thermostat calls."""
import base64,importlib.util,json,pathlib,time
spec=importlib.util.spec_from_file_location("jns_heating_bridge",
 pathlib.Path("gateway/heating_presence/deploy.py"))
bridge=importlib.util.module_from_spec(spec);spec.loader.exec_module(bridge)
INNER=r"""
from pathlib import Path
import hashlib,json,yaml
R=Path('/config')
p=R/'packages/jns_heating_predictive_schedule.yaml'
registry=json.loads((R/'.storage/core.entity_registry').read_text())['data']['entities']
have={e.get('entity_id'):e for e in registry}
wanted=[
'input_boolean.jns_heating_manual_setpoint_hold',
'input_number.jns_heating_manual_target',
'input_number.jns_heating_last_automatic_target',
'input_datetime.jns_heating_last_auto_command_time',
'sensor.jns_heating_active_requested_target']
expected=[
'jns_heating_capture_honeywell_manual_target_v1',
'jns_heating_clear_old_manual_hold_on_away_v1',
'jns_heating_clear_manual_hold_on_bedtime_v1']
registered={e.get('unique_id') for e in registry if e.get('platform')=='automation' and not e.get('disabled_by')}
result={
 "vm":905,
 "file_sha256":hashlib.sha256(p.read_bytes()).hexdigest(),
 "package_yaml_parseable":isinstance(yaml.safe_load(p.read_text()),dict),
 "registry_helper_presence":{e:e in have for e in wanted},
 "registry_automation_unique_id_presence":{e:e in registered for e in expected},
 "automation_platform_count":len([e for e in registry if e.get('platform')=='automation']),
 "selected_entity_ids":[e.get('entity_id') for e in registry
  if e.get('platform')=='automation' and
     ('honeywell' in e.get('entity_id','') or 'jns_heating' in e.get('entity_id',''))][:18],
 "core_running":True}
print("JNS_HEATING_POSTRELEASE_AUDIT "+json.dumps(result,sort_keys=True),flush=True)
"""
def main():
 r=bridge.core(INNER,seconds=90)
 if r.get('exitcode')!=0:
  print("JNS_HEATING_POSTRELEASE_AUDIT_FAILED")
  raise RuntimeError("Read-only Core container diagnosis rejected")
 out=r.get('out-data') or ''
 if not out.startswith("JNS_HEATING_POSTRELEASE_AUDIT "):
  raise RuntimeError("Unknown audit response")
 print(out,flush=True)
if __name__=="__main__":main()
