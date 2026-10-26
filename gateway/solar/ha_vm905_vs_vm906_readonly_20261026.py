#!/usr/bin/env python3
"""Read-only Node A HA-Security and Node B HA-General VM resource/status audit.
No IPs, MACs, private HA config, access tokens or service logs.
"""
import base64,json,shlex,subprocess
REMOTE=r'''
import json,re,subprocess,os,socket,urllib.error,urllib.request
vm=int("__VM__");node="__NODE__";host="__HA__"
assert os.uname().nodename.split(".")[0]==node
def run(cmd,timeout=11):
 try:
  p=subprocess.run(cmd,capture_output=True,text=True,timeout=timeout)
  return p if p.returncode==0 else None
 except (OSError,subprocess.TimeoutExpired):return None
out={"node":node,"vmid":vm}
p=run(["qm","status",str(vm)])
out["state"]=p.stdout.strip().replace("status: ","") if p else "unavailable"
p=run(["qm","config",str(vm)])
if p:
 c=p.stdout
 for k in ("memory","balloon","cores","onboot","sockets"):
  m=re.search(r"^"+k+r":\s*(\d+)",c,re.M)
  if m:out[k+"_configured"]=int(m.group(1))
 m=re.search(r"^name:\s*(\S+)",c,re.M)
 if m:out["name"]=m.group(1)
 out["qga_enabled"]=bool(re.search(r"^agent:\s*(1|enabled=1)",c,re.M))
 out["disk_count"]=len(re.findall(r"^(scsi|sata|virtio)\d+:\s+",c,re.M))
p=run(["pvesh","get","/nodes/"+node+"/qemu/"+str(vm)+"/status/current","--output-format","json"],15)
if p:
 try:
  j=json.loads(p.stdout)
  for k in ("mem","maxmem","balloon"):
   v=j.get(k)
   if isinstance(v,(int,float)):out["pve_"+k+"_GiB"]=round(v/(1024**3),3)
  out["qemu_pid_present"]=isinstance(j.get("pid"),int)
 except ValueError:pass
p=run(["ps","-eo","comm=,rss=,args="],12)
if p:
 for ln in p.stdout.splitlines():
  if not ln.startswith(("kvm ","qemu-system")) or not re.search(r" -id "+str(vm)+r"(?:\s|$)",ln):continue
  fields=ln.split(maxsplit=2)
  if len(fields)>=2 and fields[1].isdigit():out["host_qemu_RSS_GiB"]=round(int(fields[1])/1024**2,3)
  break
for port in (80,8123):
 try:
  with socket.create_connection((host,port),timeout=2):
   out["ha_tcp_"+str(port)]=True
 except OSError:out["ha_tcp_"+str(port)]=False
# Do not fetch private content, only observe an HTTP return code.
for port in (80,8123):
 if out.get("ha_tcp_"+str(port)):
  try:
   with urllib.request.urlopen("http://"+host+(":"+str(port) if port!=80 else "")+"/",timeout=4) as r:
    out["ha_http_"+str(port)]=r.status
  except urllib.error.HTTPError as e:out["ha_http_"+str(port)]=e.code
  except Exception:out["ha_http_"+str(port)]="no_http"
print("JNS_HA_RESOURCE_STATE="+json.dumps(out,sort_keys=True))
'''
def audit(vm,node,host):
 src=REMOTE.replace("__VM__",str(vm)).replace("__NODE__",node).replace("__HA__",host)
 code=base64.b64encode(src.encode()).decode()
 cmd=["ssh","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes","-o","ConnectTimeout=5",node,
      shlex.join(["python3","-c","exec(__import__('base64').b64decode('"+code+"'))"])]
 try:p=subprocess.run(cmd,capture_output=True,text=True,timeout=48)
 except (OSError,subprocess.TimeoutExpired):return {"vmid":vm,"node":node,"error":"ssh_timeout"}
 if p.returncode:return {"vmid":vm,"node":node,"error":"remote_exit"}
 records=[s.split("=",1)[1] for s in p.stdout.splitlines() if s.startswith("JNS_HA_RESOURCE_STATE=")]
 if len(records)!=1:return {"vmid":vm,"node":node,"error":"no_safe_payload"}
 try:return json.loads(records[0])
 except ValueError:return {"vmid":vm,"node":node,"error":"bad_payload"}
print("JNS_HA_ROLE_MEMORY_CHECK_START")
print("HA_SECURITY="+json.dumps(audit(906,"nodea","ha-security.home.arpa"),sort_keys=True))
print("HA_GENERAL="+json.dumps(audit(905,"nodeb","ha-general.home.arpa"),sort_keys=True))
print("JNS_HA_ROLE_MEMORY_CHECK_END")
