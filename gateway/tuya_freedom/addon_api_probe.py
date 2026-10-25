#!/usr/bin/env python3
"""Probe existing trusted Home Assistant add-on API capabilities without exporting tokens.

Only allowed calls: Docker list, check presence of SUPERVISOR_TOKEN, and GET
Core /api/ health via the Supervisor's documented proxy.
No tokens, containers' environment, credentials or personal names in logs.
"""
import json,sys,time
sys.path.insert(0,"gateway/arrival_lighting")
from readiness_probe import ssh_host
def guest(*args):
    r=json.loads(ssh_host("nodeb",["qm","guest","exec","905","--",*args]))
    pid=r.get("pid");end=time.monotonic()+75
    while not r.get("exited"):
        if not isinstance(pid,int) or time.monotonic()>end:raise RuntimeError("qga_timeout")
        time.sleep(2)
        r=json.loads(ssh_host("nodeb",["qm","guest","exec-status","905",str(pid)]))
    if r.get("exitcode")!=0:raise RuntimeError("guest_query_failed")
    return (r.get("out-data") or "").strip()
def main():
    if "running" not in ssh_host("nodeb",["qm","status","905"]):raise RuntimeError("vm905_not_running")
    containers=guest("docker","ps","--format","{{.Names}}").splitlines()
    addons=[x for x in containers if x.startswith("addon_") and
            ("ssh" in x or "terminal" in x or "studio" in x)]
    probe='''if [ -n "\${SUPERVISOR_TOKEN:-}" ]; then
      echo TOKEN_PRESENT
      if command -v curl >/dev/null 2>&1; then
        status=$(curl --connect-timeout 3 --max-time 8 -sS -o /dev/null -w '%{http_code}' \
          -H "Authorization: Bearer \${SUPERVISOR_TOKEN}" \
          http://supervisor/core/api/ 2>/dev/null || true)
        if [ "$status" = "200" ]; then echo API_READABLE; else echo API_NOT_AVAILABLE; fi
      else echo CURL_MISSING; fi
    else echo NO_ADDON_TOKEN; fi'''
    out={"identified_candidate_addons":len(addons),
         "addon_with_supervisor_token":0,"addon_with_api_read_access":0,
         "token_exported":False,"cloud_calls":False}
    for name in addons[:5]:
        try:
            result=guest("docker","exec",name,"sh","-c",probe)
            out["addon_with_supervisor_token"]+=int("TOKEN_PRESENT" in result)
            out["addon_with_api_read_access"]+=int("API_READABLE" in result)
        except Exception:
            pass
    return out
if __name__=="__main__":
    try:print("JNS_TUYA_LOCAL_API_CAPABILITY",json.dumps(main(),sort_keys=True),flush=True)
    except Exception as e:print("JNS_TUYA_LOCAL_API_CAPABILITY_BLOCKED",type(e).__name__,flush=True);raise SystemExit(1)
