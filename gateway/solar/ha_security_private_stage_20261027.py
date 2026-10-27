#!/usr/bin/env python3
"""Private, inert HA-Security source-file staging on Node B through Node C.
READ from VM906 using QGA. WRITE only to a protected directory on Node B
Proxmox host, not to any guest, HA-Core configuration or GitHub repository.
No restarts, installs, HA service reloads, security ownership changes, or
credential disclosure. No raw file contents, filenames, addresses or hashes in logs.
"""
import base64,hashlib,json,os,shlex,subprocess,sys
SSH=["ssh","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes","-o","ConnectTimeout=6"]
TAG="ha-security-906-20261027-v1"
EXTRACT=r'''
import base64,json,os,pathlib,re
root=pathlib.Path("/config")
paths=[("root",name,root/name) for name in ("configuration.yaml","automations.yaml",
                                            "scripts.yaml","scenes.yaml")]
pkg=root/"packages"
if not pkg.is_dir() or pkg.is_symlink():raise SystemExit(84)
for f in sorted(pkg.glob("*.yaml")):
 if f.is_symlink() or not f.is_file():raise SystemExit(85)
 paths.append(("package",f.name,f))
if not 2<=len([p for p in paths if p[0]=="package"])<=5:raise SystemExit(86)
files=[]
total=0
for category,name,p in paths:
 if not p.is_file():continue
 if p.is_symlink() or not re.fullmatch(r"[a-zA-Z0-9_.-]{1,90}",name):raise SystemExit(87)
 data=p.read_bytes()
 if len(data)>512*1024:raise SystemExit(88)
 total+=len(data)
 if total>2*1024*1024:raise SystemExit(89)
 files.append({"kind":category,"name":name,"content":base64.b64encode(data).decode()})
out={"source_vm":906,"role":"security","files":files}
print("JNS_PRIVATE_TRANSFER="+base64.b64encode(json.dumps(out,separators=(",",":")).encode()).decode())
'''
WRITE=r'''
import base64,hashlib,json,os,pathlib,re,sys,time
root=pathlib.Path("/var/lib/jns-solar/consolidation")
tag="ha-security-906-20261027-v1"
def fail(x):
 print("JNS_SECURITY_STAGE_BLOCKED="+x,flush=True)
 raise SystemExit(77)
if os.geteuid()!=0 or os.uname().nodename.split(".")[0]!="nodeb":fail("wrong_host_or_user")
if not root.parent.is_dir() or root.parent.is_symlink():fail("root_parent_missing")
backup=pathlib.Path("/mnt/pve/NAS/dump/jns-vm906-agent-recovery-20261026-v1/MANIFEST.json")
if not backup.is_file() or backup.is_symlink():fail("security_backup_manifest_unavailable")
try:
 m=json.loads(backup.read_text())
 if m.get("source_node")!="nodea" or not m.get("snapshot_read_only_guest"):fail("wrong_security_backup")
except (OSError,ValueError):fail("bad_backup_manifest")
try:blob=json.loads(sys.stdin.buffer.read(3000000))
except (OSError,ValueError):fail("invalid_private_transfer")
if blob.get("source_vm")!=906 or blob.get("role")!="security":fail("source_identity_mismatch")
entries=blob.get("files",[])
if not isinstance(entries,list) or not 3<=len(entries)<=9:fail("file_count_invalid")
if root.is_symlink():fail("unsafe_staging_root")
root.mkdir(mode=0o700,parents=True,exist_ok=True)
os.chmod(root,0o700)
target=root/tag
if target.exists() or target.is_symlink():fail("stage_exists_never_overwrite")
target.mkdir(mode=0o700)
payload=target/"files"
payload.mkdir(mode=0o700)
manifest=[]
total=0
try:
 for n,item in enumerate(entries,1):
  kind=item.get("kind")
  name=item.get("name")
  if kind not in ("root","package") or not isinstance(name,str) or not re.fullmatch(r"[a-zA-Z0-9_.-]{1,90}",name):fail("invalid_file_metadata")
  try:data=base64.b64decode(item.get("content",""),validate=True)
  except (TypeError,ValueError):fail("invalid_base64")
  if len(data)>512*1024:fail("source_file_too_large")
  total+=len(data)
  if total>2*1024*1024:fail("transfer_too_large")
  file=payload/("source-%02d.yaml"%n)
  with file.open("xb") as dest:dest.write(data)
  file.chmod(0o600)
  manifest.append({"kind":kind,"original_basename":name,"staged_basename":file.name,
      "bytes":len(data),"sha256":hashlib.sha256(data).hexdigest()})
 with (target/"manifest.json").open("x") as dest:
  json.dump({"source_vm":906,"target_vm":905,"stage_inert":True,
      "created_utc":time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime()),
      "files":manifest},dest,indent=2,sort_keys=True)
 (target/"manifest.json").chmod(0o600)
except Exception:
 # Fail closed. Private stage retained for forensic inspection; no HA guest affected.
 raise
print("JNS_SECURITY_PRIVATE_STAGE_OK="+json.dumps({"source_vm":906,"target_vm":905,
 "files":len(manifest),"package_files":sum(i["kind"]=="package" for i in manifest),
 "bytes":total,"staging_location":"nodeb_host_private_only",
 "ha_configuration_modified":False,"source_running_unchanged":True,
 "integrations_activated":False},sort_keys=True),flush=True)
'''
def ssh(host,argv,stdin=None,timeout=45):
 try:return subprocess.run(SSH+[host,shlex.join(argv)],input=stdin,
    text=True,capture_output=True,timeout=timeout)
 except (OSError,subprocess.TimeoutExpired):return None
