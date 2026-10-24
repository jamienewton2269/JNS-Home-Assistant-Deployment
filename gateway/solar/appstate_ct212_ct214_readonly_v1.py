#!/usr/bin/env python3
"""Read-only application-state migration source audit inside Node B containers."""
import base64,json,shlex,subprocess
SOURCE=r'''
import json,subprocess
HOSTNAMES={212:"mqtt-infra-a",214:"zigbee2mqtt-a"}
PATHS={
212:["/etc/mosquitto","/var/lib/mosquitto","/var/log/mosquitto",
     "/etc/systemd/system/mosquitto.service.d","/opt/mosquitto"],
214:["/opt/zigbee2mqtt/data","/opt/zigbee2mqtt",
     "/var/lib/zigbee2mqtt","/etc/zigbee2mqtt",
     "/etc/systemd/system/zigbee2mqtt.service","/etc/systemd/system/zigbee2mqtt.service.d"],
}
def exec_ct(ct,sh):
 try:p=subprocess.run(["pct","exec",str(ct),"--","/bin/sh","-c",sh],capture_output=True,text=True,timeout=25)
 except (OSError,subprocess.TimeoutExpired):return None
 return p
out={}
for ct,paths in PATHS.items():
 d={"container_running":False,"hostname_expected":False,"paths":{}}
 stat=subprocess.run(["pct","status",str(ct)],capture_output=True,text=True)
 d["container_running"]="running" in stat.stdout
 for path in paths:
  safe=path.replace("'","")
  p=exec_ct(ct,"if test -d '"+safe+"'; then echo directory; elif test -f '"+safe+"'; then echo file; else echo absent; fi")
  typ=p.stdout.strip() if p and p.returncode==0 else "unavailable"
  if typ in ("directory","file"):
   size=exec_ct(ct,"du -sk '"+safe+"' 2>/dev/null | awk '{print $1}'")
   try:kib=int(size.stdout.strip()) if size and size.returncode==0 else None
   except ValueError:kib=None
   d["paths"][path]={"type":typ,"kib":kib}
  else:d["paths"][path]={"type":typ}
 h=exec_ct(ct,"hostname -s")
 d["hostname_expected"]=bool(h and h.stdout.strip()==HOSTNAMES[ct])
 svc="mosquitto" if ct==212 else "zigbee2mqtt"
 r=exec_ct(ct,"systemctl is-active "+svc+" 2>/dev/null || true")
 d["service_active"]=bool(r and r.stdout.strip()=="active")
 out[str(ct)]=d
print("JNS_APP_MIGRATION_JSON="+json.dumps(out,sort_keys=True))
'''
def main():
 command=["python3","-c","exec(__import__('base64').b64decode('"+base64.b64encode(SOURCE.encode()).decode()+"'))"]
 try:p=subprocess.run(["ssh","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes","nodeb",shlex.join(command)],capture_output=True,text=True,timeout=150)
 except (OSError,subprocess.TimeoutExpired):print("APP_MIGRATION_AUDIT_BLOCKED=transport_timeout");return
 if p.returncode:print("APP_MIGRATION_AUDIT_BLOCKED=source_exit_"+str(p.returncode));return
 for line in p.stdout.splitlines():
  if line.startswith("JNS_APP_MIGRATION_JSON="):print(line)
if __name__=="__main__":main()
