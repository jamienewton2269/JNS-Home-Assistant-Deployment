#!/usr/bin/env python3
"""Confirm live ESPHome native API reachability without any switching commands."""
import subprocess,shlex,time
def ssh(node,cmd,timeout=22):
    p=subprocess.run(["ssh","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes",node,shlex.join(["/bin/sh","-c",cmd])],capture_output=True,text=True,timeout=timeout)
    print("PROBE",node,"rc",p.returncode,"out",p.stdout[-3600:].strip(),"err",p.stderr[-200:].strip(),flush=True)
print("KC868_LIVE_ESPHOME_API_AUDIT",time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime()),flush=True)
for node in ("nodea","nodeb"):
    ssh(node,"getent ahostsv4 alarmpanel.home.arpa | head -2 || true; ip route get 10.10.110.184; ip -4 neigh show 10.10.110.184 || true")
ssh("nodeb","arping -I vmbr0 -c 2 -w 4 10.10.110.184")
ssh("nodeb","ping -n -c 2 -W 2 10.10.110.184")
ssh("nodeb",'''python3 -c 'import socket
for port in (6053,80,3232):
 s=socket.socket();s.settimeout(2)
 try:s.connect(("10.10.110.184",port));print("TCP",port,"OPEN")
 except OSError as e:print("TCP",port,type(e).__name__)
 finally:s.close()' ''')
ssh("nodeb","ip -4 neigh show 10.10.110.184")
# Home Assistant container dependency inventory, no authenticated device communication or actuation.
ssh("nodeb","qm guest exec 905 -- docker exec homeassistant python3 -c 'import importlib.util; print(\"aioesphomeapi_installed\",bool(importlib.util.find_spec(\"aioesphomeapi\")))' ")
print("KC868_API_AUDIT_DONE",flush=True)
