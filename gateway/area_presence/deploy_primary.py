#!/usr/bin/env python3
"""JNS VM902 presence + MQTT area sync guarded install/check/restart."""
import base64,json,re,sys,time
from pathlib import Path
sys.path.insert(0,'gateway/area_presence')
from primary_runner import guest,install
ROOT=Path('gateway/area_presence')
def core(cmd,seconds=260):
 print('JNS_PRIMARY_HA_START '+str(cmd),flush=True)
 r=guest(['ha',*cmd],seconds)
 out=r.get('out-data') or ''
 print('JNS_PRIMARY_HA_RESULT '+json.dumps({'command':' '.join(cmd),'exitcode':r.get('exitcode'),
       'output_tail':out[-550:],'err_tail':(r.get('err-data') or '')[-350:]}),flush=True)
 return r.get('exitcode')==0
def rollback(manifest):
 rollback_code=(ROOT/'rollback_primary.py').read_bytes()
 expression="exec(compile(__import__('base64').b64decode("+repr(base64.b64encode(rollback_code).decode())+"),'<jns-primary-rollback>','exec'))"
 r=guest(['docker','exec','homeassistant','python3','-c',expression,
    manifest['backup'],json.dumps(manifest['changed_hashes'])],90)
 print('JNS_PRIMARY_ROLLBACK_RESULT '+(r.get('out-data') or '')[-600:],flush=True)
 if r.get('exitcode')!=0:raise RuntimeError('Rollback blocked: '+(r.get('err-data') or '')[-200:])
def main():
 print('JNS_PRIMARY_DEPLOY_BEGIN native MQTT and area sync',flush=True)
 install('--dry-run')
 output=install('--apply')
 m=re.search(r'JNS_PRESENCE_AREA_PRIMARY_APPLIED (\{.*\})',output)
 if not m:raise RuntimeError('No applied manifest found')
 manifest=json.loads(m.group(1))
 if manifest.get('status')!='applied':raise RuntimeError('No successful apply')
 print('JNS_PRIMARY_BACKUP '+manifest['backup'],flush=True)
 try:
  valid=core(['core','check'],260)
 except Exception as exc:
  print('JNS_PRIMARY_CORECHECK_ERROR '+str(exc)[:260],flush=True)
  rollback(manifest)
  raise
 if not valid:
  rollback(manifest)
  raise RuntimeError('HA Primary config check failed; files rolled back; restart not performed')
 print('JNS_PRIMARY_CONFIG_VALID',flush=True)
 # Core restart must complete for new integration/component activation.
 restart=core(['core','restart'],500)
 if not restart:
  raise RuntimeError('Restart exited abnormally; check VM902 Core before attempting another restart')
 print('JNS_PRIMARY_RESTART_DONE',flush=True)
 for n in range(9):
  time.sleep(9)
  try:
   if core(['core','info'],55):
    print('JNS_PRIMARY_CORE_INFO_OK',flush=True)
    break
  except Exception as e:print('JNS_PRIMARY_CORE_HEALTH_RETRY '+type(e).__name__,flush=True)
 else:raise RuntimeError('Core health not confirmed after restart')
 print('JNS_PRIMARY_MQTT_AREA_DEPLOY_DONE - area sync starts preview only',flush=True)
if __name__=='__main__':
 try:main()
 except Exception as e:
  print('JNS_PRIMARY_DEPLOY_FAILED '+type(e).__name__+': '+str(e)[:350],flush=True)
  raise SystemExit(1)
