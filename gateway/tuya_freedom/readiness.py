#!/usr/bin/env python3
"""Tuya Freedom VM905 preflight: private 12-device readiness and 5-local state audit.

No device commands, config-flow submissions, network denial rules, or cloud changes.
Public CI logs contain only aggregate numbers and boolean capabilities.
"""
import base64
import json
import sys
import time

sys.path.insert(0, "gateway/arrival_lighting")
from readiness_probe import ssh_host

GUEST = r'''
import ast, collections, datetime, json, os, pathlib, socket, urllib.request
root = pathlib.Path("/config")
stor = root/".storage"
dpath = root/".jns_tuya_freedom"
if not dpath.is_dir() or dpath.is_symlink():
    raise RuntimeError("Private migration directory absent or unsafe")
def reg(file,field):
    return json.loads((stor/file).read_text())["data"][field]
configs=reg("core.config_entries","entries")
devices=reg("core.device_registry","devices")
entities=reg("core.entity_registry","entities")
entries={x.get("entry_id"):x for x in configs}
ed=collections.defaultdict(list)
for e in entities:
    ed[e.get("device_id")].append(e)
def dids(d):
    return {str(x[1]).strip().lower() for x in d.get("identifiers",[])
         if isinstance(x,(list,tuple)) and len(x)==2
         and str(x[0]).lower()=="tuya" and len(str(x[1]).strip())>=12}
clouds=collections.defaultdict(list)
for d in devices:
    if entries.get(d.get("config_entry_id"),{}).get("domain")!="tuya":
        continue
    ids=dids(d)
    if len(ids)==1:
        clouds[next(iter(ids))].append(d)
local={}
for e in configs:
    if e.get("domain")=="tuya_local":
        dev=e.get("data",{}).get("device_id")
        if isinstance(dev,str):
            local[dev.strip().lower()]=e
def contains_key(obj):
    if isinstance(obj,dict):
        if any(k.lower() in ("local_key","localkey","device_key") and bool(v)
               for k,v in obj.items()):return True
        return any(contains_key(v) for v in obj.values())
    if isinstance(obj,list):
        return any(contains_key(x) for x in obj)
    return False
cloud_key_counts=collections.Counter()
for e in configs:
    if e.get("domain")=="tuya":
        cloud_key_counts["cloud_entry_contains_local_key"]=int(contains_key(e.get("data",{})) or contains_key(e.get("options",{}))) + cloud_key_counts["cloud_entry_contains_local_key"]
component=root/"custom_components"/"tuya_local"
manifest=component/"manifest.json"
version="unknown"
if manifest.is_file():
    version=str(json.loads(manifest.read_text()).get("version","unknown"))
flow=component/"config_flow.py"
steps=[]
if flow.is_file():
    tree=ast.parse(flow.read_text(encoding="utf-8"))
    steps=sorted(set(x.name for x in ast.walk(tree)
        if isinstance(x,(ast.AsyncFunctionDef,ast.FunctionDef))
        and x.name.startswith("async_step_")))
# HA API access is optional. No token contents are exported.
states=None
state_access="not_available"
token=os.environ.get("SUPERVISOR_TOKEN","")
if token:
    try:
        import asyncio, aiohttp
        async def get_states_ws():
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=25)) as session:
                async with session.ws_connect("ws://supervisor/core/websocket",timeout=8) as ws:
                    hello=await ws.receive_json(timeout=8)
                    if hello.get("type")!="auth_required":
                        return None
                    await ws.send_json({"type":"auth","access_token":token})
                    auth=await ws.receive_json(timeout=8)
                    if auth.get("type")!="auth_ok":
                        return None
                    await ws.send_json({"id":1,"type":"get_states"})
                    for _ in range(5):
                        res=await ws.receive_json(timeout=8)
                        if res.get("type")=="result" and res.get("id")==1 and res.get("success"):
                            return {x["entity_id"]:x["state"] for x in res.get("result",[])}
            return None
        states=asyncio.run(get_states_ws())
        if states is not None:
            state_access="supervisor_websocket"
    except (OSError,ValueError,KeyError,TimeoutError,ImportError):
        state_access="not_available"
# Never treat stale restored states as live device validation.
now=datetime.datetime.now(datetime.timezone.utc)
rows=[]
summary=collections.Counter()
for native_id, dlist in sorted(clouds.items()):
    cfg=local.get(native_id)
    local_reg=[d for d in devices
               if entries.get(d.get("config_entry_id"),{}).get("domain")=="tuya_local"
               and entries.get(d.get("config_entry_id"),{}).get("data",{}).get("device_id")==native_id]
    centities=[e for d in dlist for e in ed.get(d["id"],[]) if e.get("platform")=="tuya"]
    lentities=[e for d in local_reg for e in ed.get(d["id"],[]) if e.get("platform")=="tuya_local"]
    host=(cfg or {}).get("data",{}).get("host")
    host_syntax_ok=isinstance(host,str) and bool(host.strip())
    dns_ok=False
    if host_syntax_ok:
        try:
            socket.getaddrinfo(host,6668,type=socket.SOCK_STREAM)
            dns_ok=True
        except OSError:
            pass
    live=None
    if states is not None and cfg:
        live={e["entity_id"]:states.get(e["entity_id"],"not_loaded") for e in lentities}
    counted_status=(collections.Counter(live.values()) if live is not None else {})
    online_count=sum(v for k,v in counted_status.items() if k not in ("unavailable","unknown","not_loaded"))
    powered_domains=collections.Counter(e.get("entity_id","").split(".")[0] for e in lentities)
    cloud_domains=collections.Counter(e.get("entity_id","").split(".")[0] for e in centities)
    is_local=bool(cfg)
    summary["local_configured" if is_local else "needs_onboarding"]+=1
    if is_local:
        summary["local_with_key" if contains_key(cfg.get("data",{})) else "local_missing_key"]+=1
        summary["local_with_host" if host_syntax_ok else "local_without_host"]+=1
        summary["local_host_dns_resolves" if dns_ok else "local_host_dns_unresolved"]+=1
        if states is not None:
            summary["local_devices_with_loaded_entities"]+=int(any(
                eid in states for eid in (e["entity_id"] for e in lentities)))
            summary["local_devices_with_some_healthy_entity"]+=int(online_count>0)
            summary["local_entities_loaded_healthy"]+=online_count
            summary["local_entities_bad_or_missing"]+=len(lentities)-online_count
    else:
        summary["onboarding_cloud_entities"]+=len(centities)
        summary["onboarding_devices_without_cloud_entities"]+=int(len(centities)==0)
        domains_with_cloud={e.get("entity_id","").split(".")[0] for e in centities}
        for domain in sorted(domains_with_cloud):
            if domain in {"sensor","switch","light","select","binary_sensor","climate","cover","lock","fan","number"}:
                summary["onboarding_devices_with_"+domain]+=1
        if any("lock"==e.get("entity_id","").split(".")[0] for e in centities):
            summary["onboarding_security_critical_device"]+=1
    rows.append({
        "native_device_id":native_id,
        "device_name":next((d.get("name_by_user") or d.get("name") for d in dlist
                            if d.get("name_by_user") or d.get("name")),""),
        "cloud_entity_ids":sorted({e["entity_id"] for e in centities}),
        "cloud_domains":dict(cloud_domains),
        "local_configured":is_local,
        "local_entity_ids":sorted({e["entity_id"] for e in lentities}),
        "local_domains":dict(powered_domains),
        "has_local_key":contains_key(cfg.get("data",{})) if cfg else False,
        "local_host":host if cfg else None,
        "host_resolves":dns_ok if cfg else None,
        "local_live_states":live,
        "local_healthy_entities":online_count if live is not None else None,
        "status":"live_state_only_needs_wan_outage_test" if is_local and states is not None and online_count>0
                 else "requires_local_onboarding" if not is_local else "requires_local_state_verification",
        "approved_for_changes":False,
    })
report={
    "schema":2,"created_utc":now.isoformat(),"mode":"read_only",
    "note":"Private device data; never upload to public GitHub; live state is NOT proof of WAN independence.",
    "tuya_local_version":version,
    "tuya_local_flow_steps":steps,
    "ha_live_state_access":state_access,
    "device_records":rows,
    "aggregate":dict(summary),
}
filename=dpath/("readiness-"+now.strftime("%Y%m%dT%H%M%SZ")+".json")
fd=os.open(str(filename), os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
with os.fdopen(fd,"w",encoding="utf-8") as f:
    json.dump(report,f,indent=2,sort_keys=True)
    f.write("\n")
    f.flush()
    os.fsync(f.fileno())
# Public workflow emits safe metadata, never device IDs/names or hostnames.
print(json.dumps({"schema":2,"mode":"read_only","unique_cloud_devices":len(clouds),
                  "tuya_local_version":version,"tuya_local_flow_available":bool(steps),
                  "ha_live_state_access":state_access,
                  "local_key_in_cloud_entries":cloud_key_counts["cloud_entry_contains_local_key"],
                  "aggregate":dict(summary),
                  "private_report_staged":True},sort_keys=True))
'''

def main():
    if "running" not in ssh_host("nodeb",["qm","status","905"]):
        raise RuntimeError("VM905 not running")
    script = "exec(__import__('base64').b64decode('" + base64.b64encode(GUEST.encode()).decode() + "'))"
    q=["qm","guest","exec","905","--","docker","exec","homeassistant","python3","-c",script]
    result=json.loads(ssh_host("nodeb",q))
    deadline=time.monotonic()+80
    while not result.get("exited"):
        if not isinstance(result.get("pid"),int) or time.monotonic()>deadline:
            raise RuntimeError("HA guest-agent preflight unavailable")
        time.sleep(1)
        result=json.loads(ssh_host("nodeb",["qm","guest","exec-status","905",str(result["pid"])]))
    if result.get("exitcode")!=0:
        raise RuntimeError("HA private readiness preflight failed")
    return json.loads(result.get("out-data",""))

if __name__=="__main__":
    try:
        print("JNS_TUYA_READINESS",json.dumps(main(),sort_keys=True),flush=True)
    except Exception as exc:
        print("JNS_TUYA_READINESS_BLOCKED",type(exc).__name__,str(exc)[:100],flush=True)
        raise SystemExit(1)
