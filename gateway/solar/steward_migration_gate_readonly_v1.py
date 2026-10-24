#!/usr/bin/env python3
"""JNS Solar read-only Steward migration gate: Node B live API / data, Node C staging.
No secret contents, user data, SSH identities, MAC/IP, service logs,
entity names, configuration exports, or root-only data are printed.
"""
import json, os, pathlib, shlex, subprocess, hashlib, sqlite3

def ssh_nodeb(script,timeout=35):
    cmd=["ssh","-o","BatchMode=yes","-o","ConnectTimeout=6",
         "-o","StrictHostKeyChecking=yes","nodeb",shlex.join(["bash","-c",script])]
    try:r=subprocess.run(cmd,text=True,capture_output=True,timeout=timeout)
    except (OSError,subprocess.TimeoutExpired):return {"status":"trusted_ssh_timeout"}
    if r.returncode:return {"status":"nodeb_audit_unavailable"}
    try:
        marker="JNS_STEWARD_GATE_JSON="
        lines=[x[len(marker):] for x in r.stdout.splitlines() if x.startswith(marker)]
        return json.loads(lines[-1]) if lines else {"status":"missing_summary"}
    except ValueError:return {"status":"unexpected_audit_response"}

READ_NODEB=r'''
set -eu
test "$(hostname -s)" = nodeb || exit 65
python3 - <<'PY_REMOTE'
import json,subprocess,os,pathlib,sqlite3
def run(args,seconds=10):
 try:r=subprocess.run(args,capture_output=True,text=True,timeout=seconds)
 except (OSError,subprocess.TimeoutExpired):return None
 return r
out={"status":"ok"}
s=run(["systemctl","is-active","natural-automation.service"])
out["service_active"]=(s is not None and s.stdout.strip()=="active")
s=run(["systemctl","is-enabled","natural-automation.service"])
out["service_enabled"]=(s is not None and s.stdout.strip()=="enabled")
s=run(["pct","status","221"])
out["ct221"]=(s.stdout.strip().split(":",1)[-1].strip() if s and s.returncode==0 else "not_configured")
root=pathlib.Path("/opt/natural-automation")
out["code_present"]=(root/"natural_automation.py").is_file()
out["knowledge_directory_present"]=(root/"data/knowledge").is_dir()
out["seed_present"]=(root/"data/knowledge/current_chat_seed.md").is_file()
out["site_state_present"]=(root/"data/knowledge/site_state.json").is_file()
out["facts_db_present"]=(root/"data/steward.db").is_file()
if out["facts_db_present"]:
 db=root/"data/steward.db"
 out["facts_db_size_mb"]=round(db.stat().st_size/1048576,2)
 try:
  con=sqlite3.connect("file:"+str(db)+"?mode=ro",uri=True,timeout=3)
  out["facts_db_schema_objects"]=con.execute("select count(*) from sqlite_master").fetchone()[0]
  out["facts_db_readonly_quick_check"]=con.execute("pragma quick_check(1)").fetchone()[0]=="ok"
  con.close()
 except (sqlite3.Error,OSError):
  out["facts_db_readonly_quick_check"]="unavailable"
from urllib.request import urlopen
try:
 with urlopen("http://127.0.0.1:8099/api/status",timeout=4) as r:
  d=json.load(r)
 out["api_healthy"]=d.get("ok") is True
 out["api_apply_enabled"]=d.get("apply_enabled")
 out["api_role"]=(d.get("target") or {}).get("role")
except Exception:
 out["api_healthy"]=False
print("JNS_STEWARD_GATE_JSON="+json.dumps(out,sort_keys=True))
PY_REMOTE
'''

def nodec_local():
    d={"status":"ok"}
    home=pathlib.Path.home()
    stage=home/".local/share/jns-solar/ha900/evidence"
    files=list(stage.glob("vm900-services-*.json")) if stage.is_dir() else []
    d["ha900_manifest_on_nodec_runner"]=len(files)==1
    d["ha900_manifest_private"]=(len(files)==1 and
        (files[0].stat().st_mode & 0o077)==0 and
        (stage.stat().st_mode & 0o077)==0)
    d["ha900_manifest_sha_verified"]=False
    if len(files)==1:
        d["ha900_manifest_sha_verified"]=hashlib.sha256(files[0].read_bytes()).hexdigest()==(
            "77555d0defa1574c7e4d22e63130a42e8958766264b713b2e9f361524a221e82")
    d["root_steward_storage_present"]=pathlib.Path("/var/lib/jns-steward").is_dir()
    d["root_steward_storage_writable"]=os.access("/var/lib/jns-steward",os.W_OK)
    for name in ("jns-management-bridge.service","jns-dns-reservation-importer.service","natural-automation.service","jns-steward.service"):
        try:r=subprocess.run(["systemctl","is-active",name],capture_output=True,text=True,timeout=5)
        except (OSError,subprocess.TimeoutExpired):r=None
        d["service_"+name]=r.stdout.strip()=="active" if r is not None else False
    # Check only if the environment has the authorized importer, never attempt sudo.
    d["privileged_importer_present"]=pathlib.Path("/usr/local/sbin/jns-steward-import-ha900-evidence").exists()
    for ct in (117,130,249):
        p=pathlib.Path("/etc/pve/nodes/nodec/lxc")/(str(ct)+".conf")
        d["nodec_ct"+str(ct)+"_definition_visible"]=p.exists()
    return d
print("JNS_SOLAR_STEWARD_MIGRATION_GATE_READONLY")
print("NODEB_LIVE="+json.dumps(ssh_nodeb(READ_NODEB),sort_keys=True))
print("NODEC_STAGING="+json.dumps(nodec_local(),sort_keys=True))
print("JNS_SOLAR_STEWARD_MIGRATION_GATE_COMPLETE")
