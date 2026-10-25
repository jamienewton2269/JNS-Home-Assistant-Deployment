#!/usr/bin/env python3
"""Post-restart HA-General health read-only check; no configuration writes."""
import json,sys,time
sys.path.insert(0,'gateway/arrival_lighting')
from readiness_probe import ssh_host
checks={}
checks['vm905']=ssh_host('nodeb',['qm','status','905']).strip()
def guest(argv):
 result=json.loads(ssh_host('nodeb',['qm','guest','exec','905','--',*argv]))
 pid=result.get('pid')
 for i in range(25):
  if result.get('exited'):break
  if not isinstance(pid,int):raise RuntimeError('guest pid missing')
  time.sleep(1)
  result=json.loads(ssh_host('nodeb',['qm','guest','exec-status','905',str(pid)]))
 return {'exitcode':result.get('exitcode'),'out':(result.get('out-data') or '')[:1700]}
checks['docker_running']=guest(['docker','inspect','-f','{{.State.Running}}','homeassistant'])
checks['core_info']=guest(['ha','core','info','--raw-json'])
checks['nodeb_http']=ssh_host('nodeb',['curl','-sS','-o','/dev/null','-w','%{http_code}','--max-time','7','http://ha-general.home.arpa/']).strip()
print('JNS_SENSOR_NAMES_POST_HEALTH '+json.dumps(checks),flush=True)
if 'running' not in checks['vm905'] or checks['docker_running']['out'].strip()!='true':
 raise SystemExit('HA-General VM/Core not running')
if checks['core_info']['exitcode']!=0:raise SystemExit('HA-Core info unavailable')
if checks['nodeb_http'] not in ('200','301','302','307','308','401'):
 raise SystemExit('HA-General HTTP unhealthy')
print('JNS_SENSOR_NAMES_POST_HEALTH_VERIFIED',flush=True)
