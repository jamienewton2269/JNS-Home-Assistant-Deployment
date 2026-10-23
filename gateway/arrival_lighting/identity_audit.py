#!/usr/bin/env python3
"""JNS Welcome Home exact-mapping audit. No writes; avoid any tokens / credentials."""
import readiness_probe as rp
import base64,json,time
PRIMARY=r"""
import json
from pathlib import Path
s=Path('/config/.storage')
entities=json.loads((s/'core.entity_registry').read_text())['data']['entities']
devices={d['id']:d for d in json.loads((s/'core.device_registry').read_text())['data']['devices']}
apps=[e for e in entities if e.get('platform')=='mobile_app']
res=[]
for e in apps:
    eid=e.get('entity_id','')
    words=('device_tracker.','wifi','ssid','bluetooth','network','connection')
    if any(w in eid.lower() for w in words):
        res.append(dict(entity_id=eid,original_name=e.get('original_name'),
          disabled_by=e.get('disabled_by'),
          device=devices.get(e.get('device_id'),{}).get('name') or '<unnamed>'))
print(json.dumps({'mobile_candidates':res,'all_trackers':[e.get('entity_id') for e in entities if e.get('entity_id','').startswith('device_tracker.')]},ensure_ascii=False))
"""
GENERAL=r"""
import json,re
from pathlib import Path
p=Path('/config/configuration.yaml')
text=p.read_text()
lines=text.splitlines()
result={'remote_key_lines':[],
        'has_mqtt_statestream':any(x.strip().startswith('mqtt_statestream:') for x in lines)}
for i,line in enumerate(lines,1):
    if re.match(r'^(remote_homeassistant|remote_home_assistant|homeassistant|mqtt|automation|script|timer):',line):
        result['remote_key_lines'].append((i,line))
    elif re.match(r'^\s{2,6}(host|entity_prefix|include|exclude|entities|domains|entity_globs|prefix|filter|mode|servers|platform):',line):
        # names/keys only. Never print values that may be hostnames or credentials.
        result['remote_key_lines'].append((i,line.split(':')[0]+': [REDACTED]'))
print(json.dumps(result))
"""
def run(vm,node,body):
    status=rp.ssh_host(node,['qm','status',str(vm)])
    if 'running' not in status: raise RuntimeError('VM not running')
    enc=base64.b64encode(body.encode()).decode()
    pycmd="exec(__import__('base64').b64decode('"+enc+"'))"
    q=['qm','guest','exec',str(vm),'--','docker','exec','homeassistant','python3','-c',pycmd]
    response=json.loads(rp.ssh_host(node,q))
    for _ in range(40):
        if response.get('exited'): break
        pid=response.get('pid')
        if pid is None: raise RuntimeError('Guest returned no pid')
        time.sleep(1)
        response=json.loads(rp.ssh_host(node,['qm','guest','exec-status',str(vm),str(pid)]))
    if response.get('exitcode')!=0 or not response.get('exited'):
        raise RuntimeError('Guest script failed')
    return json.loads(response['out-data'])
for vm,node,body in ((902,'nodea',PRIMARY),(905,'nodeb',GENERAL)):
    try:
        print('VM'+str(vm),json.dumps(run(vm,node,body),ensure_ascii=False),flush=True)
    except Exception as e:
        print('VM'+str(vm),'BLOCKED',str(e)[:200],flush=True)
