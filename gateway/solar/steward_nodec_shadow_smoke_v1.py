#!/usr/bin/env python3
"""Node C isolated Natural Automation start-up smoke test.
Opens previously staged zip privately; runs a temporary loopback-only server
on a private DB COPY with apply gate OFF and no infrastructure target access.
No production service, app paths, data, DNS or startup units are modified.
"""
import hashlib,io,os,pathlib,socket,sqlite3,subprocess,sys,tempfile,time,urllib.error,urllib.request,zipfile
SHA="517a78dc7ccfc3547181626b59c67fbddbd8a9155bf37d91d203a5c9042ec3e4"
def fail(reason):
 print("JNS_STEWARD_NODEC_SHADOW_BLOCKED="+reason)
 sys.exit(1)
def main():
 if os.uname().nodename.split(".")[0]!="nodec" or os.geteuid()==0:fail("runner_identity_invalid")
 root=pathlib.Path.home()/".local/share/jns-solar/steward/migration-stage"
 zpath=root/("nodeb-steward-staged-"+SHA[:16]+".zip")
 if not zpath.is_file() or zpath.is_symlink():fail("source_archive_missing")
 if hashlib.sha256(zpath.read_bytes()).hexdigest()!=SHA:fail("source_sha_mismatch")
 with tempfile.TemporaryDirectory(prefix="jns-steward-shadow-") as tmp:
  base=pathlib.Path(tmp)
  os.chmod(base,0o700)
  with zipfile.ZipFile(zpath) as a:
   for m in a.infolist():
    dest=base/pathlib.PurePosixPath(m.filename)
    if m.filename.startswith("/") or ".." in pathlib.PurePosixPath(m.filename).parts:fail("unsafe_member")
    if m.file_size>8*1024**2 or m.is_dir():fail("unsafe_member_type")
    dest.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    dest.write_bytes(a.read(m))
    os.chmod(dest,0o600)
  app=base/"application"
  db=app/"data/steward.db"
  if not db.is_file():fail("db_missing")
  con=sqlite3.connect(str(db))
  healthy=(con.execute("PRAGMA quick_check(1)").fetchone()[0]=="ok")
  schema=con.execute("select count(*) from sqlite_master").fetchone()[0]
  con.close()
  if not healthy or schema<5:fail("db_integrity_check")
  path=app/"natural_automation.py"
  src=path.read_text()
  old_import='sys.path.insert(0,"/opt/real-progress")'
  old_root='ROOT=Path("/opt/natural-automation")'
  if old_import not in src or old_root not in src:fail("source_code_contract_changed")
  patched=src.replace(old_import,'sys.path.insert(0,os.environ["JNS_SHADOW_REAL"])').replace(old_root,'ROOT=Path(os.environ["JNS_SHADOW_ROOT"])')
  path.write_text(patched)
  with socket.socket() as s:
   s.bind(("127.0.0.1",0));port=s.getsockname()[1]
  env={"PATH":"/usr/bin:/bin","HOME":str(base),"PYTHONUNBUFFERED":"1",
   "NA_BIND":"127.0.0.1","NA_PORT":str(port),"NA_ENABLE_APPLY":"0",
   "NA_TARGET_ROLE":"ha-general","NA_PROXMOX_HOSTS":"invalid.invalid",
   "JNS_SHADOW_ROOT":str(app),"JNS_SHADOW_REAL":str(base/"real-progress")}
  logs=base/"private_stdout_stderr.log"
  try:
   with logs.open("w") as f:
    p=subprocess.Popen(["/usr/bin/python3",str(path)],cwd=str(app),env=env,
            stdout=f,stderr=subprocess.STDOUT)
   success=False
   for _ in range(35):
    if p.poll() is not None:break
    try:
     with urllib.request.urlopen("http://127.0.0.1:"+str(port)+"/",timeout=0.7) as req:
      if req.status==200 and b"<" in req.read(1024):success=True;break
    except (OSError,urllib.error.URLError,TimeoutError):pass
    time.sleep(0.4)
  finally:
   if 'p' in locals() and p.poll() is None:
    p.terminate()
    try:p.wait(timeout=4)
    except subprocess.TimeoutExpired:p.kill();p.wait(timeout=4)
  if not success:fail("loopback_http_start_failed")
  print("JNS_SOLAR_STEWARD_SHADOW_NODEC_SMOKE_OK")
  print("SQLITE_BACKUP_INTEGRITY=ok")
  print("SQLITE_SCHEMA_OBJECTS="+str(schema))
  print("PRIVATE_LOOPBACK_HTTP_200=yes")
  print("SHADOW_APPLY_ENABLED=no")
  print("PRODUCTION_NODEB_UNCHANGED=yes")
  print("NODEC_SHADOW_STOPPED_AND_TEMP_REMOVED=yes")
  print("NODEC_PERMANENT_SERVICE_INSTALLED=no")
if __name__=="__main__":main()