def main():
 if os.uname().nodename.split(".")[0]!="nodec":
  print("JNS_SECURITY_STAGE_BLOCKED=wrong_runner",flush=True);return 1
 for host,vm,name in (("nodea",906,"ha-security"),("nodeb",905,"ha-s2-general")):
  q=ssh(host,["qm","status",str(vm)])
  c=ssh(host,["qm","config",str(vm)])
  if not q or q.returncode or q.stdout.strip()!="status: running" or not c or c.returncode or "\nname: "+name+"\n" not in "\n"+c.stdout:
   print("JNS_SECURITY_STAGE_BLOCKED=expected_live_vm_unavailable",flush=True);return 1
 code=base64.b64encode(EXTRACT.encode()).decode()
 proc=ssh("nodea",["qm","guest","exec","906","--","docker","exec",
                    "homeassistant","python3","-c",
                    "exec(__import__('base64').b64decode('"+code+"'))"],timeout=50)
 if not proc or proc.returncode:
  print("JNS_SECURITY_STAGE_BLOCKED=source_guest_agent",flush=True);return 1
 try:j=json.loads(proc.stdout)
 except ValueError:
  print("JNS_SECURITY_STAGE_BLOCKED=source_bad_reply",flush=True);return 1
 if not j.get("exited") and j.get("pid"):
  for _ in range(35):
   import time
   time.sleep(.35)
   p=ssh("nodea",["qm","guest","exec-status","906",str(j["pid"])],timeout=20)
   if not p or p.returncode:break
   try:j=json.loads(p.stdout)
   except ValueError:break
 if not j.get("exited") or j.get("exitcode")!=0 or j.get("out-truncated"):
  print("JNS_SECURITY_STAGE_BLOCKED=source_exec_incomplete",flush=True);return 1
 rows=[x.split("=",1)[1] for x in (j.get("out-data") or "").splitlines() if x.startswith("JNS_PRIVATE_TRANSFER=")]
 if len(rows)!=1:
  print("JNS_SECURITY_STAGE_BLOCKED=no_private_payload",flush=True);return 1
 try:private=base64.b64decode(rows[0],validate=True).decode()
 except (ValueError,UnicodeDecodeError):
  print("JNS_SECURITY_STAGE_BLOCKED=bad_private_payload",flush=True);return 1
 writer=base64.b64encode(WRITE.encode()).decode()
 send=ssh("nodeb",["python3","-u","-c",
                   "exec(__import__('base64').b64decode('"+writer+"'))"],
          stdin=private,timeout=95)
 if not send or send.returncode:
  for line in (send.stdout if send else "").splitlines():
   if line.startswith("JNS_SECURITY_STAGE_BLOCKED="):print(line,flush=True)
  print("JNS_SECURITY_STAGE_BLOCKED=destination_did_not_verify",flush=True);return 1
 public=[x for x in send.stdout.splitlines() if x.startswith("JNS_SECURITY_PRIVATE_STAGE_OK=")]
 if len(public)!=1:
  print("JNS_SECURITY_STAGE_BLOCKED=missing_verification",flush=True);return 1
 print(public[0],flush=True)
 print("JNS_NO_HA_RUNTIME_CHANGES=yes",flush=True)
 return 0
if __name__=="__main__":sys.exit(main())
