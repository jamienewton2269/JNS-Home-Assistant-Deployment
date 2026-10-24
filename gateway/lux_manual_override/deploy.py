#!/usr/bin/env python3
"""Guarded JNS evening manual-off deploy; native HA config gates and rollback."""
import base64,json,pathlib,re,subprocess,sys,time,urllib.request
sys.path.insert(0,'gateway/arrival_lighting')
from readiness_probe import ssh_host
folder=pathlib.Path('gateway/lux_manual_override')
def qga(args,limit=260):
    result=json.loads(ssh_host('nodeb',['qm','guest','exec','905','--',*args]))
    pid=result.get('pid')
    until=time.monotonic()+limit
    while not result.get('exited'):
        if not isinstance(pid,int):raise RuntimeError('QGA initial PID missing; cannot safely retry')
        if time.monotonic()>=until:raise RuntimeError('QGA PID '+str(pid)+' still active; manual status required')
        time.sleep(3)
        result=json.loads(ssh_host('nodeb',['qm','guest','exec-status','905',str(pid)]))
    return result
def ha(*args,limit=250):
    result=qga(['ha',*args],limit=limit)
    report={'action':' '.join(args),'code':result.get('exitcode'),
       'response':(result.get('out-data') or '')[-500:],
       'error':(result.get('err-data') or '')[-250:]}
    print('JNS_LUX_NATIVE_HA '+json.dumps(report),flush=True)
    return result.get('exitcode')==0
def runner(mode):
    result=subprocess.run([sys.executable,str(folder/'runner.py'),mode],
           capture_output=True,text=True,timeout=175)
    print('JNS_LUX_RUN '+mode+' '+result.stdout[-5400:],flush=True)
    if result.returncode!=0:
        print('JNS_LUX_RUN_FAILED '+result.stderr[-650:],flush=True)
        raise RuntimeError(mode+' failed')
    if mode=='--apply':
        match=re.search(r'JNS_LUX_MANUAL_APPLIED (\{.+\})',result.stdout)
        if not match:raise RuntimeError('Missing applied record')
        return json.loads(match.group(1))
    if 'JNS_LUX_MANUAL_PLAN' not in result.stdout:
        raise RuntimeError('Missing dry-run manifest')
def rollback(record):
    source=(folder/'rollback_vm905.py').read_bytes()
    python_code="exec(compile(__import__('base64').b64decode("+repr(base64.b64encode(source).decode())+"),'<jns-lux-rollback>','exec'))"
    result=qga(['docker','exec','homeassistant','python3','-c',python_code,record['backup'],json.dumps(record['after_hashes'])],90)
    print('JNS_LUX_ROLLBACK '+(result.get('out-data') or '')[-500:],flush=True)
    if result.get('exitcode')!=0:raise RuntimeError('Rollback returned nonzero: '+(result.get('err-data') or '')[-300:])
def http_readiness():
    try:
        with urllib.request.urlopen('http://ha-general.home.arpa/',timeout=6) as res:
            return res.status==200
    except Exception:return False
def main():
    print('JNS_LUX_DEPLOY_BEGIN_VM905',flush=True)
    runner('--dry-run')
    record=runner('--apply')
    print('JNS_LUX_CONFIG_WRITTEN '+record['backup'],flush=True)
    try:
        valid=ha('core','check',limit=270)
    except Exception as err:
        print('JNS_LUX_CHECK_UNCONFIRMED '+str(err)[:180],flush=True)
        try:rollback(record)
        except Exception as r:print('JNS_LUX_ROLLBACK_UNCONFIRMED '+str(r)[:180],flush=True)
        raise
    if not valid:
        rollback(record)
        raise RuntimeError('Home Assistant rejected config; original files restored')
    print('JNS_LUX_CONFIG_VALID',flush=True)
    # Loading the new package requires a single Core restart.
    # Do NOT retry if command status remains unknown.
    try:
        restarted=ha('core','restart',limit=285)
    except RuntimeError as e:
        print('JNS_LUX_RESTART_STATUS_UNKNOWN '+str(e)[:170],flush=True)
        raise
    if not restarted:raise RuntimeError('Restart command failed; inspect Core before retry')
    print('JNS_LUX_RESTART_COMPLETED',flush=True)
    for i in range(24):
        if http_readiness():
            print('JNS_LUX_HTTP_OK',flush=True)
            break
        time.sleep(5)
    else:raise RuntimeError('HA-General HTTP readiness not confirmed')
    print('JNS_LUX_DEPLOY_FINISHED',flush=True)
try:main()
except Exception as e:
    print('JNS_LUX_DEPLOY_BLOCKED '+type(e).__name__+': '+str(e)[:260],flush=True)
    raise SystemExit(2)
