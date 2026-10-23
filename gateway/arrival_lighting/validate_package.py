#!/usr/bin/env python3
"""Validate staged Welcome Home YAML with the production HA-General Python/YAML parser; no writes."""
import base64, json, shlex, subprocess, pathlib, time
p=pathlib.Path('gateway/arrival_lighting/jns_welcome_home_vm905.STAGED.yaml')
data=p.read_bytes()
inspect=String if False else """
import yaml,json,base64
x=yaml.safe_load(base64.b64decode(SOURCE))
assert isinstance(x,dict)
assert set(('timer','script','automation','input_boolean','input_text','input_datetime','input_number')).issubset(x)
ids=[a.get('id') for a in x['automation']]
assert len(ids)==2 and len(ids)==len(set(ids))
assert not x['input_boolean']['jns_welcome_home_enabled']['initial']
print(json.dumps({'valid':True,'automations':len(ids),'timers':list(x['timer']),'scripts':list(x['script'])}))
"""
inspect=inspect.replace("SOURCE",repr(base64.b64encode(data).decode()))
remote_cmd="exec(__import__('base64').b64decode("+repr(base64.b64encode(inspect.encode()).decode())+"))"
command=['qm','guest','exec','905','--','docker','exec','homeassistant','python3','-c',remote_cmd]
base=['ssh','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=7','root@nodeb.home.arpa']
def run(args):
    p=subprocess.run(args,capture_output=True,text=True,timeout=60)
    if p.returncode:
        raise SystemExit('Validation path unavailable, command rc '+str(p.returncode))
    return p.stdout
assert run(base+['hostname -s']).strip()=='nodeb'
response=json.loads(run(base+[shlex.join(command)]))
for _ in range(50):
    if response.get('exited'): break
    pid=response.get('pid')
    if not isinstance(pid,int): raise SystemExit('Guest exec status missing')
    time.sleep(1)
    response=json.loads(run(base+[shlex.join(['qm','guest','exec-status','905',str(pid)])]))
if not response.get('exited') or response.get('exitcode')!=0:
    raise SystemExit('Home Assistant YAML validation failed')
print('HA_GENERAL_YAML_PARSED_OK',response.get('out-data','').strip())
