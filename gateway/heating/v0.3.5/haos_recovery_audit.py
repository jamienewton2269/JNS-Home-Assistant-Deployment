#!/usr/bin/env python3
"""Read-only HAOS host filesystem fallback capability inspection.

Verifies that /config from the Home Assistant Core container resolves to the
host's supervisor/homeassistant directory, including the private backup.
No writes, service manipulation, controller actions, file contents or secrets.
"""
import hashlib,json,sys,time
sys.path.insert(0,"gateway/arrival_lighting")
from readiness_probe import ssh_host

EXPECTED="44054f9172e3c9e2e944240b5369b49d9735d8349fb7ca2dd0a2a782d7c8a4f8"
STAGE="v035-20261024T162546Z-43b0f6ec"
HOST="/mnt/data/supervisor/homeassistant"
GUEST="/config"

def qga(args,limit=40):
    r=json.loads(ssh_host("nodeb",["qm","guest","exec","905","--",*args]))
    deadline=time.monotonic()+limit
    while not r.get("exited"):
        if not isinstance(r.get("pid"),int) or time.monotonic()>deadline:
            raise RuntimeError("HAOS QGA command unknown; audit blocked")
        time.sleep(1)
        r=json.loads(ssh_host("nodeb",["qm","guest","exec-status","905",str(r["pid"])]))
    if r.get("exitcode")!=0:
        return ""
    return (r.get("out-data") or "").strip()

# Query only known absolute paths; not a generalised file browser.
out={}
for label,where in [
    ("host_integration",HOST+"/custom_components/jns_heating_zones/thermal.py"),
    ("host_stage_backup",HOST+"/.jns_heating_backups/"+STAGE+"/original/thermal.py"),
    ("host_stage_candidate",HOST+"/.jns_heating_backups/"+STAGE+"/candidate.py"),
    ("host_configuration",HOST+"/configuration.yaml"),
]:
    digest=qga(["sha256sum",where],limit=40)
    if digest and len(digest.split())>=2 and len(digest.split()[0])==64:
        out[label]={"exists":True,"digest":digest.split()[0]}
    else:
        out[label]={"exists":False}
# Pin the container's active source hash to independently check the host mapping.
inside=qga(["docker","exec","homeassistant","sha256sum",
            GUEST+"/custom_components/jns_heating_zones/thermal.py"],limit=40)
if inside and len(inside.split())>=2:
    out["core_active_digest"]=inside.split()[0]
out["host_to_core_mapping_matches"]=(
    out["host_integration"].get("digest")==out.get("core_active_digest")==EXPECTED
)
out["host_snapshot_original_matches"]=(
    out["host_stage_backup"].get("digest")==EXPECTED)
# Check tools by executing help only. No service actions.
out["host_shell_available"]=bool(qga(["/bin/sh","-c","echo JNS_SHELL_READONLY"],limit=30))
out["host_mv_available"]=bool(qga(["/bin/sh","-c","command -v mv"],limit=30))
out["host_cp_available"]=bool(qga(["/bin/sh","-c","command -v cp"],limit=30))
out["recovery_route_verified"]=all((
    out["host_to_core_mapping_matches"],
    out["host_snapshot_original_matches"],
    out["host_shell_available"],
    out["host_mv_available"],
    out["host_cp_available"],
    out["host_stage_candidate"].get("exists",False),
))
print("JNS_HEATING_HOST_FALLBACK_AUDIT",json.dumps(out,sort_keys=True),flush=True)
if not out["recovery_route_verified"]:
    sys.exit(2)
