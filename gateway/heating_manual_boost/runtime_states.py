#!/usr/bin/env python3
"""Authenticated *read-only* HA-General runtime state probe, token never logged.

Runs in existing Home Assistant container via QGA; uses only the in-container
Supervisor credential, if present. Never exports credential from VM905.
"""
import base64,importlib.util,json,pathlib
spec=importlib.util.spec_from_file_location("bridge",pathlib.Path("gateway/heating_presence/deploy.py"))
bridge=importlib.util.module_from_spec(spec);spec.loader.exec_module(bridge)
INNER=r"""
import os,json,urllib.request,urllib.error
token=os.environ.get('SUPERVISOR_TOKEN','')
entities=[
 'input_boolean.jns_heating_manual_setpoint_hold',
 'input_number.jns_heating_manual_target',
 'input_number.jns_heating_last_automatic_target',
 'input_datetime.jns_heating_last_auto_command_time',
 'sensor.jns_heating_active_requested_target',
 'automation.jns_heating_follow_honeywell_thermostat_and_dashboard_setpoint',
 'automation.jns_heating_restore_minimum_on_leaving_home',
 'automation.jns_heating_explicit_bedtime_activation_ends_earlier_manual_hold',
 'climate.thermostat_thermostat']
if not token:
 print('JNS_HEATING_STATE_AUDIT '+json.dumps({'auth':'no_in_container_supervisor_token','checked':False}))
else:
 base='http://supervisor/core/api'
 results={}
 for e in entities:
  req=urllib.request.Request(base+'/states/'+e,
     headers={'Authorization':'Bearer '+token,'Accept':'application/json'})
  try:
   with urllib.request.urlopen(req,timeout=6) as response:
    data=json.load(response)
   results[e]={'status':'ok','present':True,
                'enabled':data.get('state')!='unavailable',
                'state':data.get('state') if e.startswith('input_boolean.') else '[not logged]'}
  except urllib.error.HTTPError as ex:
   results[e]={'status':ex.code,'present':False}
  except Exception as ex:
   results[e]={'status':type(ex).__name__,'present':False}
 print('JNS_HEATING_STATE_AUDIT '+json.dumps({'auth':'local-only',
 'states':results},sort_keys=True))
"""
def main():
 out=bridge.core(INNER,seconds=120)
 if out.get('exitcode')!=0:raise RuntimeError("VM905 read-only state audit failed")
 text=out.get('out-data') or ''
 if not text.startswith('JNS_HEATING_STATE_AUDIT '):raise RuntimeError("Unexpected VM905 state audit result")
 print(text,flush=True)
if __name__=="__main__":main()
