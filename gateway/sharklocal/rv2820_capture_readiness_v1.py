#!/usr/bin/env python3
"""Passive RV2820 traffic capture readiness. NO captures, probes or network changes.
Output tool availability and interfaces only; no addresses, keys or traffic.
"""
import json
import re
import shutil
import subprocess

SSH=["ssh","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes","-o","ConnectTimeout=5"]
INSPECT=r'''
set -eu
printf 'HOST=%s\n' "$(hostname -s)"
printf 'TCPDUMP=%s\n' "$(command -v tcpdump >/dev/null 2>&1 && echo yes || echo no)"
printf 'TSHARK=%s\n' "$(command -v tshark >/dev/null 2>&1 && echo yes || echo no)"
printf 'DUMPCAP=%s\n' "$(command -v dumpcap >/dev/null 2>&1 && echo yes || echo no)"
printf 'IP_CMD=%s\n' "$(command -v ip >/dev/null 2>&1 && echo yes || echo no)"
if command -v ip >/dev/null 2>&1; then
 ip -o link show | sed -E 's/^[0-9]+: ([^:@ ]+).*$/IFACE=\1/' | grep '^IFACE=' || :
fi
'''

def inspect_local():
    try:
        p=subprocess.run(["bash","-c",INSPECT],capture_output=True,text=True,timeout=12)
        return decode(p.returncode,p.stdout)
    except (OSError,subprocess.TimeoutExpired):
        return {"status":"unavailable"}

def decode(code,stdout):
    if code!=0:return {"status":"unavailable"}
    d={"status":"ok","tools":{},"interfaces":[]}
    for line in stdout.splitlines():
        if "=" not in line:continue
        k,v=line.split("=",1)
        if k in {"TCPDUMP","TSHARK","DUMPCAP","IP_CMD"}:d["tools"][k.lower()]=v=="yes"
        if k=="IFACE" and re.fullmatch(r"[A-Za-z0-9_.-]{1,32}",v):
            d["interfaces"].append(v)
    return d

def inspect_remote(node):
    try:
        p=subprocess.run(SSH+[node,"bash -s"],input=INSPECT,capture_output=True,text=True,timeout=18)
        return decode(p.returncode,p.stdout)
    except (OSError,subprocess.TimeoutExpired):
        return {"status":"ssh_unavailable"}

print("JNS_RV2820_CAPTURE_READINESS="+json.dumps({
    "mode":"read_only","captures_started":0,"network_settings_changed":0,
    "nodec":inspect_local(),
    "nodea":inspect_remote("nodea"),
    "nodeb":inspect_remote("nodeb"),
    "visibility_note":"Switched and Wi-Fi unicast requires verified SPAN/TAP/AP/router vantage; network interfaces alone do not prove visibility"
},sort_keys=True))
