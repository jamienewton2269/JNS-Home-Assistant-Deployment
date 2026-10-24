#!/usr/bin/env python3
"""JNS doorbell mobile-camera architecture read-only audit: VM902 & VM905."""
import base64, json, shlex, subprocess, time
SOURCE=r'''
from pathlib import Path
import json,re,os,subprocess
P=Path("/config")
def reg(fn,key):
 try: return json.loads((P/".storage"/fn).read_text())["data"].get(key,[])
 except Exception:return []
entries=reg("core.config_entries","entries")
print("INTEGRATIONS",json.dumps([{"domain":e.get("domain"),"title":e.get("title"),"disabled":e.get("disabled_by"),"source":e.get("source")} for e in entries if e.get("domain") in ("mqtt","mobile_app","camera","onvif","tapo","go2rtc","webrtc","generic","ffmpeg","stream","media_player","browser_mod","hacs") or re.search("camera|tapo|door|front",str(e.get("title","")),re.I)][:65],default=str)[:14000],flush=True)
entities=reg("core.entity_registry","entities")
picked=[]
for e in entities:
 s=" ".join(str(e.get(k,"")) for k in ("entity_id","name","original_name","platform"))
 if re.search("camera\.|mobile_app|front.?door|doorbell|tapo|c210|go2rtc|webrtc|speaker|microphone|two.?way|notify",s,re.I):
  picked.append({"entity":e.get("entity_id"),"name":e.get("name") or e.get("original_name"),"platform":e.get("platform"),"disabled":e.get("disabled_by"),"device":e.get("device_id")})
print("RELEVANT_ENTITIES",json.dumps(picked[:130],default=str)[:22000],flush=True)
devices=reg("core.device_registry","devices")
picked_devices=[]
for d in devices:
 if re.search("mobile_app|tapo|camera|front door|doorbell|c210",str(d.get("name_by_user"))+" "+str(d.get("name"))+" "+str(d.get("model"))+" "+str(d.get("manufacturer")),re.I) or d.get("config_entries") and any(x.get("domain")=="mobile_app" and x.get("entry_id") in d["config_entries"] for x in entries):
  picked_devices.append({"name":d.get("name_by_user") or d.get("name"),"model":d.get("model"),"manufacturer":d.get("manufacturer"),"disabled":d.get("disabled_by")})
print("RELEVANT_DEVICES",json.dumps(picked_devices[:80],default=str)[:11000],flush=True)
pkg=P/"packages"
print("PACKAGE_FILENAMES",[x.name for x in sorted(pkg.glob("*.yaml"))] if pkg.exists() else [],flush=True)
try:
 import yaml
 for path in [P/"automations.yaml",*sorted(pkg.glob("*.yaml"))]:
  if not path.exists():continue
  data=yaml.safe_load(path.read_text())
  rows=data if isinstance(data,list) else data.get("automation",[]) if isinstance(data,dict) else []
  if isinstance(rows,dict):rows=list(rows.values())
  for a in rows if isinstance(rows,list) else []:
   if not isinstance(a,dict):continue
   alias=str(a.get("alias",""))
   if re.search("door.?bell|camera|c210|front door|notification|welcome home",alias,re.I):
    triggers=a.get("triggers",a.get("trigger",[]))
    actions=a.get("actions",a.get("action",[]))
    def summarize(v,depth=0):
     if depth>8:return "[depth limit]"
     if isinstance(v,list):return [summarize(x,depth+1) for x in v[:25]]
     if isinstance(v,dict):
      safe={"trigger","triggers","entity_id","topic","type","domain","service","action","target","data","conditions","condition","state","sequence","choose","platform","to","from","delay","message","title","url","tag","clickAction","event_type","payload","enabled","mode"}
      return {k:summarize(z,depth+1) for k,z in v.items() if k in safe and not re.search("token|password|key|auth|secret|user",k,re.I)}
     return str(v)[:280]
    print("AUTOMATION",json.dumps({"file":path.name,"id":a.get("id"),"alias":alias,"triggers":summarize(triggers),"actions":summarize(actions)},default=str)[:5500],flush=True)
except Exception as e:print("AUTOMATION_PARSE_ERROR",type(e).__name__,str(e)[:150],flush=True)
addon_path=Path("/mnt/data/supervisor/addons/data")
# HA Core docker container has no Supervisor addon volume; do not probe secrets.
print("JNS_DOORBELL_ARCHITECTURE_READONLY_COMPLETE",flush=True)
'''
def ssh(host,args,timeout=25):
 p=subprocess.run(["ssh","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes",host,shlex.join(args)],
      capture_output=True,text=True,timeout=timeout)
 if p.returncode: raise RuntimeError("SSH_EXIT_"+str(p.returncode)+" "+p.stderr[-300:])
 return json.loads(p.stdout)
def guest(host,vm,args,limit=45):
 d=ssh(host,["qm","guest","exec",str(vm),"--",*args],timeout=limit+15)
 pid=d.get("pid");start=time.monotonic()
 while not d.get("exited"):
  if pid is None or time.monotonic()-start>limit:raise RuntimeError("QGA_TIMEOUT_OR_NO_PID")
  time.sleep(.8)
  d=ssh(host,["qm","guest","exec-status",str(vm),str(pid)],timeout=20)
 return d.get("exitcode"),d.get("out-data",""),d.get("err-data","")
code="exec(__import__('base64').b64decode("+repr(base64.b64encode(SOURCE.encode()).decode())+"))"
for name,host,vm in [("HA_PRIMARY","nodea",902),("HA_GENERAL","nodeb",905)]:
 print("===NODE",name,vm,"===",flush=True)
 try:
  rc,out,err=guest(host,vm,["docker","exec","homeassistant","python3","-c",code],limit=60)
  print("GUEST_EXIT",rc,flush=True)
  print(out[:50000],flush=True)
  print("GUEST_ERROR",err[-600:],flush=True)
 except Exception as e:print("NODE_READ_ERROR",name,type(e).__name__,str(e)[:230],flush=True)
print("=== PROXMOX SUPERVISOR ADDON LISTS ===",flush=True)
for name,host,vm in [("HA_PRIMARY","nodea",902),("HA_GENERAL","nodeb",905)]:
 try:
  rc,out,err=guest(host,vm,["ha","apps","list"],limit=30)
  print("ADDON_METADATA",name,"rc",rc,"items",out[-13000:],"err",err[-250:],flush=True)
 except Exception as e:print("ADDON_READ_ERROR",name,type(e).__name__,str(e)[:150],flush=True)
print("DOORBELL_MOBILE_CAMERA_AUDIT_DONE",flush=True)
