#!/usr/bin/env python3
"""Node C runner -> Node B trusted SSH -> Node A VM902 guest agent.
No direct .storage modifications, secret output, restarts or light control.
"""
import base64
import json
import pathlib
import sys
import time
import readiness_probe as rp

ROOT=pathlib.Path(__file__).resolve().parent
APPLY="--apply" in sys.argv

def main():
    source=(ROOT/"enable_wifi_core.py").read_bytes()
    encoded=base64.b64encode(source).decode()
    # Decode payload in the VM902 Core container. No files written on VM902.
    arg="exec(compile(__import__('base64').b64decode("+repr(encoded)+"),'<jns-enable-wifi>','exec'))"
    cmd=["qm","guest","exec","902","--","docker","exec","homeassistant",
         "python3","-c",arg]
    print("JNS_VM902_WIFI_TRACKER mode="+("apply" if APPLY else "preflight"),flush=True)
    if not APPLY:
        # Python source uses sys.argv to decide; this performs a guarded, read-only query.
        pass
    else:
        # sys.argv is local to the python3 -c invocation. Add flag to process.
        cmd.append("--apply")
    initial=json.loads(rp.ssh_host("nodea",cmd))
    result=initial
    for _ in range(45):
        if result.get("exited"):
            break
        pid=result.get("pid")
        if not isinstance(pid,int):
            raise RuntimeError("guest_agent_status_missing_pid")
        time.sleep(1)
        result=json.loads(rp.ssh_host("nodea",["qm","guest","exec-status","902",str(pid)]))
    if not result.get("exited"):
        raise RuntimeError("guest_command_did_not_finish")
    report=json.loads((result.get("out-data") or "").strip())
    print("JNS_WIFI_RESULT "+json.dumps(report,sort_keys=True),flush=True)
    if result.get("exitcode")!=0 or report.get("status")=="blocked":
        raise SystemExit(2)
    if APPLY and report.get("status") not in ("enabled","already_enabled"):
        raise SystemExit(3)
    print("JNS_WIFI_REGISTRY_API_OK",flush=True)
if __name__=="__main__":
    main()
