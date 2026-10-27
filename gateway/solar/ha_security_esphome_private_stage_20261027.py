#!/usr/bin/env python3
"""Securely stage VM906 ESPHome enrolment metadata on Node B host, inert.
No HAOS file writes, API connection, config entry copying or integration
activation. Enrolment data never enters GitHub logs, artifacts, or repository.
"""
import base64,json,os,shlex,subprocess,sys,time
SSH=["ssh","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes","-o","ConnectTimeout=6"]
EXTRACT=r'''
import base64,json,pathlib
path=pathlib.Path("/config/.storage/core.config_entries")
if path.is_symlink() or not path.is_file():raise SystemExit(70)
all_entries=json.loads(path.read_text()).get("data",{}).get("entries",[])
entries=[x for x in all_entries if isinstance(x,dict) and x.get("domain")=="esphome" and not x.get("disabled_by")]
if len(entries)!=1:raise SystemExit(71)
entry=entries[0]
public={"domain":entry.get("domain"),"data":entry.get("data",{}),
        "options":entry.get("options",{}),"title":entry.get("title"),
        "unique_id":entry.get("unique_id"),"version":entry.get("version")}
if not isinstance(public["data"],dict) or not public["data"]:raise SystemExit(72)
print("JNS_PRIVATE_ESPHOME_BLOB="+base64.b64encode(json.dumps(public,separators=(",",":")).encode()).decode())
'''
STAGE=r'''
import hashlib,json,os,pathlib,sys
root=pathlib.Path("/var/lib/jns-solar/consolidation/ha-security-906-20261027-v1")
target=root/"esphome-enrolment-private.json"
def fail(msg):
 print("JNS_ESPHOME_STAGE_BLOCKED="+msg,flush=True)
 raise SystemExit(72)
if os.geteuid()!=0 or os.uname().nodename.split(".")[0]!="nodeb":fail("wrong_host")
manifest=root/"manifest.json"
if not manifest.is_file() or manifest.is_symlink():fail("security_stage_missing")
try:
 m=json.loads(manifest.read_text())
 if m.get("source_vm")!=906 or m.get("target_vm")!=905:fail("stage_identity")
except (OSError,ValueError):fail("bad_stage_manifest")
if target.exists() or target.is_symlink():fail("private_target_already_exists")
try:obj=json.loads(sys.stdin.buffer.read(200000))
except (OSError,ValueError):fail("invalid_payload")
if obj.get("domain")!="esphome" or not isinstance(obj.get("data"),dict) or not obj["data"]:
 fail("wrong_or_empty_integration")
with target.open("x") as f:json.dump(obj,f,sort_keys=True,indent=2);f.write("\n")
target.chmod(0o600)
key_present=any(("key" in k.lower() or "psk" in k.lower() or "noise" in k.lower())
 for k in list(obj.get("data",{}))+list(obj.get("options",{})))
print("JNS_ESPHOME_PRIVATE_STAGE_OK="+json.dumps({"source_vm":906,"target_vm":905,
 "entries":1,"enrolment_data_present":True,"key_like_field_present":key_present,
 "staged_host_private_only":True,"ha_config_entries_modified":False,
 "esphome_client_connected":False},sort_keys=True),flush=True)
'''
def ssh(host,args,stdin=None,timeout=35):
 try:return subprocess.run(SSH+[host,shlex.join(args)],capture_output=True,text=True,
                           input=stdin,timeout=timeout)
 except (OSError,subprocess.TimeoutExpired):return None
def guest(vm,node,code):
 b64=base64.b64encode(code.encode()).decode()
 r=ssh(node,["qm","guest","exec",str(vm),"--","docker","exec","homeassistant",
             "python3","-c","exec(__import__('base64').b64decode('"+b64+"'))"],timeout=40)
 if not r or r.returncode:return None
 try:j=json.loads(r.stdout)
 except ValueError:return None
 for _ in range(45):
  if j.get("exited"):return j
  if not j.get("pid"):break
  time.sleep(.25)
  r=ssh(node,["qm","guest","exec-status",str(vm),str(j["pid"])],timeout=18)
  if not r or r.returncode:break
  try:j=json.loads(r.stdout)
  except ValueError:break
 return None
def main():
 if os.uname().nodename.split(".")[0]!="nodec":
  print("JNS_ESPHOME_STAGE_BLOCKED=wrong_runner");return 1
 source=guest(906,"nodea",EXTRACT)
 if not source or source.get("exitcode")!=0 or source.get("out-truncated"):
  print("JNS_ESPHOME_STAGE_BLOCKED=source_integration_not_readable");return 1
 rows=[x.split("=",1)[1] for x in (source.get("out-data") or "").splitlines() if x.startswith("JNS_PRIVATE_ESPHOME_BLOB=")]
 if len(rows)!=1:
  print("JNS_ESPHOME_STAGE_BLOCKED=no_private_source");return 1
 try:blob=base64.b64decode(rows[0],validate=True).decode()
 except (ValueError,UnicodeDecodeError):
  print("JNS_ESPHOME_STAGE_BLOCKED=decode_failure");return 1
 stage_code=base64.b64encode(STAGE.encode()).decode()
 result=ssh("nodeb",["python3","-u","-c","exec(__import__('base64').b64decode('"+stage_code+"'))"],
            stdin=blob,timeout=35)
 if not result or result.returncode:
  for row in (result.stdout if result else "").splitlines():
   if row.startswith("JNS_ESPHOME_STAGE_BLOCKED="):print(row,flush=True)
  print("JNS_ESPHOME_STAGE_BLOCKED=destination_failure",flush=True);return 1
 rows=[x for x in result.stdout.splitlines() if x.startswith("JNS_ESPHOME_PRIVATE_STAGE_OK=")]
 if len(rows)!=1:
  print("JNS_ESPHOME_STAGE_BLOCKED=no_confirmation");return 1
 print(rows[0],flush=True)
 print("JNS_HA_RUNTIME_UNCHANGED=yes",flush=True)
 return 0
if __name__=="__main__":sys.exit(main())
