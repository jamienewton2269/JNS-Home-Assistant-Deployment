#!/usr/bin/env python3
"""Read-only live inspect HA-General remote_homeassistant block and installed component."""
import readiness_probe as rp
import base64,json,time
SRC=r"""
from pathlib import Path
import json,re
p=Path('/config/configuration.yaml')
lines=p.read_text().splitlines()
start=next((i for i,line in enumerate(lines) if line.startswith('remote_homeassistant:')),None)
out={'remote_present':start is not None}
if start is not None:
    b=[]
    for line in lines[start+1:]:
        if line and not line[0].isspace() and not line.startswith('#'): break
        m=re.match(r'^(\s*)([\w_-]+):(\s*)(.*)$',line)
        if m:
            key=m.group(2)
            # Never expose remote endpoint or secret values.
            val=m.group(4)
            safe=(key in ('mode','entity_prefix','entity_globs','entities','domains','entity_category','scan_interval','filter'))
            if key in ('mode','entity_prefix'): safe=True
            if 'token' in key or 'password' in key or 'key' in key: safe=False
            b.append({'indent':len(m.group(1)),'key':key,'value':val[:80] if safe else '[redacted]'})
        elif line.lstrip().startswith('- '):
            val=line.strip()[2:]
            b.append({'list_item':val[:80] if ('device_tracker' in val or 'sensor.' in val or 'include:' in val or 'exclude:' in val) else '[redacted]'})
    out['remote_structure']=b
component=Path('/config/custom_components/remote_homeassistant')
out['component_exists']=component.is_dir()
manifest=component/'manifest.json'
if manifest.exists():
    d=json.loads(manifest.read_text())
    out['manifest_version']=d.get('version')
es=json.loads(Path('/config/.storage/core.entity_registry').read_text())['data']['entities']
out['remote_entity_matches']=[e['entity_id'] for e in es if e.get('platform')=='remote_homeassistant' or 'sm_s721b' in e.get('entity_id','') or e.get('entity_id','').startswith('device_tracker.')]
print(json.dumps(out))
"""
def guest():
    enc=base64.b64encode(SRC.encode()).decode()
    p="exec(__import__('base64').b64decode('"+enc+"'))"
    q=['qm','guest','exec','905','--','docker','exec','homeassistant','python3','-c',p]
    r=json.loads(rp.ssh_host('nodeb',q))
    for _ in range(40):
        if r.get('exited'): break
        time.sleep(1)
        r=json.loads(rp.ssh_host('nodeb',['qm','guest','exec-status','905',str(r['pid'])]))
    if r.get('exitcode')!=0: raise RuntimeError('guest command failed')
    return r.get('out-data')
print('VM905 REMOTE INTEGRATION',guest())
