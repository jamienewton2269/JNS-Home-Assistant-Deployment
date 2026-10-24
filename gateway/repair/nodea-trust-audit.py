#!/usr/bin/env python3
"""Read-only trust audit for Node A, via already trusted Node B."""
import subprocess, shlex
def run(args,timeout=15):
    try:
        p=subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=timeout)
        return p.returncode,p.stdout.strip(),p.stderr.strip()
    except Exception as e: return 125,"",type(e).__name__
def remote(args):
    return run(["ssh","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes","nodeb",shlex.join(args)],timeout=18)
print("JNS_NODEA_TRUST_AUDIT",flush=True)
for args in (["hostname","-s"],["pvecm","nodes"],["getent","hosts","nodea.home.arpa"]):
    rc,out,err=remote(args)
    print("NODEB",shlex.join(args),"rc",rc,"result",out[:700],"error_type",err[:100] if rc else "",flush=True)
r=remote(["ssh","-o","BatchMode=yes","-o","ConnectTimeout=5","-o","StrictHostKeyChecking=yes",
          "root@nodea.home.arpa","hostname -s; ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub -E sha256"])
print("NODEB_TO_NODEA","rc",r[0],"result",r[1][:250],"error",r[2][:180],flush=True)
r2=remote(["ssh","-o","BatchMode=yes","-o","ConnectTimeout=5","-o","StrictHostKeyChecking=yes",
           "root@nodea","hostname -s; ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub -E sha256"])
print("NODEB_TO_NODEA_SHORT","rc",r2[0],"result",r2[1][:250],"error",r2[2][:180],flush=True)
try:
    s=subprocess.run(["ssh-keyscan","-T","4","-t","ed25519","nodea.home.arpa"],capture_output=True,text=True,timeout=8)
    p=subprocess.run(["ssh-keygen","-lf","-","-E","sha256"],input=s.stdout,capture_output=True,text=True,timeout=5)
    print("NODEC_SCAN_FINGERPRINT",p.stdout.strip()[:180],"keyscan_rc",s.returncode,flush=True)
except Exception as e:print("NODEC_SCAN_BLOCKED",type(e).__name__,flush=True)
print("DONE_READ_ONLY",flush=True)
