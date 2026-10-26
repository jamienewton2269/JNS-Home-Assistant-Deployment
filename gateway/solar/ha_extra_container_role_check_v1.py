#!/usr/bin/env python3
"""Read-only addon role inventory on HA-Primary/General via QGA.
Print normalized HAOS container IDs only when they match expected structured
names. Never print arbitrary Docker image, environment, labels or commands.
"""
import json,re,shlex,subprocess,time,hashlib
GUESTS={902:"nodea",905:"nodeb"}
def ssh(host,args,timeout=24):
 try:p=subprocess.run(["ssh","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes",
     "-o","ConnectTimeout=5",host,shlex.join(args)],capture_output=True,text=True,timeout=timeout)
 except (OSError,subprocess.TimeoutExpired):return None
 return p.stdout if p.returncode==0 else None
def qga(node,vm):
 raw=ssh(node,["qm","guest","exec",str(vm),"--","docker","ps","--format","{{json .}}"],30)
 if raw is None:return {"status":"unavailable"}
 try:j=json.loads(raw)
 except ValueError:return {"status":"bad_response"}
 for _ in range(20):
  if j.get("exited"):break
  if j.get("pid") is None:break
  time.sleep(.4)
  raw=ssh(node,["qm","guest","exec-status",str(vm),str(j["pid"])],10)
  if raw is None:break
  try:j=json.loads(raw)
  except ValueError:break
 if j.get("exitcode")!=0:return {"status":"guest_failed"}
 names=[]
 for line in (j.get("out-data") or "").splitlines():
  try:x=json.loads(line)
  except ValueError:continue
  name=x.get("Names","")
  if not isinstance(name,str):continue
  if name in ("homeassistant","hassio_supervisor","hassio_observer","hassio_audio","hassio_dns","hassio_multicast","hassio_cli"):continue
  # HAOS addons follow addon_<repository-id>_<slug>; output only the last
  # recognized whitelisted suffix, never arbitrary names.
  name=name.lower().strip("/")
  known=("ssh","configurator","studio_code","vscode","mqtt","mosquitto",
         "esphome","matter_server","zigbee2mqtt","piper","whisper","samba",
         "node_red","nodered","go2rtc","frigate","rtsp","influxdb","mariadb",
         "music_assistant","mpd","file_editor","openwakeword","backup","terminal")
  matches=[k for k in known if name.endswith("_"+k) or name==k]
  names.append({"role":matches[-1] if matches else "unclassified_addon",
                "is_haos_addon":name.startswith("addon_"),
                "name_fingerprint":hashlib.sha256(name.encode()).hexdigest()[:9]})
 return {"status":"ok","additional_containers":names}
for vm,node in GUESTS.items():print("HA"+str(vm)+"_OTHER_SERVICE_ROLES="+json.dumps(qga(node,vm),sort_keys=True))
