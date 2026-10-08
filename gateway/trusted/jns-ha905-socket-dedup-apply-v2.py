#!/usr/bin/env python3
"""HA905 protected socket dashboard repair via existing Node C runner/Proxmox guest agent."""
import base64, hashlib, json, os, pathlib, re, shlex, subprocess, sys, time
BASE='/mnt/data/supervisor/homeassistant'
PATH=BASE+'/dashboards/testing.yaml'
REG=BASE+'/.storage/core.entity_registry'
RUNAS=['runuser','-u','github-runner','--','ssh','-o','BatchMode=yes','-o','ConnectTimeout=8','-o','StrictHostKeyChecking=yes','-o','HostName=10.10.10.235','nodeb']
def guest(cmd):
    call=RUNAS+['timeout 18 qm guest exec 905 -- /bin/sh -c '+shlex.quote(cmd)]
    proc=subprocess.run(call,capture_output=True,text=True,timeout=30)
    if proc.returncode: raise RuntimeError('SSH/guest failure: '+proc.stderr[:500])
    d=json.loads(proc.stdout)
    if not d.get('exited') or d.get('exitcode')!=0 or d.get('out-truncated'): raise RuntimeError('Guest command failure: '+str(d)[:600])
    return d.get('out-data','')
def fetch(path):
    size=int(guest("wc -c < "+shlex.quote(path)).strip())
    if not (2000 < size < 100000): raise RuntimeError('Unexpected dashboard size '+str(size))
    parts=[]
    for i in range((size+2047)//2048):
        s=guest("dd if="+shlex.quote(path)+" bs=2048 skip="+str(i)+" count=1 2>/dev/null | base64")
        parts.append(base64.b64decode(s))
    raw=b''.join(parts)
    if len(raw)!=size: raise RuntimeError('File transfer incomplete')
    return raw
print('[1/5] Identify DrayTek Tuya Local switch',flush=True)
q='.data.entities[] | select(.device_id == "f0096d1c12e239a2d71b697c963e198c") | .entity_id'
raw=guest("jq -r "+shlex.quote(q)+" "+shlex.quote(REG))
switches=[s for s in raw.splitlines() if s.startswith('switch.') and not any(v in s for v in ('child_lock','overcharge','protection'))]
if len(switches)!=1: raise RuntimeError('Ambiguous DrayTek local power switch: '+repr(switches))
router=switches[0]
nas='switch.nas_server_plug'
cloud=['switch.nas_server_socket_1','switch.wdmycloud_nas_socket_1']
print('Local NAS:',nas,'Local router:',router,'Cloud duplicates:',cloud,flush=True)
print('[2/5] Fetch dashboard; validate known structure',flush=True)
old=fetch(PATH)
text=old.decode('utf-8')
if 'JNS_SOCKET_DEDUP_V2' in text:
    print('Already patched; no changes');sys.exit(0)
first=text.index('  - title: Controls')
protected=text.index('  - title: Protected IT') if '  - title: Protected IT' in text else -1
commission=text.index('  - title: Commissioning')
if not (first<protected<commission):raise RuntimeError('Unexpected dashboard view structure; refusing modification')
controls=text[first:text.index('\n  - title:',first+5)]
if '            - domain: switch' not in controls or '          exclude:' not in controls:raise RuntimeError('Controls filter format changed')
# Explicitly exclude both cloud aliases and both local infrastructure power switches
for eid in [nas,router]+cloud:
    controls=controls.replace('          exclude:\n','          exclude:\n            - entity_id: '+eid+'\n',1)
new=text[:first]+controls+text[text.index('\n  - title:',first+5):]
# Add a dedicated secure view for the two local physical sockets.
# Do not rely on the label existing. No cloud aliases are surfaced.
start=new.index('  - title: Protected IT')
end=new.index('  - title: Commissioning')
pv=new[start:end]
# The auto-populated Protected IT card must exclude the explicit tiles and both
# cloud aliases, otherwise applying Protected IT labels can create duplicates.
if '        sort:\n          method: area' not in pv:
    raise RuntimeError('Unexpected Protected IT auto-entities structure')
protected_exclusions='        exclude:\n'+''.join('          - entity_id: '+eid+'\n' for eid in [nas,router]+cloud)
pv=pv.replace('        sort:\n          method: area',protected_exclusions+'        sort:\n          method: area',1)
insert='''      # JNS_SOCKET_DEDUP_V1: physical infrastructure sockets; avoid cloud aliases
      - type: markdown
        content: "Verified local power controls only. Switching either outlet can interrupt infrastructure."
      - type: grid
        columns: 2
        square: false
        cards:
'''
for label,eid in [('NAS Server Power',nas),('DrayTek Router Power',router)]:
    insert+=f'''          - type: tile
            entity: {eid}
            name: {label}
            tap_action:
              action: toggle
              confirmation:
                text: "Confirm power change to {label}."
            hold_action:
              action: more-info
'''
pv=pv.replace('    cards:\n','    cards:\n'+insert,1)
new=new[:start]+pv+new[end:]
if new==text:raise RuntimeError('No changes were made')
newb=new.encode()
print('[3/5] Create backup and stage candidate',flush=True)
stamp=time.strftime('%Y%m%dT%H%M%S')
backup=PATH+'.jns-socket-dedup-'+stamp+'.bak'
stage=PATH+'.jns-dedup-staging'
guest('cp -p '+shlex.quote(PATH)+' '+shlex.quote(backup)+' && : > '+shlex.quote(stage))
try:
    for i in range(0,len(newb),2048):
        b64=base64.b64encode(newb[i:i+2048]).decode()
        guest("printf '%s' "+shlex.quote(b64)+" | base64 -d >> "+shlex.quote(stage))
        print(f'  staged {min(i+2048,len(newb))}/{len(newb)} bytes',flush=True)
    print('[4/5] Verify checksum and install dashboard',flush=True)
    sha=hashlib.sha256(newb).hexdigest()
    got=guest('sha256sum '+shlex.quote(stage)).split()[0]
    if sha!=got:raise RuntimeError('Checksum mismatch: refusing install')
    guest('mv '+shlex.quote(stage)+' '+shlex.quote(PATH))
except Exception:
    print('FAILED: original dashboard unchanged unless install completed; backup at '+backup,flush=True)
    raise
print('[5/5] DONE. Backup:',backup,flush=True)
print('Excluded from ordinary Controls: '+', '.join([nas,router]+cloud))
print('Protected IT local controls: '+nas+', '+router)
print('No lights switched, integrations/registries unchanged, no Core restart.')\nprint('IMPORTANT: dashboard confirmation is NOT a service-level interlock. Do not turn off either infrastructure outlet.')
