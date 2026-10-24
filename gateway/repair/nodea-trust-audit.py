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


# Prove direct auth with a TEMPORARY known_hosts entry, sourced from Node A via
# a verified SSH session on Node B. Never use accept-new or disable verification.
import tempfile,os
rc,pub,err=remote(["ssh","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes","root@nodea.home.arpa","cat /etc/ssh/ssh_host_ed25519_key.pub"])
if rc==0 and pub.split()[:1]==["ssh-ed25519"] and len(pub.split())>=2:
    observed=subprocess.run(["ssh-keyscan","-T","4","-t","ed25519","nodea.home.arpa"],capture_output=True,text=True,timeout=8)
    match=any(line.split()[1:3]==pub.split()[:2] for line in observed.stdout.splitlines() if line and not line.startswith("#"))
    print("NODEA_CROSS_VERIFIED",match,flush=True)
    if match:
        with tempfile.NamedTemporaryFile(mode="w",prefix="jns-ssh-attested-",delete=False) as f:
            f.write("nodea.home.arpa "+pub.split()[0]+" "+pub.split()[1]+"\n")
            file=f.name
        try:
            rc,out,err=run(["ssh","-o","UserKnownHostsFile="+file,"-o","GlobalKnownHostsFile=/dev/null",
                "-o","BatchMode=yes","-o","StrictHostKeyChecking=yes","-o","ConnectTimeout=5",
                "root@nodea.home.arpa","hostname -s"],timeout=12)
            print("NODEC_TO_NODEA_WITH_VERIFIED_PIN","rc",rc,"identity",out[:30],"error",err[:140],flush=True)
        finally:os.unlink(file)
else:print("NODEA_PIN_TEST_BLOCKED",rc,err[:140],flush=True)
