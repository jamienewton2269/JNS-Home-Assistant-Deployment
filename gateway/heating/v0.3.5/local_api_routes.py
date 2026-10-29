#!/usr/bin/env python3
"""Read-only capability audit for existing HAOS client API credentials.

Neither tokens nor Home Assistant state contents leave the respective
container. Checks only HTTP status of fixed local endpoints.
"""
import json,sys,time
sys.path.insert(0,"gateway/arrival_lighting")
from readiness_probe import ssh_host

SH=r"""
if [ -z "$SUPERVISOR_TOKEN" ]; then
 echo JNS_ROUTE token_absent
 exit 0
fi
if ! command -v curl >/dev/null 2>&1; then
 echo JNS_ROUTE curl_absent
 exit 0
fi
for endpoint in '/' '/states/climate.thermostat_thermostat'; do
 status="$(curl -sS -o /dev/null -m 7 -w '%{http_code}' -H "Authorization: Bearer $SUPERVISOR_TOKEN" "http://supervisor/core/api$endpoint" 2>/dev/null)" || status=network_error
 case "$endpoint" in
  '/') echo "JNS_ROUTE base_api_$status" ;;
  *) echo "JNS_ROUTE fixed_climate_$status" ;;
 esac
done
"""

def qga(args):
    r=json.loads(ssh_host("nodeb",["qm","guest","exec","905","--",*args]))
    end=time.monotonic()+75
    while not r.get("exited"):
        if not isinstance(r.get("pid"),int) or time.monotonic()>end:
            raise RuntimeError("read-only capability command timeout")
        time.sleep(1)
        r=json.loads(ssh_host("nodeb",["qm","guest","exec-status","905",str(r["pid"])]))
    if r.get("exitcode")!=0:
        return None
    return (r.get("out-data") or "").strip()

for container in ("app_core_ssh","hassio_cli"):
    try:
        out=qga(["docker","exec",container,"sh","-c",SH])
        tokens=[s.strip() for s in (out or "").splitlines()
                if s.startswith("JNS_ROUTE ")]
        print("JNS_HEATING_AUTH_ROUTE",json.dumps({"container":container,
            "checks":tokens[:5] if out is not None else ["unavailable"]}),flush=True)
    except Exception as exc:
        print("JNS_HEATING_AUTH_ROUTE",json.dumps({"container":container,
            "error_type":type(exc).__name__}),flush=True)
