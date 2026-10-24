#!/usr/bin/env python3
"""JNS Solar: stage private MQTT and Zigbee2MQTT app-state archives on Node A.

Tar runs inside the unprivileged containers to avoid host user-namespace
snapshot permission errors. No CT/network/DNS/service/onboot changes.
Application snapshots of running services are PRELIMINARY only, and must be
replaced by clean, final service-stopped exports before production cutover.
No raw archive contents, private paths or credentials enter GitHub logs.
"""
import base64,hashlib,json,os,re,shlex,subprocess,sys
SSH=["ssh","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes","-o","ConnectTimeout=6"]
MAX_ARCHIVE=160*1024*1024
SOURCES={
 212:{"hostname":"mqtt-infra-a","target":230,"paths":["etc/mosquitto","var/lib/mosquitto","var/log/mosquitto"]},
 214:{"hostname":"zigbee2mqtt-a","target":231,"paths":["opt/zigbee2mqtt","etc/systemd/system/zigbee2mqtt.service"]}
}
REMOTE=r'''
import datetime,hashlib,json,os,pathlib,subprocess,sys,tarfile,io
ct=int(sys.argv[1])
meta={
 212:("mqtt-infra-a",["etc/mosquitto","var/lib/mosquitto","var/log/mosquitto"]),
 214:("zigbee2mqtt-a",["opt/zigbee2mqtt","etc/systemd/system/zigbee2mqtt.service"])
}
if ct not in meta or os.geteuid()!=0 or os.uname().nodename.split(".")[0]!="nodeb":sys.exit(71)
host,paths=meta[ct]
c=subprocess.run(["pct","config",str(ct)],capture_output=True,text=True,timeout=10)
if c.returncode or "hostname: "+host not in c.stdout:sys.exit(72)
p=subprocess.run(["pct","status",str(ct)],capture_output=True,text=True,timeout=10)
if p.returncode or "status: running" not in p.stdout:sys.exit(73)
data=subprocess.run(["pct","exec",str(ct),"--","/bin/tar","-czf","-","-C","/",*paths],
                   stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=120)
if data.returncode or not data.stdout or len(data.stdout)>167772160:sys.exit(74)
try:
 with tarfile.open(fileobj=io.BytesIO(data.stdout),mode="r:gz") as tf:
  members=tf.getmembers()
  if not members:sys.exit(75)
  found=set(m.name.strip("./") for m in members)
  for wanted in paths:
   if not any(x==wanted or x.startswith(wanted+"/") for x in found):sys.exit(76)
except (OSError,tarfile.TarError):sys.exit(77)
path=pathlib.Path("/var/lib/jns-solar/ct-app-staging")
path.mkdir(parents=True,exist_ok=True,mode=0o700)
os.chmod(path,0o700)
digest=hashlib.sha256(data.stdout).hexdigest()
target=path/("ct-"+str(ct)+"-"+digest[:16]+".tar.gz")
if target.exists():
 if target.is_symlink() or hashlib.sha256(target.read_bytes()).hexdigest()!=digest:sys.exit(78)
else:
 import tempfile
 fd,temp=tempfile.mkstemp(prefix=".incoming-",dir=str(path))
 try:
  with os.fdopen(fd,"wb") as f:
   f.write(data.stdout);f.flush();os.fsync(f.fileno())
  os.chmod(temp,0o600);os.replace(temp,target)
 finally:
  if os.path.exists(temp):os.unlink(temp)
print("JNS_CT_APP_EXPORT="+json.dumps({"ctid":ct,"path":str(target),"bytes":len(data.stdout),"sha256":digest,
      "tar_members":len(members),"source_still_running":True},sort_keys=True))
'''
def fail(code):
 print("JNS_SOLAR_CT_APP_TRANSFER_BLOCKED="+code,flush=True);sys.exit(1)
def run(host,args,timeout=60):
 try:p=subprocess.run(SSH+[host,shlex.join(args)],capture_output=True,text=True,timeout=timeout)
 except (OSError,subprocess.TimeoutExpired):fail("remote_timeout")
 if p.returncode:fail(host+"_rc_"+str(p.returncode))
 return p.stdout
