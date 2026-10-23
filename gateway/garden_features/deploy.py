#!/usr/bin/env python3
"""JNS HA-General Garden Features guarded deployment and activation."""
import base64,json,pathlib,re,subprocess,sys,time
sys.path.insert(0,'gateway/arrival_lighting')
from readiness_probe import ssh_host

DIR=pathlib.Path('gateway/garden_features')
CORE_TIMEOUT=245

def guest(args,timeout=245):
    response=json.loads(ssh_host('nodeb',['qm','guest','exec','905','--',*args]))
    pid=response.get('pid')
    deadline=time.monotonic()+timeout
    while not response.get('exited'):
        if not isinstance(pid,int):
            raise RuntimeError('Guest agent did not provide a PID; command status unknown')
        if time.monotonic()>=deadline:
            raise RuntimeError('Guest command timeout; verify its PID '+str(pid)+' before retrying')
        time.sleep(3)
        response=json.loads(ssh_host('nodeb',['qm','guest','exec-status','905',str(pid)]))
    return response

def ha(command, timeout=245):
    print('JNS_HA_START '+(' '.join(command)),flush=True)
    response=guest(['ha',*command],timeout)
    code=response.get('exitcode')
    print('JNS_HA_RESULT '+json.dumps({
      'command':' '.join(command),
      'exitcode':code,
      'stdout':(response.get('out-data') or '')[-1100:],
      'stderr':(response.get('err-data') or '')[-650:]
    }),flush=True)
    return code==0

def run_local(mode):
    result=subprocess.run([sys.executable,str(DIR/'runner.py'),mode],
        capture_output=True,text=True,timeout=175)
    print('JNS_GARDEN_RUNNER '+mode+' '+result.stdout[-7500:],flush=True)
    if result.returncode!=0:
        print('JNS_GARDEN_RUNNER_ERROR '+result.stderr[-1100:],flush=True)
        raise RuntimeError('VM905 garden package '+mode+' failed')
    if mode=='--apply':
        match=re.search(r'(?m)^JNS_GARDEN_APPLIED (\{.+\})\s*$',result.stdout)
        if match is None:raise RuntimeError('Missing new package manifest')
        return json.loads(match.group(1))
    if 'JNS_GARDEN_PATCH_DONE' not in result.stdout:
        raise RuntimeError('Dry-run not complete')
    return None

def rollback(manifest):
    script=(DIR/'rollback_vm905.py').read_bytes()
    arg="exec(compile(__import__('base64').b64decode("+repr(base64.b64encode(script).decode())+"),'<garden-rollback>','exec'))"
    response=guest(['docker','exec','homeassistant','python3','-c',
                   arg,manifest['backup'],json.dumps(manifest['hashes'])],90)
    print('JNS_GARDEN_ROLLBACK_RESULT '+(response.get('out-data') or '')[-1000:],flush=True)
    if response.get('exitcode')!=0:
        raise RuntimeError('Rollback failed/blocked: '+(response.get('err-data') or '')[-400:])

def main():
    print('JNS_GARDEN_DEPLOY_START - HA-General VM905 only',flush=True)
    run_local('--dry-run')
    manifest=run_local('--apply')
    if manifest.get('status')!='applied':
        raise RuntimeError('Unexpected package deployment status')
    print('JNS_GARDEN_CONFIG_APPLIED_BACKUP '+manifest['backup'],flush=True)
    try:
        is_valid=ha(['core','check'],CORE_TIMEOUT)
    except Exception as exc:
        print('JNS_GARDEN_CORE_CHECK_EXCEPTION '+type(exc).__name__+': '+str(exc)[:160],flush=True)
        try:rollback(manifest)
        except Exception as rollback_error:
            print('JNS_GARDEN_ROLLBACK_NEEDS_MANUAL_REVIEW '+str(rollback_error)[:160],flush=True)
        raise RuntimeError('Post-deployment HA config check could not complete; no restart attempted')
    if not is_valid:
        rollback(manifest)
        raise RuntimeError('Post-deployment HA config rejected; original files restored')
    print('JNS_GARDEN_CONFIG_VALID',flush=True)
    # A full Core restart is required to load the new package helpers.
    # Other VM905 integrations may experience a brief service interruption.
    if not ha(['core','restart'],140):
        raise RuntimeError('HA Core restart not confirmed; configuration valid but activation uncertain')
    print('JNS_GARDEN_RESTART_REQUEST_ACCEPTED',flush=True)
    for attempt in range(8):
        time.sleep(8)
        try:
            if ha(['core','info'],45):
                print('JNS_GARDEN_HA_CORE_INFO_OK',flush=True)
                break
        except Exception as exc:
            print('JNS_GARDEN_CORE_RECOVERY_RETRY '+str(attempt+1)+' '+type(exc).__name__,flush=True)
    else:
        raise RuntimeError('HA Core post-restart health not confirmed')
    print('JNS_GARDEN_DEPLOY_COMPLETE - verify dashboard and entities',flush=True)

if __name__=='__main__':
    try: main()
    except Exception as err:
        print('JNS_GARDEN_DEPLOY_FAILED '+type(err).__name__+': '+str(err)[:260],flush=True)
        sys.exit(1)
