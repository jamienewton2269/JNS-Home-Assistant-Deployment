#!/usr/bin/env python3
"""Read-only HA-General startup and address diagnostic; no secrets in public logs."""
import base64,json,sys
sys.path.insert(0,'gateway/garden_features')
from runner import qga

snippet=r"""
import collections,json,pathlib,re,socket
status={}
for port in (80,8123):
    sk=socket.socket()
    sk.settimeout(3)
    status[str(port)]=sk.connect_ex(('127.0.0.1',port))
    sk.close()
path=pathlib.Path('/config/home-assistant.log')
lines=path.read_text(errors='replace').splitlines()[-2000:] if path.exists() else []
errors=collections.Counter()
for line in lines:
    if ' ERROR ' not in line and ' CRITICAL ' not in line: continue
    m=re.search(r'\[([a-zA-Z0-9_.-]+)\]',line)
    errors[m.group(1) if m else 'unknown']+=1
out={'local_port_connection_codes':status,'log_exists':path.exists(),
     'log_recent_error_components':errors.most_common(12),
     'recent_log_count':len(lines)}
print(json.dumps(out))
"""
enc=base64.b64encode(snippet.encode()).decode()
arg="exec(__import__('base64').b64decode('"+enc+"'))"
r=qga(['docker','exec','homeassistant','python3','-c',arg],timeout=35)
print('VM905_LOCAL_STARTUP',r.get('out-data','').strip(),flush=True)
if r.get('exitcode')!=0:
    print('VM905_LOCAL_DIAGNOSTIC_BLOCKED',str(r.get('err-data',''))[-300:],flush=True)
print('VM905_DNS_RESOLVES_FROM_NODEB',flush=True)
from readiness_probe import ssh_host
for cmd in (['getent','hosts','ha-general.home.arpa'],['qm','guest','exec','905','--','ha','network','info']):
    try:
        answer=ssh_host('nodeb',cmd)
        if cmd[0]=='getent': print('DNS',answer.strip()[:300],flush=True)
        else: print('NETWORK_INFO',answer[-8000:],flush=True)
    except Exception as e:
        print('NETWORK_INFO_BLOCKED',type(e).__name__,flush=True)