def check_targets():
 check=r'''
set -Eeuo pipefail
test "$(hostname -s)" = nodea
test ! -f /etc/pve/lxc/230.conf
test ! -f /etc/pve/lxc/231.conf
test "$(df -Pk /var/lib/vz/dump | awk 'NR==2{print $4}')" -gt 5242880
install -d -m 0700 /var/lib/jns-solar/ct-app-staging
echo TARGET_OK
'''
 if "TARGET_OK" not in run("nodea",["bash","-c",check],20):fail("nodea_target_check")
def one(ct):
 encoded=base64.b64encode(REMOTE.encode()).decode()
 info=run("nodeb",["python3","-c",
      "import base64,sys;exec(base64.b64decode('"+encoded+"'))",str(ct)],180)
 matches=[x.split("=",1)[1] for x in info.splitlines() if x.startswith("JNS_CT_APP_EXPORT=")]
 if len(matches)!=1:fail("source_metadata_missing")
 try:details=json.loads(matches[0])
 except ValueError:fail("metadata_not_json")
 source=details.get("path","")
 sha=details.get("sha256","")
 size=details.get("bytes",0)
 if (details.get("ctid")!=ct or not re.fullmatch(r"/var/lib/jns-solar/ct-app-staging/ct-"+str(ct)+r"-[a-f0-9]{16}\.tar\.gz",source) or not re.fullmatch(r"[a-f0-9]{64}",sha)
     or not isinstance(size,int) or size<1000 or size>MAX_ARCHIVE):
  fail("source_digest_or_path_invalid")
 destination="/var/lib/jns-solar/ct-app-staging/ct-"+str(ct)+"-"+sha[:16]+".tar.gz"
 partial=destination+".partial"
 preflight="set -eu; test ! -e "+shlex.quote(destination)+"; test ! -e "+shlex.quote(partial)+"; echo READY"
 if "READY" not in run("nodea",["bash","-c",preflight],12):fail("destination_exists_or_locked")
 try:
  src=subprocess.Popen(SSH+["nodeb",shlex.join(["cat",source])],stdout=subprocess.PIPE,stderr=subprocess.DEVNULL)
  dst=subprocess.Popen(SSH+["nodea",shlex.join(["bash","-c","umask 077; cat > "+shlex.quote(partial)])],
                stdin=src.stdout,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
  src.stdout.close();dc=dst.wait(timeout=150);sc=src.wait(timeout=150)
 except (OSError,subprocess.TimeoutExpired):fail("copy_timeout")
 if dc!=0 or sc!=0:fail("copy_transport_error")
 verify="set -Eeuo pipefail; test \"$(stat -c %s "+shlex.quote(partial)+")\" = "+str(size)+"; test \"$(sha256sum "+shlex.quote(partial)+" | awk '{print $1}')\" = "+shlex.quote(sha)+"; chmod 0600 "+shlex.quote(partial)+"; mv -- "+shlex.quote(partial)+" "+shlex.quote(destination)+"; echo VERIFIED"
 if "VERIFIED" not in run("nodea",["bash","-c",verify],35):fail("sha_verification_failed")
 print("CT_"+str(ct)+"_STAGED_NODEA=yes",flush=True)
 print("CT_"+str(ct)+"_ARCHIVE_BYTES="+str(size),flush=True)
 print("CT_"+str(ct)+"_ARCHIVE_SHA256="+sha,flush=True)
 print("CT_"+str(ct)+"_FINAL_CLEAN_EXPORT_REQUIRED=yes",flush=True)
def main():
 print("JNS_SOLAR_CT_APP_STATE_COPY_START",flush=True)
 check_targets()
 for ct in (212,214):one(ct)
 print("NODEA_DESTINATION_CONTAINERS_STARTED=no",flush=True)
 print("PRODUCTION_NODEB_SERVICES_CHANGED=no",flush=True)
 print("JNS_SOLAR_CT_APP_STATE_COPY_COMPLETE",flush=True)
if __name__=="__main__":main()
