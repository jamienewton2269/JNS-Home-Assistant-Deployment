#!/usr/bin/env python3
"""Read-only target host discovery for HA-Security VM906."""
import subprocess,shlex,socket
def run(args,timeout=14):
    try:
        p=subprocess.run(args,capture_output=True,text=True,timeout=timeout)
        return p.returncode,p.stdout.strip()[-900:],p.stderr.strip()[-250:]
    except Exception as e:return -1,"",type(e).__name__+": "+str(e)[:100]
print("=== HA-SECURITY VM906 ROUTE DISCOVERY ===",flush=True)
for host in ("nodec.home.arpa","nodec","nodeb.home.arpa","ha-security.home.arpa"):
    try:
        ip=sorted({x[4][0] for x in socket.getaddrinfo(host,None)})
    except Exception as e:ip=[type(e).__name__]
    print("DNS",host,ip,flush=True)
for host in ("nodec.home.arpa","nodec","nodeb","nodea"):
    cmd=["ssh","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes","-o","ConnectTimeout=5", "root@"+host,"hostname -s; command -v qm || true; qm status 906 2>/dev/null || true"]
    code,out,err=run(cmd)
    print("SSH_PROBE",host,"rc",code,"out",out,"err",err,flush=True)
print("=== ROUTE DISCOVERY DONE ===",flush=True)
