#!/usr/bin/env python3
"""Write VM905-only operator instructions from exact Tuya LAN discovery."""
import base64,json,sys,time
sys.path.insert(0,"gateway/arrival_lighting")
from readiness_probe import ssh_host
GUEST=r'''
import collections,datetime,json,os,pathlib
root=pathlib.Path("/config/.jns_tuya_freedom")
sources=sorted(root.glob("udp-discovery-*.json"))
if not sources:raise RuntimeError("no_discovery")
doc=json.loads(sources[-1].read_text())
report=json.loads((root/"latest-live.json").read_text())
names={str(r.get("native_device_id","")).lower():r.get("name","")
       for r in report.get("physical_devices",[])}
summary=collections.Counter()
lines=["# Tuya Freedom — local host repair checklist","",
       "This file stays on HA-General. No Tuya configuration has been changed.",
       "Use the existing Tuya Local integration Configure/Options flow, not Delete.",
       ""]
for row in doc.get("devices",[]):
    deviceid=str(row.get("native_id","")).lower()
    old=row.get("configured_host")
    found=row.get("discovered_address")
    identity=row.get("scanner_returned_id_matches")
    decision=("await_physical_identity_check" if found and identity is not True
              else "candidate_host_update" if found and old!=found
              else "no_address_discovered" if not found
              else "address_unchanged")
    summary[decision]+=1
    lines.extend(["## "+(names.get(deviceid) or "Unnamed Tuya device"),"",
                  "- Current configured host: "+str(old),
                  "- LAN discovery host: "+str(found or "Not discovered"),
                  "- Native ID check: "+str(identity),
                  "- Proposed action: "+decision,
                  "- If identity is verified, open HA-General → Settings → Devices & Services → Tuya Local → "
                  "the existing device → Configure, change Host only, and save. "
                  "Preserve local key, entity IDs, type and protocol.",
                  ""])
lines.extend(["Never infer an IP for an undiscovered device. "
              "Do not disable native cloud integrations or re-pair devices.",
              ""])
output=root/"LOCAL_REPAIR_INSTRUCTIONS.md"
if output.is_symlink():raise RuntimeError("unsafe_symlink")
temp=root/".LOCAL_REPAIR_INSTRUCTIONS.new"
fd=os.open(str(temp),os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
with os.fdopen(fd,"w") as f:
    f.write("\n".join(lines)+"\n")
    f.flush();os.fsync(f.fileno())
os.replace(temp,output)
os.chmod(output,0o600)
print(json.dumps({"status":"PRIVATE_CHECKLIST_UPDATED",
                  "summary":dict(summary),"configuration_changed":False,
                  "path":"/config/.jns_tuya_freedom/LOCAL_REPAIR_INSTRUCTIONS.md"}))
'''
def main():
    if "running" not in ssh_host("nodeb",["qm","status","905"]):
        raise RuntimeError("vm905_down")
    src="exec(__import__('base64').b64decode('"+base64.b64encode(GUEST.encode()).decode()+"'))"
    r=json.loads(ssh_host("nodeb",["qm","guest","exec","905","--","docker","exec","homeassistant","python3","-c",src]))
    pid=r.get("pid")
    end=time.monotonic()+95
    while not r.get("exited"):
        if not isinstance(pid,int) or time.monotonic()>end:
            raise RuntimeError("guest_agent_timeout")
        time.sleep(2)
        r=json.loads(ssh_host("nodeb",["qm","guest","exec-status","905",str(pid)]))
    if r.get("exitcode")!=0:raise RuntimeError("private_report_failed")
    return json.loads(r.get("out-data",""))
if __name__=="__main__":
    try:print("JNS_TUYA_LOCAL_REPAIR_CHECKLIST",json.dumps(main(),sort_keys=True),flush=True)
    except Exception as e:
        print("JNS_TUYA_LOCAL_REPAIR_CHECKLIST_BLOCKED",type(e).__name__,str(e)[:80],flush=True)
        raise SystemExit(1)
