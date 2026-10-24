#!/usr/bin/env python3
"""JNS HA-Security VM906: enumerate explicitly authorised READ-ONLY access only."""
import os, subprocess, socket, shutil, json
def cmd(name,args,timeout=12):
    try:
        p=subprocess.run(args,capture_output=True,text=True,timeout=timeout)
        print(name,"rc",p.returncode,"out",p.stdout[-2500:],"err",p.stderr[-350:],flush=True)
    except Exception as e:print(name,type(e).__name__,str(e)[:160],flush=True)
print("VM906_EXISTING_AUTHORIZED_ACCESS_AUDIT",flush=True)
print("RUNNER_USER",os.getuid(),flush=True)
for hostname in ("ha-security.home.arpa","nodec.home.arpa"):
    try: print("RESOLUTION",hostname,sorted({x[4][0] for x in socket.getaddrinfo(hostname,None)}),flush=True)
    except Exception as e:print("RESOLUTION_ERROR",hostname,type(e).__name__,flush=True)
cmd("AUTHORIZED_SUDO_CAPABILITIES",["sudo","-n","-l"],timeout=9)
for key in ("/usr/sbin/qm","/usr/bin/pvesh","/usr/local/sbin/jns-gateway-exec"):
    print("EXECUTABLE_EXISTS",key,os.path.isfile(key),flush=True)
# Checks only: would sudo allow these exact read-only calls? '-n' prevents password prompts.
for argv in (["/usr/sbin/qm","status","906"],["/usr/bin/pvesh","get","/nodes/nodec/qemu/906/status/current"]):
    cmd("ROOTED_VM906_READONLY",["sudo","-n",*argv],timeout=12)
for path in ("/etc/pve/nodes/nodec/qemu-server/906.conf","/etc/pve/qemu-server/906.conf"):
    try:print("VM_CONFIG_METADATA",path,"exists",os.path.exists(path),"can_read",os.access(path,os.R_OK),flush=True)
    except Exception as e:print("VM_CONFIG_METADATA_ERROR",type(e).__name__,flush=True)
# Check HA-Security HTTPS/HTTP without credentials, emit HTTP status only and no body.
for host in ("ha-security.home.arpa",):
    try:
        with socket.create_connection((host,8123),timeout=4):print("HA_SECURITY_TCP8123_OPEN",flush=True)
    except OSError as e:print("HA_SECURITY_TCP8123_ERROR",type(e).__name__,flush=True)
print("VM906_AUTHORIZED_ACCESS_AUDIT_COMPLETE",flush=True)
