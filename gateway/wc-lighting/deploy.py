#!/usr/bin/env python3
"""Transactional patch of VM905 WC light activation lux condition.
Home Assistant guest-agent only. Never touches VM902, fans or other automation.
"""
import base64,json,pathlib,time,sys
sys.path.insert(0,'gateway/arrival_lighting')
from readiness_probe import ssh_host
PATCH=pathlib.Path('gateway/wc-lighting/patch_core.py').read_bytes()
SOURCE=base64.b64encode(PATCH).decode()
def vm905(args, timeout=210):
    request=['qm','guest','exec','905','--timeout','12','--',*args]
    response=json.loads(ssh_host('nodeb',request))
    until=time.monotonic()+timeout
    # QEMU exec-status returns exited/exitcode but does NOT repeat the initial PID.
    # Keep the PID from the original guest exec response for all polls.
    pid=response.get('pid')
    while not response.get('exited'):
        if not isinstance(pid,int) or time.monotonic()>until:
            raise RuntimeError('guest command still in progress / initial PID missing; stop for manual review')
        time.sleep(2)
        response=json.loads(ssh_host('nodeb',['qm','guest','exec-status','905',str(pid)]))
    return response
def patch(args):
    cmd="exec(compile(__import__('base64').b64decode("+repr(SOURCE)+"),'<wc-patch>','exec'))"
    response=vm905(['docker','exec','homeassistant','python3','-c',cmd,*args],60)
    output=(response.get('out-data') or '').strip()
    try: report=json.loads(output)
    except Exception: raise RuntimeError('WC patch returned no valid status (exit '+str(response.get('exitcode'))+')')
    print('WC_PATCH_RESULT '+json.dumps(report,sort_keys=True),flush=True)
    if response.get('exitcode')!=0 or report.get('status')=='blocked':
        raise RuntimeError('WC patch rejected: '+str(report.get('error')))
    return report
def cli(args,limit=240):
    response=vm905(['ha',*args],limit)
    report={'command':'ha '+ ' '.join(args),
            'exitcode':response.get('exitcode'),
            'stdout':(response.get('out-data') or '')[:700],
            'stderr':(response.get('err-data') or '')[:500]}
    print('WC_HA_CLI '+json.dumps(report),flush=True)
    return response.get('exitcode')==0
def main():
    print('=== WC DAYTIME LIGHT EARLIER 1.5x ===',flush=True)
    dry=patch([])
    if dry.get('status')=='already_applied':
        print('WC_ALREADY_PATCHED_NO_RESTART');return
    if dry.get('status')!='preflight_ok':raise RuntimeError('unexpected preflight status')
    if not cli(['core','check'],240):
        raise RuntimeError('existing HA config invalid before patch - no changes made')
    changed=patch(['--apply'])
    if changed.get('status')!='patched':raise RuntimeError('apply did not patch')
    if changed.get('old_sha256')!=dry.get('old_sha256'):
        raise RuntimeError('source changed between preflight and apply; manual verification needed')
    if not cli(['core','check'],240):
        print('WC_POST_PATCH_CONFIG_CHECK_FAILED_ROLLING_BACK',flush=True)
        patch(['--rollback',changed['backup'],changed['new_sha256']])
        cli(['core','check'],240)
        raise RuntimeError('failed validation: backup restored, activation cancelled')
    # Activation: an automation-only reload has no confirmed unattended
    # credential path on this HAOS VM. Core restart is the supported fallback.
    if not cli(['core','restart'],240):
        raise RuntimeError('configuration valid, but Core restart failed; manual review required')
    if not cli(['core','info'],100):
        raise RuntimeError('restart requested, but Core info unavailable')
    print('WC_CONFIG_VALID_AND_CORE_RESTART_COMMAND_SUCCEEDED',flush=True)
if __name__=='__main__':
    try:main()
    except Exception as exc:
        print('WC_DEPLOY_BLOCKED',type(exc).__name__,str(exc)[:240],flush=True)
        raise SystemExit(1)
