#!/usr/bin/env python3
"""JNS Welcome Home read-only inventory. Run as root on Node B or Node A.

Uses existing Proxmox guest agents. No files, services or entities are modified.
Print output locally; do not upload private phone details to public CI logs.
"""
import base64
import json
import shlex
import socket
import subprocess
import time

PRIMARY = r"""
import json
from pathlib import Path
p=Path('/config/.storage')
def r(f,k): return json.loads((p/f).read_text())['data'][k]
entries=r('core.config_entries','entries')
entities=r('core.entity_registry','entities')
devices={d['id']:d for d in r('core.device_registry','devices')}
result={'mobile_apps':[e.get('title') for e in entries if e.get('domain')=='mobile_app'],
        'presence_candidates':[]}
for e in entities:
    eid=e.get('entity_id','')
    d=devices.get(e.get('device_id'),{})
    name=d.get('name_by_user') or d.get('name') or ''
    combined=' '.join([eid,name,str(e.get('original_name') or '')]).lower()
    wanted=(eid.startswith('device_tracker.') or 'bmw' in combined or
            (e.get('platform')=='mobile_app' and
             any(s in combined for s in ('wifi','bluetooth','ssid','network','connection'))))
    if wanted:
        result['presence_candidates'].append(
            {'entity_id':eid,'platform':e.get('platform'),'device':name,
             'original_name':e.get('original_name'),'disabled_by':e.get('disabled_by')})
print(json.dumps(result,ensure_ascii=False))
"""
GENERAL = r"""
import json
from pathlib import Path
import yaml
root=Path('/config')
package=root/'packages/jns_doorbell_security_lighting.yaml'
targets=('switch.0xa4c138bda6ec8ea0','switch.0x84fd27fffe9ce438')
result={'doorbell_package_present':package.exists(),'lighting_automations':[]}
if package.exists():
    data=yaml.safe_load(package.read_text()) or {}
    result['package_sections']=list(data)
    result['package_automation_summary']=[]
    for item in (data.get('automation') or []):
        content=yaml.safe_dump(item,sort_keys=False)
        result['package_automation_summary'].append(
            {'alias':item.get('alias'),'contains_target':any(x in content for x in targets),
             'script_snippet':content[:6000]})
for a in (yaml.safe_load((root/'automations.yaml').read_text()) or []):
    content=yaml.safe_dump(a,sort_keys=False)
    if any(x in content for x in targets):
        result['lighting_automations'].append({'alias':a.get('alias'),'id':a.get('id'),
                                                'script_snippet':content[:6000]})
print(json.dumps(result,ensure_ascii=False))
"""

def local_command(args, timeout=50):
    p=subprocess.run(args,text=True,capture_output=True,timeout=timeout)
    if p.returncode:
        raise RuntimeError((p.stderr or p.stdout)[:500])
    return p.stdout

def on_node(node,args):
    if socket.gethostname().split('.')[0] == node:
        return local_command(args)
    if node not in ('nodea','nodeb','nodec'):
        raise RuntimeError('Unrecognised Proxmox node')
    hostname=node+'.home.arpa'
    opts=['-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=8']
    actual=local_command(['ssh',*opts,'root@'+hostname,'hostname -s'],20).strip()
    if actual != node:
        raise RuntimeError('Remote hostname mismatch')
    return local_command(['ssh',*opts,'root@'+hostname,shlex.join(args)],50)

def guest(node,vm,args):
    result=json.loads(on_node(node,['qm','guest','exec',str(vm),'--',*args]))
    deadline=time.monotonic()+50
    while not result.get('exited'):
        pid=result.get('pid')
        if not isinstance(pid,int) or time.monotonic()>deadline:
            raise RuntimeError('Guest agent returned no exit status or timed out')
        time.sleep(1)
        result=json.loads(on_node(node,['qm','guest','exec-status',str(vm),str(pid)]))
    if result.get('exitcode') != 0:
        raise RuntimeError('VM guest command failed: '+str(result.get('err-data',''))[:700])
    return result.get('out-data','')

def main():
    # Node A and Node B can have independent cluster views.
    # Use known verified VM placement instead of cross-node pvesh enumeration.
    print('=== JNS WELCOME HOME READ-ONLY AUDIT V2 ===',flush=True)
    for vm,node,source in [(902,'nodea',PRIMARY),(905,'nodeb',GENERAL)]:
        print('VM',vm,'known host',node,flush=True)
        try:
            status=on_node(node,['qm','status',str(vm)]).strip()
            print('VM',vm,'local Proxmox status:',status,flush=True)
            if 'status: running' not in status.lower():
                print('VM',vm,'BLOCKED: host reports VM not running; no changes made',flush=True)
                continue
            enc=base64.b64encode(source.encode()).decode()
            pycmd="exec(__import__('base64').b64decode('"+enc+"'))"
            report=json.loads(guest(node,vm,['docker','exec','homeassistant','python3','-c',pycmd]))
            print(json.dumps(report,indent=2,ensure_ascii=False),flush=True)
        except Exception as e:
            print('VM',vm,'BLOCKED:',str(e),flush=True)
            if vm==902:
                print('If SSH from Node B is not trusted, run this audit on Node A directly.',flush=True)
    print('=== AUDIT FINISHED; NO CHANGES MADE ===',flush=True)

if __name__ == '__main__':
    main()
