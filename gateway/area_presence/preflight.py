#!/usr/bin/env python3
"""Read-only MQTT area catalogue and presence transport audit on Node C runner.
Do not print SSIDs, auth tokens, MQTT passwords or phone location states.
"""
import base64,json,shlex,subprocess,sys,time
sys.path.insert(0,'gateway/arrival_lighting')
from readiness_probe import ssh_host

PROBE=r"""
from pathlib import Path
import json, yaml
root=Path('/config'); st=root/'.storage'
es=json.loads((st/'core.entity_registry').read_text())['data']['entities']
cs=json.loads((st/'core.config_entries').read_text())['data']['entries']
cfg=(root/'configuration.yaml').read_text()
areas=json.loads((st/'core.area_registry').read_text())['data']['areas']
home=(root/'packages/jns_welcome_home.yaml')
out={
 'mqtt_config_entries':[{'disabled_by':x.get('disabled_by'),'source':x.get('source'),'state':x.get('state')} for x in cs if x.get('domain')=='mqtt'],
 'mqtt_statestream_top_level':any(x.startswith('mqtt_statestream:') for x in cfg.splitlines()),
 'root_config_has_packages':('packages' in cfg),
 'area_count':len(areas),
 'area_ids':[x.get('id') for x in areas],
 'welcome_package_exists':home.exists(),
 'welcome_automation_registry_ids':[
  x.get('entity_id') for x in es if x.get('platform')=='automation' and
  ('welcome_home' in str(x.get('entity_id')) or 'jns_welcome_home' in str(x.get('unique_id')))],
 'mobile_entities':[
   {'entity_id':x['entity_id'],'disabled_by':x.get('disabled_by')}
   for x in es if x.get('platform')=='mobile_app' and x.get('entity_id') in
   ['device_tracker.sm_s721b','sensor.sm_s721b_wi_fi_connection']],
 'named_local_packages':[p.name for p in (root/'packages').glob('*.yaml') if any(w in p.name for w in ('area','mqtt','welcome','presence'))],
 'named_local_scripts':[p.name for p in (root/'').glob('*area*') if p.is_file()],
}
try:
 c=yaml.safe_load(cfg)
 out['mqtt_statestream_yaml_type']=type(c.get('mqtt_statestream')).__name__ if isinstance(c,dict) else None
except Exception as exc:
 out['config_yaml_parse_error']=type(exc).__name__
print(json.dumps(out,sort_keys=True))
"""
def execute(vm,node,script):
    arg="exec(__import__('base64').b64decode('"+base64.b64encode(script.encode()).decode()+"'))"
    resp=json.loads(ssh_host(node,['qm','guest','exec',str(vm),'--','docker','exec','homeassistant','python3','-c',arg]))
    pid=resp.get('pid')
    for _ in range(48):
        if resp.get('exited'):break
        if not isinstance(pid,int): raise RuntimeError('missing_initial_guest_pid')
        time.sleep(1)
        resp=json.loads(ssh_host(node,['qm','guest','exec-status',str(vm),str(pid)]))
    if not resp.get('exited') or resp.get('exitcode')!=0:
        raise RuntimeError('guest_read_failed: '+(resp.get('err-data') or '')[-320:])
    return json.loads(resp.get('out-data') or '{}')
def cmd(args,timeout=25):
    p=subprocess.run(args,text=True,capture_output=True,timeout=timeout)
    return {'rc':p.returncode,'stdout':p.stdout[-10000:],'stderr':p.stderr[-400:]}
for vm,node in [(902,'nodea'),(905,'nodeb'),(906,'nodec')]:
    try:
        if vm==906:
            # VM906 owned by Node C; confirm host first.
            host=subprocess.run(['hostname','-s'],capture_output=True,text=True,timeout=3).stdout.strip()
            if host!='nodec': raise RuntimeError('not trusted nodec runner')
            local=subprocess.run(['qm','status','906'],capture_output=True,text=True,timeout=10)
            if local.returncode!=0:raise RuntimeError('Node C qm control unavailable')
            # Use local qm guest agent without exposing sensitive config.
            encoded=base64.b64encode(PROBE.encode()).decode()
            q=subprocess.run(['qm','guest','exec','906','--','docker','exec','homeassistant','python3','-c',"exec(__import__('base64').b64decode('"+encoded+"'))"],capture_output=True,text=True,timeout=50)
            if q.returncode:raise RuntimeError('Node C VM906 QGA unavailable')
            resp=json.loads(q.stdout)
            pid=resp.get('pid')
            for i in range(35):
                if resp.get('exited'):break
                if not isinstance(pid,int): raise RuntimeError('VM906 missing QGA pid')
                time.sleep(1)
                resp=json.loads(subprocess.run(['qm','guest','exec-status','906',str(pid)],capture_output=True,text=True,timeout=30).stdout)
            if not resp.get('exited') or resp.get('exitcode')!=0:raise RuntimeError('VM906 HA guest not available')
            result=json.loads(resp.get('out-data') or '{}')
        else:result=execute(vm,node,PROBE)
        print('JNS_AREA_BRIDGE_VM'+str(vm)+' '+json.dumps(result,sort_keys=True),flush=True)
    except Exception as exc:
        print('JNS_AREA_BRIDGE_VM'+str(vm)+'_BLOCKED '+str(exc)[:230],flush=True)
try:
    p=cmd(['ssh','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=5',
           'root@nodeb.home.arpa','pct exec 212 -- timeout 10 mosquitto_sub -h mqtt-infra-a.home.arpa -p 1883 -t jns/site/areas/catalogue -C 1'],20)
    if p['rc']==0:
        data=json.loads(p['stdout'])
        print('JNS_MQTT_AREA_CATALOGUE '+json.dumps({
            'schema':data.get('schema'),'source':data.get('source'),
            'generated_at':data.get('generated_at'),
            'area_count':len(data.get('areas',[])),
            'area_ids':[a.get('id') for a in data.get('areas',[]) if isinstance(a,dict)]
          },sort_keys=True),flush=True)
    else: print('JNS_MQTT_AREA_CATALOGUE_BLOCKED '+str(p['rc'])+' '+p['stderr'][:120],flush=True)
except Exception as exc:print('JNS_MQTT_AREA_CATALOGUE_BLOCKED '+str(exc)[:130],flush=True)
