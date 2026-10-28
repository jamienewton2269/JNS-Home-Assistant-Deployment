#!/usr/bin/env python3
"""Inspect only temporary local app and sanitized Supervisor errors read-only."""
import base64,json,os,shlex,subprocess
SSH=["ssh","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes","-o","ConnectTimeout=6"]
HOST=r'''
import json,os,pathlib,re,subprocess,time
if os.geteuid()!=0 or os.uname().nodename.split(".")[0]!="nodeb":raise SystemExit(70)
SLUG="local_jns_ha905_core_api_probe"
PATH="/mnt/data/supervisor/apps/local/jns_ha905_core_api_probe"
def qga(argv,timeout=45):
 try:r=subprocess.run(["qm","guest","exec","905","--",*argv],text=True,capture_output=True,timeout=25)
 except (OSError,subprocess.TimeoutExpired):return None
 if r.returncode:return None
 try:j=json.loads(r.stdout)
 except ValueError:return None
 deadline=time.monotonic()+timeout
 while not j.get("exited") and time.monotonic()<deadline:
  if not j.get("pid"):return None
  time.sleep(.4)
  r=subprocess.run(["qm","guest","exec-status","905",str(j["pid"])],text=True,capture_output=True,timeout=22)
  if r.returncode:return None
  try:j=json.loads(r.stdout)
  except ValueError:return None
 return j if j.get("exited") else None
def run(*argv,timeout=45):
 j=qga(list(argv),timeout)
 return j.get("exitcode") if j else None,str(j.get("out-data","")) if j else ""
rc,raw=run("ha","apps","info",SLUG,"--raw-json")
o={"info_cli_exit":rc}
try:
 obj=json.loads(raw)
 data=obj.get("data",obj) if isinstance(obj,dict) else {}
 o["info_result"]=obj.get("result") if isinstance(obj,dict) else "nondict"
 o["installed"]=data.get("installed") if isinstance(data,dict) else None
 o["available"]=data.get("available") if isinstance(data,dict) else None
 o["state"]=data.get("state") if isinstance(data,dict) else None
 o["repo_local"]=(data.get("repository")=="local") if isinstance(data,dict) else None
except (ValueError,TypeError):o["info_json_invalid"]=True
rc,raw=run("ha","apps","install","--help")
o["install_cli_help_exit"]=rc
o["help_mentions_no_progress"]="--no-progress" in raw
rc,raw=run("ha","apps","uninstall","--help")
o["uninstall_cli_help_exit"]=rc
p=qga(["sh","-c",
 "for x in /mnt/data/supervisor/apps/local/jns_ha905_core_api_probe"
 " /mnt/data/supervisor/apps/local/jns_ha905_core_api_probe/Dockerfile"
 " /mnt/data/supervisor/apps/local/jns_ha905_core_api_probe/config.yaml;"
 " do if test -e \"$x\"; then echo present; else echo absent; fi; done"])
if p:
 o["source_presence"]=str(p.get("out-data","")).splitlines()
rc,raw=run("ha","supervisor","logs","--lines","200",timeout=45)
lines=raw.splitlines()
selected=[x.lower() for x in lines if SLUG in x or "dockerfile is missing" in x.lower()]
o["supervisor_references_app"]=len(selected)
o["supervisor_app_error_excerpt"]=[
 re.sub(r"(?i)(bearer\\s+|token[=:]\\s*|password[=:]\\s*)\\S+",
        "[REDACTED]",x.split(SLUG,1)[-1]).strip()[:230]
 for x in selected[-8:] if ("error" in x or "fail" in x or "invalid" in x)]
o["error_classes"]={
 "dockerfile_missing":any("dockerfile" in x and "missing" in x for x in selected),
 "build_failed":any("build" in x and ("error" in x or "failed" in x) for x in selected),
 "image_pull_failed":any("pull" in x and ("error" in x or "failed" in x) for x in selected),
 "invalid_config":any("invalid" in x or "validation" in x for x in selected),
 "repository_missing":any("repository" in x and ("not" in x or "missing" in x) for x in selected),
 "not_found":any("not found" in x or "notfound" in x for x in selected)
}
# Store response may have an error message; classify without exposing it.
rc,raw=run("ha","store","info",SLUG,"--raw-json")
o["store_info_cli_exit"]=rc
try:
 obj=json.loads(raw)
 o["store_info_result"]=obj.get("result") if isinstance(obj,dict) else None
 data=obj.get("data",{}) if isinstance(obj,dict) else {}
 o["store_available"]=data.get("available") if isinstance(data,dict) else None
except (ValueError,TypeError):pass
print("JNS_HA905_API_INSTALL_FAILURE_READONLY="+json.dumps(o,sort_keys=True))
'''
def main():
 if os.uname().nodename.split(".")[0]!="nodec":return 1
 code=base64.b64encode(HOST.encode()).decode()
 try:p=subprocess.run(SSH+["nodeb",shlex.join(["python3","-c",
       "exec(__import__('base64').b64decode('"+code+"'))"])],
       text=True,capture_output=True,timeout=200)
 except (OSError,subprocess.TimeoutExpired):
  print("JNS_HA905_API_DIAG_BLOCKED=transport");return 1
 rows=[s for s in p.stdout.splitlines() if s.startswith("JNS_HA905_API_INSTALL_FAILURE_READONLY=")]
 if p.returncode or len(rows)!=1:
  print("JNS_HA905_API_DIAG_BLOCKED=host_query");return 1
 print(rows[0]);print("JNS_HA905_API_DIAG_NO_GUEST_CHANGES=yes");return 0
if __name__=="__main__":raise SystemExit(main())
