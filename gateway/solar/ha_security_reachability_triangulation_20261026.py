#!/usr/bin/env python3
"""Read-only HA-Security DNS and TCP reachability from Node A/B/C.
Never prints addresses, MACs, auth or HTTP bodies.
"""
import base64,json,os,shlex,socket,subprocess
def probe():
    results={"host":os.uname().nodename.split(".")[0]}
    for name in ("ha-security.home.arpa","ha-primary.home.arpa","ha-general.home.arpa"):
        data={}
        try:
            a=socket.getaddrinfo(name,None,type=socket.SOCK_STREAM)
            data["dns_resolution"]=bool(a)
            data["has_ipv4"]=any(x[0]==socket.AF_INET for x in a)
            data["has_ipv6"]=any(x[0]==socket.AF_INET6 for x in a)
        except OSError:
            data["dns_resolution"]=False
        for port in ((80,443,8123) if name=="ha-security.home.arpa" else (8123,)):
            try:
                with socket.create_connection((name,port),timeout=3):
                    data["tcp_"+str(port)]=True
            except OSError:data["tcp_"+str(port)]=False
        results[name.split(".",1)[0]]=data
    return results
SRC=r'''
import json,os,socket,subprocess,re
def test(name):
 d={}
 try:
  a=socket.getaddrinfo(name,None,type=socket.SOCK_STREAM)
  d["dns_resolution"]=bool(a)
  d["has_ipv4"]=any(x[0]==socket.AF_INET for x in a)
  d["has_ipv6"]=any(x[0]==socket.AF_INET6 for x in a)
 except OSError:d["dns_resolution"]=False
 for port in ((80,443,8123) if name=="ha-security.home.arpa" else (8123,)):
  try:
   with socket.create_connection((name,port),timeout=3):d["tcp_"+str(port)]=True
  except OSError:d["tcp_"+str(port)]=False
 return d
host=os.uname().nodename.split(".")[0]
if host not in ("nodea","nodeb"):raise SystemExit(77)
out={"host":host}
for name in ("ha-security.home.arpa","ha-primary.home.arpa","ha-general.home.arpa"):
 out[name.split(".",1)[0]]=test(name)
if host=="nodea":
 p=subprocess.run(["qm","config","906"],capture_output=True,text=True,timeout=10)
 if p.returncode==0:
  net=re.search(r"^net0:\s*(.*)",p.stdout,re.M)
  out["vm906_net0_present"]=bool(net)
  if net:out["vm906_net0_link_down"]=bool(re.search(r"(?:^|,)link_down=1(?:,|$)",net.group(1)))
print("JNS_HA_SECURITY_NET_TRIANGULATION="+json.dumps(out,sort_keys=True))
'''
def remote(name):
    enc=base64.b64encode(SRC.encode()).decode()
    cmd=["ssh","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes","-o","ConnectTimeout=5",name,
         shlex.join(["python3","-c","exec(__import__('base64').b64decode('"+enc+"'))"])]
    try:r=subprocess.run(cmd,capture_output=True,text=True,timeout=56)
    except (OSError,subprocess.TimeoutExpired):return {"access":"timeout"}
    if r.returncode:return {"access":"unavailable"}
    lines=[q.split("=",1)[1] for q in r.stdout.splitlines() if q.startswith("JNS_HA_SECURITY_NET_TRIANGULATION=")]
    try:return json.loads(lines[-1])
    except (ValueError,IndexError):return {"access":"no_safe_result"}
for name in ("nodea","nodeb"):
    print(name.upper()+"="+json.dumps(remote(name),sort_keys=True),flush=True)
print("NODEC="+json.dumps(probe(),sort_keys=True),flush=True)
print("JNS_READONLY=yes")
