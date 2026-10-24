#!/usr/bin/env python3
"""Targeted KC868-A16 network reachability audit; no configuration changes."""
import subprocess, shlex, time
def ssh(node, cmd):
    p=subprocess.run(["ssh","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes",node,shlex.join(["/bin/sh","-c",cmd])],capture_output=True,text=True,timeout=22)
    print(node,"rc",p.returncode,"out",p.stdout[-2400:].strip(),"err",p.stderr[-200:].strip(),flush=True)

print("KC868_TARGETED_REACHABILITY",time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime()),flush=True)
ssh("nodeb","ip route get 10.10.10.184; ip -4 neigh show 10.10.10.184 dev vmbr0")
ssh("nodeb","arping -c 3 -w 5 -I vmbr0 10.10.10.184")
ssh("nodeb","ping -n -c 2 -W 2 -I 10.10.10.163 10.10.10.184")
ssh("nodeb","ip -4 neigh show 10.10.10.184 dev vmbr0")
ssh("nodeb",'''python3 -c 'import socket
for port in (6053,80,3232):
 s=socket.socket();s.settimeout(2)
 try:s.connect(("10.10.10.184",port));print("TCP",port,"OPEN")
 except OSError as e:print("TCP",port,type(e).__name__)
 finally:s.close()' ''')
ssh("nodeb","bridge fdb show | grep -i '78:1c:3c:ce:82:5b' | head -8 || true")
print("KC868_TARGETED_AUDIT_DONE",flush=True)
