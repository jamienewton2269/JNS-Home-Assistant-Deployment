#!/usr/bin/env python3
"""JNS guarded package patch over existing Node C -> Node B -> VM905 QGA."""
import base64,json,pathlib,shlex,subprocess,sys,time
sys.path.insert(0,'gateway/arrival_lighting')
from readiness_probe import ssh_host
HERE=pathlib.Path('gateway/garden_features')
CODE=(HERE/'patch_vm905.py').read_bytes()
PACKAGE=(HERE/'jns_garden_features_backdoor.yaml').read_bytes()
MODE='--apply' if '--apply' in sys.argv else '--dry-run'

def qga(args,timeout=180):
    response=json.loads(ssh_host('nodeb',['qm','guest','exec','905','--',*args]))
    pid=response.get('pid')
    deadline=time.monotonic()+timeout
    while not response.get('exited'):
        if not isinstance(pid,int):
            raise RuntimeError('Guest exec returned no initial PID; do not guess execution status')
        if time.monotonic()>deadline:raise RuntimeError('Guest still executing; manual review required')
        time.sleep(1)
        response=json.loads(ssh_host('nodeb',['qm','guest','exec-status','905',str(pid)]))
    return response

def patch():
    source="PACKAGE_B64="+repr(base64.b64encode(PACKAGE).decode())+";exec(compile(__import__('base64').b64decode("+repr(base64.b64encode(CODE).decode())+"),'<jns-garden-patch>','exec'))"
    result=qga(['docker','exec','homeassistant','python3','-c',source,MODE])
    out=result.get('out-data','')
    print(out[:9000],flush=True)
    if result.get('exitcode')!=0:
        print('JNS_GARDEN_GUEST_STDERR '+(result.get('err-data') or '')[-2000:],flush=True)
    if result.get('exitcode')!=0 or 'JNS_GARDEN_BLOCKED' in out:raise RuntimeError('guest patcher blocked')
    expected=('JNS_GARDEN_APPLIED' if MODE=='--apply' else 'JNS_GARDEN_PLAN')
    if expected not in out:raise RuntimeError('missing '+expected)
    return result

if __name__=='__main__':
    print('=== GARDEN FEATURE + BACK DOOR MODE '+MODE+' ===',flush=True)
    patch()
    print('JNS_GARDEN_PATCH_DONE',flush=True)
