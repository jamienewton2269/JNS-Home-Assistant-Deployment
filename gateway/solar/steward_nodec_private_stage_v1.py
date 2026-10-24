#!/usr/bin/env python3
"""Privately stage a complete, inert Natural Automation v1 candidate on Node C.
Copies ONLY approved Node B service code + SQLite-consistent knowledge snapshot;
does NOT install, run, reload, stop, modify config, or enable application.
No private content reaches CI logs, GitHub files, or user transcript.
"""
import base64,hashlib,io,json,os,pathlib,shlex,subprocess,sys,tempfile,zipfile
REMOTE=r'''
import hashlib,io,os,pathlib,sqlite3,subprocess,sys,zipfile
if os.geteuid()!=0 or os.uname().nodename.split(".")[0]!="nodeb":
 sys.exit(71)
app=pathlib.Path("/opt/natural-automation")
files=[]
for rbase,rel,pattern in [(app,"steward","*.py"),(app,"tools","*.py"),
                           (app,"data/knowledge","*")]:
 path=rbase/rel
 if not path.is_dir():sys.exit(72)
 for p in sorted(path.rglob(pattern)):
  if p.is_symlink():sys.exit(73)
  if p.is_file():
   if p.stat().st_size>2097152:sys.exit(74)
   files.append((p,"application/"+p.relative_to(app).as_posix()))
for rel in ("natural_automation.py","VERSION"):
 p=app/rel
 if not p.is_file() or p.is_symlink():sys.exit(75)
 files.append((p,"application/"+rel))
root=pathlib.Path("/opt/real-progress")
if root.is_dir():
 for p in sorted(root.rglob("*.py")):
  if p.is_symlink():sys.exit(76)
  if p.is_file():
   if p.stat().st_size>2097152:sys.exit(77)
   files.append((p,"real-progress/"+p.relative_to(root).as_posix()))
unit=pathlib.Path("/etc/systemd/system/natural-automation.service")
if not unit.is_file() or unit.is_symlink():sys.exit(78)
files.append((unit,"systemd/natural-automation.service"))
if len(files)>150:sys.exit(79)
db=app/"data/steward.db"
if not db.is_file() or db.is_symlink():sys.exit(80)
try:
 source=sqlite3.connect("file:"+str(db)+"?mode=ro",uri=True,timeout=8)
 memory=sqlite3.connect(":memory:")
 source.backup(memory,pages=50,sleep=0.1)
 if memory.execute("pragma quick_check(1)").fetchone()[0]!="ok":sys.exit(81)
 snapshot=memory.serialize()
 source.close();memory.close()
except (sqlite3.Error,AttributeError):sys.exit(82)
if len(snapshot)>8*1024*1024:sys.exit(83)
b=io.BytesIO()
with zipfile.ZipFile(b,"w",compression=zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
 for p,target in files:
  data=p.read_bytes()
  archive.writestr(target,data)
 archive.writestr("application/data/steward.db",snapshot)
payload=b.getvalue()
if len(payload)>8*1024*1024:sys.exit(84)
sys.stdout.buffer.write(payload)
'''
def fail(message):
 print("JNS_STEWARD_NODEC_PRIVATE_STAGE_BLOCKED="+message)
 sys.exit(1)
def main():
 if os.uname().nodename.split(".")[0]!="nodec" or os.geteuid()==0:fail("unexpected_runner")
 cmd=["ssh","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes","-o","ConnectTimeout=6","nodeb",
       shlex.join(["python3","-c","exec(__import__('base64').b64decode('"+base64.b64encode(REMOTE.encode()).decode()+"'))"])]
 try:p=subprocess.run(cmd,capture_output=True,timeout=45)
 except (OSError,subprocess.TimeoutExpired):fail("trusted_transport_timeout")
 if p.returncode:
  print("JNS_STEWARD_NODEC_PRIVATE_STAGE_REMOTE_EXIT="+str(p.returncode))
  fail("source_export_failed")
 data=p.stdout
 if not data or len(data)>8*1024*1024:fail("invalid_archive_size")
 try:
  with zipfile.ZipFile(io.BytesIO(data)) as archive:
   members=archive.infolist()
   names=[z.filename for z in members]
   if len(names)!=len(set(names)) or len(names)>160:fail("duplicate_or_excessive_entries")
   if "application/data/steward.db" not in names or "application/natural_automation.py" not in names:fail("required_source_missing")
   total=0
   for z in members:
    n=pathlib.PurePosixPath(z.filename)
    if z.is_dir() or n.is_absolute() or ".." in n.parts:fail("unsafe_archive_path")
    if not z.filename.startswith(("application/","real-progress/","systemd/")):fail("untrusted_archive_path")
    if z.file_size>8*1024*1024:fail("entry_too_large")
    total+=z.file_size
   if total>16*1024*1024:fail("too_large_uncompressed")
   db=archive.read("application/data/steward.db")
   if not db.startswith(b"SQLite format 3\x00"):fail("invalid_database_snapshot")
 except (zipfile.BadZipFile,RuntimeError):fail("invalid_zip")
 sha=hashlib.sha256(data).hexdigest()
 home=pathlib.Path.home()
 cur=home
 for name in (".local","share","jns-solar","steward","migration-stage"):
  cur=cur/name
  if cur.exists():
   if cur.is_symlink() or not cur.is_dir() or cur.stat().st_uid!=os.geteuid():fail("unsafe_private_path")
   if name in ("jns-solar","steward","migration-stage") and cur.stat().st_mode & 0o077:fail("unsafe_permissions")
  else:cur.mkdir(mode=0o700)
 dest=cur/("nodeb-steward-staged-"+sha[:16]+".zip")
 if dest.exists():
  if dest.is_symlink() or hashlib.sha256(dest.read_bytes()).hexdigest()!=sha:fail("existing_archive_mismatch")
 else:
  fd,tmp=tempfile.mkstemp(dir=str(cur),prefix=".incoming-")
  try:
   with os.fdopen(fd,"wb") as f:
    f.write(data);f.flush();os.fsync(f.fileno())
   os.chmod(tmp,0o600);os.replace(tmp,dest)
  finally:
   if os.path.exists(tmp):os.unlink(tmp)
 os.chmod(dest,0o600)
 print("JNS_STEWARD_NODEC_CANDIDATE_STAGED_OK")
 print("ARCHIVE_SHA256="+sha)
 print("ARCHIVE_BYTES="+str(len(data)))
 print("FILE_COUNT="+str(len(members)))
 print("SQLITE_SNAPSHOT_VALID_HEADER=yes")
 print("PRIVATE_STAGING_ROOT_ONLY=no_runner_owned_yes")
 print("SOURCE_NODEB_SERVICE_UNCHANGED=yes")
 print("NODEC_SERVICE_STARTED=no")
 print("APPLY_ENABLED=no")
 print("PROMOTION_READY=no")
if __name__=="__main__":main()
