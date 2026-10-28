#!/usr/bin/env python3
"""Stage a reviewed, manual-only HA905 app on Node B PRIVATE HOST storage.

This is NOT an HAOS app installation. No /addons, /config, Docker, Supervisor
or Core API changes. No credentials are read, transferred, or logged.
Never overwrite an existing stage, fail closed for unexpected app source.
"""
import base64, hashlib, json, os, pathlib, shlex, subprocess

SSH=["ssh","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes","-o","ConnectTimeout=6"]
SOURCE=pathlib.Path(__file__).parent/"ha905_core_api_bridge_app"
FILES=("config.yaml","Dockerfile","probe.py","README.md")
TARGET="/var/lib/jns-solar/consolidation/ha905-core-api-bridge-probe-20261028-v1"
REMOTE=r'''
import base64,hashlib,json,os,pathlib,shutil,subprocess,sys,tempfile
if os.geteuid()!=0 or os.uname().nodename.split(".")[0]!="nodeb":raise SystemExit(70)
parent=pathlib.Path("/var/lib/jns-solar/consolidation")
dest=parent/"ha905-core-api-bridge-probe-20261028-v1"
if not parent.is_dir() or parent.is_symlink() or dest.exists() or dest.is_symlink():raise SystemExit(71)
p=subprocess.run(["qm","status","905"],capture_output=True,text=True,timeout=10)
if p.returncode or p.stdout.strip()!="status: running":raise SystemExit(72)
j=json.loads(sys.stdin.buffer.read(150000))
expected=("config.yaml","Dockerfile","probe.py","README.md")
if tuple(sorted(j.get("files",{})))!=tuple(sorted(expected)):raise SystemExit(73)
contents={}
for name in expected:
 record=j["files"][name]
 if not isinstance(record,dict):raise SystemExit(74)
 data=base64.b64decode(record["content_b64"],validate=True)
 if len(data)>40000 or hashlib.sha256(data).hexdigest()!=record["sha256"]:raise SystemExit(75)
 contents[name]=data
cfg=contents["config.yaml"].decode()
probe=contents["probe.py"].decode()
required=("boot: manual_only","startup: once","homeassistant_api: true",
          "host_network: false","full_access: false","docker_api: false",
          "stdin: false","ports: {}","hassio_api: false")
if not all(x in cfg for x in required):raise SystemExit(76)
if "method=\"GET\"" not in probe or "method=\"POST\"" in probe or "config_entries/flow" in probe:
 raise SystemExit(77)
tmp=pathlib.Path(tempfile.mkdtemp(prefix=".jns-api-bridge-stage-",dir=parent))
tmp.chmod(0o700)
try:
 for name in expected:
  file=tmp/name
  with file.open("xb") as stream:
   stream.write(contents[name]);stream.flush();os.fsync(stream.fileno())
  file.chmod(0o600)
 manifest={"stage_version":1,"target_vm":905,"host":"nodeb",
           "source": "JNS-Home-Assistant-Deployment",
           "app_installed":False,"app_started":False,"core_api_tested_live":False,
           "no_production_changes":True,"source_file_sha256":{
               name:hashlib.sha256(contents[name]).hexdigest() for name in expected}}
 with (tmp/"manifest.json").open("xb") as f:
  f.write((json.dumps(manifest,sort_keys=True,indent=2)+"\n").encode())
  f.flush();os.fsync(f.fileno())
 (tmp/"manifest.json").chmod(0o600)
 os.rename(tmp,dest)
except BaseException:
 shutil.rmtree(tmp,ignore_errors=True)
 raise
print("JNS_API_BRIDGE_INERT_STAGE="+json.dumps({
  "source_files_staged":len(expected),"manifest_verified":True,
  "target_vm":905,"private_host_directory_created":True,
  "installed_in_haos":False,"admin_api_access_activated":False,
  "vm905_config_modified":False,"vm906_modified":False},sort_keys=True))
'''
def main():
 if os.uname().nodename.split(".")[0]!="nodec":
  print("JNS_API_BRIDGE_PRIVATE_STAGE_BLOCKED=wrong_runner");return 1
 records={}
 for name in FILES:
  path=SOURCE/name
  if not path.is_file() or path.is_symlink():
   print("JNS_API_BRIDGE_PRIVATE_STAGE_BLOCKED=missing_source");return 1
  data=path.read_bytes()
  if not data or len(data)>40000:
   print("JNS_API_BRIDGE_PRIVATE_STAGE_BLOCKED=unexpected_size");return 1
  records[name]={"content_b64":base64.b64encode(data).decode(),
                 "sha256":hashlib.sha256(data).hexdigest()}
 json_body=json.dumps({"files":records},separators=(",",":"))
 code=base64.b64encode(REMOTE.encode()).decode()
 argv=SSH+["nodeb",shlex.join(["python3","-u","-c",
                              "exec(__import__('base64').b64decode('"+code+"'))"])]
 try:p=subprocess.run(argv,input=json_body,text=True,capture_output=True,timeout=55)
 except (OSError,subprocess.TimeoutExpired):
  print("JNS_API_BRIDGE_PRIVATE_STAGE_BLOCKED=host_timeout");return 1
 matches=[x for x in p.stdout.splitlines() if x.startswith("JNS_API_BRIDGE_INERT_STAGE=")]
 if p.returncode or len(matches)!=1:
  print("JNS_API_BRIDGE_PRIVATE_STAGE_BLOCKED=host_validation");return 1
 print(matches[0],flush=True)
 print("JNS_HA_SECURITY_RUNTIME_AND_CLUSTER_UNCHANGED=yes",flush=True)
 return 0
if __name__=="__main__":raise SystemExit(main())
