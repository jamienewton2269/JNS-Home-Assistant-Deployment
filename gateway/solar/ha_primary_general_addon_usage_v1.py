#!/usr/bin/env python3
"""Read-only HAOS Docker/Supervisor role footprint from Proxmox QGA.
Classifies names locally; never emits raw container names/images, log content,
configuration, secrets, device IDs, addresses or tokens.
"""
import json,shlex,subprocess,time,re
ROLES={902:"nodea",905:"nodeb",906:"nodea"}
TYPES=("core","supervisor","observer","dns","audio","multicast","cli","piper",
       "mqtt","mosquitto","zigbee2mqtt","esphome","mariadb","mysql","postgres",
       "influxdb","go2rtc","frigate","ffmpeg","rtsp","webrtc","camera",
       "node-red","nodered","ssh","samba","studio_code","file_editor","matter",
       "backup","watchdog","other")
def ssh(host,cmd,timeout=18):
 try:p=subprocess.run(["ssh","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes","-o","ConnectTimeout=5",host,shlex.join(cmd)],capture_output=True,text=True,timeout=timeout)
 except (OSError,subprocess.TimeoutExpired):return None
 return p.stdout if p.returncode==0 else None
def qga(vm,host,command):
 raw=ssh(host,["qm","guest","exec",str(vm),"--",*command],28)
 if raw is None:return {"status":"qga_unavailable"}
 try:j=json.loads(raw)
 except ValueError:return {"status":"bad_qga"}
 for _ in range(30):
  if j.get("exited"):break
  if "pid" not in j:break
  time.sleep(.4)
  raw=ssh(host,["qm","guest","exec-status",str(vm),str(j["pid"])],10)
  if raw is None:break
  try:j=json.loads(raw)
  except ValueError:break
 if not j.get("exited"):return {"status":"timeout"}
 if j.get("exitcode")!=0:return {"status":"guest_command_failed","code":j.get("exitcode")}
 return {"status":"ok","lines":(j.get("out-data") or "").splitlines()}
def classify(name):
 name=name.lower().lstrip("/")
 if name=="homeassistant":return "core"
 if name.startswith("hassio_"):
  suffix=name[7:]
  if suffix in ("supervisor","observer","dns","audio","multicast","cli"):return suffix
 if name.startswith("addon_"):
  slug=name[6:].replace("core_","",1) if name[6:].startswith("core_") else name[6:]
  mapping=(("ssh","ssh"),("configurator","file_editor"),("studio","studio_code"),
   ("vscode","studio_code"),("mosquitto","mqtt"),("zigbee","zigbee2mqtt"),
   ("esphome","esphome"),("mariadb","mariadb"),("mysql","mysql"),
   ("influxdb","influxdb"),("frigate","frigate"),("go2rtc","go2rtc"),
   ("matter","matter"),("piper","piper"),("whisper","tts"),
   ("samba","samba"),("nodered","nodered"),("node-red","nodered"),
   ("backup","backup"),("rtsp","rtsp"),("web","web"),("music","audio"),
   ("mpd","audio"),("chromium","browser"),("librespot","audio"))
  for word,key in mapping:
   if word in slug:return "addon_"+key
  return "addon_other"
 if name in ("hassio","hassio_audio","hassio_dns"):return "supervisor"
 return "other"
def mb(text):
 # Docker: 183.3MiB / 2GiB
 v=text.split(" / ",1)[0].strip()
 m=re.match(r"^([0-9.]+)\s*([A-Za-z]+)$",v)
 if not m:return None
 number=float(m.group(1));unit=m.group(2)
 scale={"B":1/1048576,"kB":1/1024,"KB":1/1024,"KiB":1/1024,
        "MB":1,"MiB":1,"GB":1000/1.048576,"GiB":1024}
 return round(number*scale[unit],1) if unit in scale else None
def audit(vm,host):
 status=ssh(host,["qm","status",str(vm)])
 if status is None or "status: running" not in status:return {"status":"guest_off_or_inaccessible"}
 p=qga(vm,host,["docker","ps","-a","--format","{{json .}}"])
 if p["status"]!="ok":return p
 rec=[]
 for row in p["lines"]:
  try:j=json.loads(row)
  except ValueError:continue
  kind=classify(j.get("Names",""))
  live=j.get("State","")=="running" or j.get("Status","").lower().startswith("up ")
  rec.append({"role":kind,"running":live})
 counts={}
 for row in rec:
  k=row["role"]
  d=counts.setdefault(k,{"running":0,"stopped":0})
  d["running" if row["running"] else "stopped"]+=1
 stats=qga(vm,host,["docker","stats","--no-stream","--format","{{json .}}"])
 mem={}
 if stats["status"]=="ok":
  for row in stats["lines"]:
   try:j=json.loads(row)
   except ValueError:continue
   kind=classify(j.get("Name",""))
   n=mb(j.get("MemUsage",""))
   if n is None:continue
   mem[kind]=round(mem.get(kind,0)+n,1)
 return {"status":"ok","container_total":len(rec),
         "services_by_category":counts,
         "container_memory_MiB_by_category":mem,
         "sum_container_docker_memory_MiB":round(sum(mem.values()),1) if mem else None,
         "docker_stats_available":stats["status"]=="ok"}
print("JNS_HA_DOCKER_OVERHEAD_AUDIT")
for vm,host in ROLES.items():
 print("VM"+str(vm)+"="+json.dumps(audit(vm,host),sort_keys=True))
print("JNS_HA_DOCKER_OVERHEAD_AUDIT_END")
