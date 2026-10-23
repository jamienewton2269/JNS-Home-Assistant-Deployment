#!/usr/bin/env python3
"""Read-only, PII-minimised audit executed on the existing Node C runner."""
import base64
import json
import shlex
import subprocess
import time
NODEMAP={902:"nodea",905:"nodeb"}
INSPECT=r"""
import json
from pathlib import Path
b=Path('/config')
s=b/'.storage'
def entries(file,key):
    return json.loads((s/file).read_text())['data'][key]
es=entries('core.entity_registry','entities')
cs=entries('core.config_entries','entries')
apps=[x for x in cs if x.get('domain')=='mobile_app']
mq=[x for x in cs if x.get('domain')=='mqtt']
mobile=[x for x in es if x.get('platform')=='mobile_app']
track=[x for x in es if x.get('entity_id','').startswith('device_tracker.')]
wifi=[x for x in mobile if any(z in ' '.join([x.get('entity_id',''),str(x.get('original_name') or '')]).lower() for z in ('wifi','ssid','network','connection'))]
bt=[x for x in mobile if 'bluetooth' in ' '.join([x.get('entity_id',''),str(x.get('original_name') or '')]).lower()]
cfg=(b/'configuration.yaml').read_text()
out={
 'mobile_app_count':len(apps),
 'mobile_tracker_count':len([x for x in track if x.get('platform')=='mobile_app']),
 'all_tracker_count':len(track),
 'wifi_entity_count':len(wifi),
 'wifi_enabled_count':len([x for x in wifi if not x.get('disabled_by')]),
 'bluetooth_entity_count':len(bt),
 'bluetooth_enabled_count':len([x for x in bt if not x.get('disabled_by')]),
 'mqtt_config_entries':len(mq),
 'mqtt_statestream_in_root_config':any(x.strip().startswith('mqtt_statestream:') for x in cfg.splitlines()),
 'config_package_include':('packages' in cfg),
 'doorbell_package_exists':(b/'packages/jns_doorbell_security_lighting.yaml').exists(),
}
print(json.dumps(out))
"""
def run(command, timeout=40):
    p=subprocess.run(command,capture_output=True,text=True,timeout=timeout)
    if p.returncode:
        raise RuntimeError("command exited "+str(p.returncode))
    return p.stdout
def ssh_host(node, command):
    for hostname in (node+'.home.arpa',node):
        try:
            base=['ssh','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=5','root@'+hostname]
            check=run(base+['hostname -s'],12).strip()
            if check!=node:
                raise RuntimeError('hostname mismatch')
            return run(base+[shlex.join(command)],60)
        except (RuntimeError,subprocess.TimeoutExpired):
            continue
    # Try Node B as an existing trusted management hop for Node A.
    if node=='nodea':
        for hostname in ('nodea.home.arpa','nodea'):
            inner=['ssh','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=5','root@'+hostname]
            outer=['ssh','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=5','root@nodeb.home.arpa']
            try:
                identity=run(outer+[shlex.join(inner+['hostname -s'])],20).strip()
                if identity!=node: raise RuntimeError('wrong remote node')
                return run(outer+[shlex.join(inner+[shlex.join(command)])],65)
            except (RuntimeError,subprocess.TimeoutExpired):
                pass
    raise RuntimeError("trusted SSH not available for "+node+" (including Node B hop)")
def probe(vm,node):
    try:
        status=ssh_host(node,['qm','status',str(vm)]).strip()
        if 'running' not in status:
            return {'status':'blocked_vm_not_running','host':node}
        payload=base64.b64encode(INSPECT.encode()).decode()
        pycmd="exec(__import__('base64').b64decode('"+payload+"'))"
        q=['qm','guest','exec',str(vm),'--','docker','exec','homeassistant','python3','-c',pycmd]
        output=json.loads(ssh_host(node,q))
        for _ in range(30):
            if output.get('exited'):
                break
            pid=output.get('pid')
            if pid is None:
                raise RuntimeError('missing guest PID')
            time.sleep(1)
            output=json.loads(ssh_host(node,['qm','guest','exec-status',str(vm),str(pid)]))
        if not output.get('exited'):
            raise RuntimeError('guest process did not finish')
        if output.get('exitcode')!=0:
            raise RuntimeError('guest command exit '+str(output.get('exitcode')))
        return {'status':'ok','host':node,**json.loads(output['out-data'])}
    except Exception as e:
        # Do not disclose private entity names or state contents in public workflow logs.
        return {'status':'blocked','host':node,'reason':str(e)[:100]}
def main():
    print('=== JNS WELCOME HOME PREFLIGHT (NO CONFIGURATION WRITES) ===')
    for vm,node in NODEMAP.items():
        print('VM'+str(vm),json.dumps(probe(vm,node),sort_keys=True),flush=True)
    print('=== PREFLIGHT FINISHED ===')
if __name__=='__main__':
    main()
