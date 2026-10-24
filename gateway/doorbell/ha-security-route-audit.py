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

print("=== CURRENT NODE C / VM PLACEMENT ===",flush=True)
for host in ("nodea","nodeb"):
    r=run(["ssh","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes",host,"qm list | grep -E '(^|[[:space:]])906[[:space:]]' || true"],20)
    print("VM906_OWNER_CHECK",host,"rc",r[0],"out",r[1],"err",r[2],flush=True)
for host in ("10.10.110.13",):
    try: print("DNS",host,sorted({x[4][0] for x in socket.getaddrinfo(host,None)}),flush=True)
    except Exception as e:print("DNS",host,type(e).__name__,flush=True)
    for variant,extra in (("default",[]),("nodec-alias",["-o","HostKeyAlias=nodec"]),("name",["-o","HostKeyAlias=nodec.home.arpa"])):
        r=run(["ssh","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes","-o","ConnectTimeout=5",*extra,"root@"+host,"hostname -s; command -v qm; qm status 906"],14)
        print("NODEC_DIRECT",variant,"rc",r[0],"out",r[1],"err",r[2],flush=True)
for host in ("nodeb","nodea"):
    cmd="for alias in 10.10.110.13 nodec nodec.home.arpa; do ssh -o BatchMode=yes -o StrictHostKeyChecking=yes -o ConnectTimeout=4 root@\\$alias 'hostname -s; qm status 906' 2>&1 | head -2; done"
    r=run(["ssh","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes",host,cmd],25)
    print("HOP_TO_NODEC",host,"rc",r[0],"out",r[1],"err",r[2],flush=True)
print("=== NODE C PLACEMENT CHECK COMPLETE ===",flush=True)

print("=== TRUSTED NODE A/B TO NODE C AUTH CHECK ===",flush=True)
for hop in ("nodea","nodeb"):
    for dest in ("nodec","nodec.home.arpa","10.10.110.13"):
        inner=["ssh","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes","-o","ConnectTimeout=4","root@"+dest,"hostname -s"]
        outer=["ssh","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes",hop, __import__('shlex').join(inner)]
        result=run(outer,12)
        print("TRUSTED_HOP",hop,dest,"rc",result[0],"out",result[1][:100],"error",result[2][:180],flush=True)
    for dest in ("nodec","nodec.home.arpa","10.10.110.13"):
        outer=["ssh","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes",hop,
        __import__('shlex').join(["ssh-keygen","-F",dest])]
        result=run(outer,12)
        print("HOSTKEY_TRUST",hop,dest,"rc",result[0],"found",bool(result[1]),"err",result[2][:100],flush=True)
scan=run(["ssh-keyscan","-T","5","-t","ed25519","10.10.110.13"],9)
if scan[0]==0 and scan[1]:
    fp=run(["ssh-keygen","-lf","-","-E","sha256"],7)
    print("NODEC_SCAN_REACHABLE",bool(scan[1]),flush=True)
else:print("NODEC_SCAN",scan[0],scan[2],flush=True)
print("=== TRUST ROUTE AUDIT DONE ===",flush=True)

print("=== EXISTING RUNNER CAPABILITIES (READ ONLY) ===",flush=True)
for cmd in (["hostname","-s"],["command","-v","qm"],["command","-v","pvesh"],["command","-v","pct"]):
    z=run(cmd,7);print("RUNNER_CMD",cmd[0:3],z[0],z[1][:110],flush=True)
for cmd in (["/bin/sh","-c","test -x /usr/local/sbin/jns-gateway-exec && echo JNS_GATEWAY_PRESENT || true"],
            ["/bin/sh","-c","test -r /opt/jns-ha-control-plane/README.txt && echo CONTROL_PLANE_PRESENT || true"],
            ["/bin/sh","-c","ls -ld /run/proxmox /etc/pve /etc/pve/nodes 2>/dev/null || true"]):
    z=run(cmd,7);print("RUNNER_PATHS",z[0],z[1][:180],flush=True)
for target in ("ha-security.home.arpa","10.10.110.13"):
    z=run(["/bin/sh","-c","timeout 4 bash -c 'echo > /dev/tcp/"+target+"/22' 2>/dev/null"],7)
    print("TCP_SSH",target,"available",z[0]==0,flush=True)
print("=== CAPABILITY AUDIT COMPLETE ===",flush=True)
