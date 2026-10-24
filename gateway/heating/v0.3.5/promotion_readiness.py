#!/usr/bin/env python3
"""Read-only release-capability and runtime-health audit for VM905.

No privileged gateway installation, no HA reload, restart, writes, or tokens.
Output contains only aggregate capability/status and approved version fields.
"""
import base64,hashlib,json,os,pathlib,re,sys,time
sys.path.insert(0,"gateway/arrival_lighting")
from readiness_probe import ssh_host

APPROVED_COMPONENT="jns_heating_zones"
SNAPSHOT="v035-20261024T162546Z-43b0f6ec"
INSPECT=r"""
import hashlib,json,pathlib
root=pathlib.Path("/config")
comp=root/"custom_components"/"jns_heating_zones"
store=root/".storage"
orig="v035-20261024T162546Z-43b0f6ec"
stage=root/".jns_heating_backups"/orig
manifest=json.loads((comp/"manifest.json").read_text())
meta=json.loads((stage/"state.json").read_text())
registry=json.loads((store/"core.entity_registry").read_text())["data"]["entities"]
config_entries=json.loads((store/"core.config_entries").read_text())["data"]["entries"]
heating_entries=[x for x in config_entries if x.get("domain")=="jns_heating_zones"]
lyric_entries=[x for x in config_entries if "lyric" in (x.get("domain") or "").lower() or "honeywell" in (x.get("domain") or "").lower()]
registered=[e for e in registry if (e.get("platform")=="jns_heating_zones")]
recording=sorted(store.glob("jns_heating_zone_*"))
samples=[len(json.loads(p.read_text()).get("data",{}).get("samples",[])) for p in recording]
out={
 "active_version":manifest.get("version"),
 "source_hash":hashlib.sha256((comp/"thermal.py").read_bytes()).hexdigest(),
 "snapshot_state":meta.get("state"),
 "stage_id_matches":meta.get("stage_id")==orig,
 "snapshot_files_complete":all((stage/q).exists() for q in
   ("original/thermal.py","original/manifest.json","candidate.py","state.json")),
 "component_entities_count":len(registered),
 "heating_config_entries_count":len(heating_entries),
 "lyric_related_config_entries_count":len(lyric_entries),
 "stores_count":len(recording),
 "samples_total":sum(samples),
 "configuration_exists":(root/"configuration.yaml").is_file(),
 "core_restart_or_reload_called":False,
}
print(json.dumps(out,sort_keys=True))
"""

def qga(args,timeout=45):
    status=json.loads(ssh_host("nodeb",["qm","guest","exec","905","--",*args]))
    deadline=time.monotonic()+timeout
    while not status.get("exited"):
        if not isinstance(status.get("pid"),int) or time.monotonic()>deadline:
            raise RuntimeError("VM905 guest agent did not return status; no writes attempted")
        time.sleep(1)
        status=json.loads(ssh_host("nodeb",["qm","guest","exec-status","905",str(status["pid"])]))
    if status.get("exitcode")!=0:
        raise RuntimeError("VM905 read-only command exit "+str(status.get("exitcode")))
    return (status.get("out-data") or "").strip()

for target in ("/usr/local/sbin/jns-gateway-exec","/usr/local/libexec"):
    path=pathlib.Path(target)
    if path.exists():
        st=path.stat()
        print("JNS_GATEWAY_TARGET",json.dumps({
            "path":target,"root_owned":st.st_uid==0,
            "group_or_world_writable":bool(st.st_mode & 0o022),
            "executable":bool(st.st_mode & 0o111),
            "is_symlink":path.is_symlink()
        },sort_keys=True),flush=True)
    else:
        print("JNS_GATEWAY_TARGET",json.dumps({"path":target,"present":False}),flush=True)
# Read only approved line-level structure from wrapper, not embedded commands.
wrapper=pathlib.Path("/usr/local/sbin/jns-gateway-exec")
if wrapper.is_file():
    raw=wrapper.read_text(errors="replace")
    found=sorted(set(re.findall(r"(?:job_type|gateway_capabilities|capability|case\s+)\b",raw,re.I)))
    print("JNS_GATEWAY_WRAPPER",json.dumps({"bytes":len(raw),"sha256":hashlib.sha256(raw.encode()).hexdigest(),
        "recognised_dispatch_tokens":found},sort_keys=True),flush=True)

vhost=ssh_host("nodeb",["qm","status","905"]).strip()
print("JNS_VM905_HOST_STATUS",json.dumps({"running":"running" in vhost},sort_keys=True),flush=True)
code="exec(__import__('base64').b64decode('"+base64.b64encode(INSPECT.encode()).decode()+"'))"
snapshot=json.loads(qga(["docker","exec","homeassistant","python3","-c",code]))
print("JNS_VM905_PREPROMOTION_READONLY",json.dumps(snapshot,sort_keys=True),flush=True)
# HA CLI info is also read-only; keep only state/version, never any public URL.
try:
    info=json.loads(qga(["ha","core","info"],timeout=60))
    print("JNS_VM905_CORE_HEALTH",json.dumps({"version":info.get("version"),
        "state":info.get("state"),"boot":info.get("boot"),
        "watchdog":info.get("watchdog")},sort_keys=True),flush=True)
except Exception as e:
    print("JNS_VM905_CORE_HEALTH",json.dumps({"available":False,
        "error_type":type(e).__name__},sort_keys=True),flush=True)
