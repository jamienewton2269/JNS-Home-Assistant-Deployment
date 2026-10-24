#!/usr/bin/env python3
"""KC868-A16 non-invasive network and firmware survey. No relays/OTA/restarts."""
import subprocess, shlex, json, time, re

def run(args, timeout=16):
    try:
        p=subprocess.run(args,capture_output=True,text=True,timeout=timeout)
        return {"rc":p.returncode,"out":p.stdout[-24000:],"err":p.stderr[-350:]}
    except Exception as e: return {"rc":-1,"err":type(e).__name__}

def ssh(node, command, timeout=20):
    return run(["ssh","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes","-o","ConnectTimeout=6",node,shlex.join(command)],timeout)

def guest(node, vm, command):
    a=ssh(node,["qm","guest","exec",str(vm),"--","/bin/sh","-c",command],25)
    try:d=json.loads(a["out"])
    except Exception:return {"error":"guest_not_available","detail":a["err"][-150:]}
    for n in range(10):
        if d.get("exited"):break
        time.sleep(.5)
        a=ssh(node,["qm","guest","exec-status",str(vm),str(d["pid"])],20)
        try:d=json.loads(a["out"])
        except Exception:break
    return {"rc":d.get("exitcode"),"out":d.get("out-data","")[-17000:],"err":d.get("err-data","")[-150:]}

print("KC868_A16_READ_ONLY_NETWORK_AUDIT",time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime()),flush=True)
for node in ("nodea","nodeb"):
    checks={
    "identity":"hostname -s; ip -br -4 addr show",
    "route_to_old_esp":"ip route get 10.10.10.252",
    "known_neighbours":"ip -4 neigh show | grep -Ei '10\\.10\\.10\\.252|78:1c:3c:ce:82:5b|10\\.10\\.110\\.' | head -35",
    "physical_interfaces":"ip -br link show | head -22",
    "arp_capability":"command -v arping || true",
    "usb_serial":"ls -l /dev/ttyUSB* 2>/dev/null || true; lsusb 2>/dev/null | grep -Ei 'ch340|ch341|serial' | head -8 || true",
    "hostname_resolution":"for h in alarmpanel.home.arpa kc868-a16.home.arpa doorbell.home.arpa esphome-web-630464.home.arpa; do getent ahostsv4 \"$h\" | head -1; done",
    }
    for label,cmd in checks.items():
        res=ssh(node,["/bin/sh","-c",cmd])
        print("NODE",node,label,"rc",res["rc"],"output",res["out"][:3400],"err",res["err"][:120],flush=True)
    # Only ICMP and direct TCP checks; never toggle I/O.
    for dest in ("10.10.10.252",):
        x=ssh(node,["ping","-n","-c","1","-W","2",dest])
        print("PING",node,dest,"rc",x["rc"],"detail",(x["out"]+x["err"])[-420:],flush=True)
    # Proxmox host isn't homeassistant container; use guest exec for file read.
print("HA900_STORED_ESPHOME_CONFIG",flush=True)
raw=guest("nodea",900,"cat /mnt/data/supervisor/homeassistant/esphome/alarmpanel.yaml")
if raw.get("rc")!=0: print("CONFIG_READ_FAILED",raw.get("err"),flush=True)
else:
    lines=raw["out"].splitlines()
    for n,line in enumerate(lines,1):
        if re.search(r"(?i)password|secret|key|ssid|username|api:|ota:|web_server:|mqtt:|captive|cert",line):
            continue
        if n<=85 or re.search(r"(?i)door|bell|chime|mqtt|on_press|on_click|on_release|Y10|X[0-9]{2}|id: out_y10",line):
            print("YAML",n,line[:160],flush=True)
print("KC868_A16_NETWORK_AUDIT_DONE",flush=True)
