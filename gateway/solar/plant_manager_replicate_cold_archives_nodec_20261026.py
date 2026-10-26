#!/usr/bin/env python3
"""Copy verified VM903 offline archives from Node B NAS to Node C NFS backup share.

Existing Node C runner access only; neither guest nor Proxmox configuration
is changed. Copy both archives and manifest, verify byte length and SHA-256.
Never publish archive data or HA credentials to GitHub.
"""
import hashlib,json,os,re,shlex,subprocess,sys,uuid
from pathlib import Path
SOURCE=Path("/mnt/pve/NAS/dump")
DEST=Path("/mnt/pve/nfs-ct/dump")
MANIFEST="jns-plant-manager-vm903-cold-20261026.json"
SSH=["ssh","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes",
     "-o","ConnectTimeout=7","nodeb"]
def fail(code):
    print("JNS_PLANT_NODEC_REPLICATION_BLOCKED="+code,flush=True);raise SystemExit(1)
def ssh_output(argv,timeout=25):
    p=subprocess.run(SSH+[shlex.join(argv)],capture_output=True,timeout=timeout)
    return p.stdout if p.returncode==0 else None
def sha_of(p):
    h=hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda:f.read(4*1024*1024),b""):
            h.update(chunk)
    return h.hexdigest()
def main():
    p=subprocess.run(["hostname","-s"],capture_output=True,text=True)
    if p.returncode or p.stdout.strip()!="nodec":fail("wrong_runner")
    mounted=subprocess.run(["findmnt","-n","-M","/mnt/pve/nfs-ct"],capture_output=True)
    if mounted.returncode:fail("nfs_backup_not_mounted")
    if not DEST.parent.is_dir() or DEST.parent.is_symlink():fail("target_mount_missing")
    if not os.access(DEST.parent,os.W_OK):fail("target_mount_not_writable")
    if DEST.is_symlink():fail("target_dir_symlink")
    if not DEST.exists():
        DEST.mkdir(mode=0o700)
    if not DEST.is_dir() or not os.access(DEST,os.W_OK):fail("target_directory_not_writable")
    raw=ssh_output(["cat",str(SOURCE/MANIFEST)])
    if not raw or len(raw)>10000:fail("source_manifest_unavailable")
    try:j=json.loads(raw)
    except ValueError:fail("manifest_malformed")
    if j.get("vmid")!=903 or j.get("source_status")!="stopped" or j.get("onboot")!=0:
        fail("manifest_mismatch")
    backups=j.get("backups",[])
    if len(backups)!=2 or {x.get("stage") for x in backups}!={"SAFETY_LIVE","COLD"}:
        fail("backup_inventory_unexpected")
    verified=[]
    for b in backups:
        name=b.get("file","")
        expected_hash=b.get("sha256","")
        bytes_expected=b.get("bytes",0)
        if not re.fullmatch(r"vzdump-qemu-903-\d{4}_\d{2}_\d{2}-\d{2}_\d{2}_\d{2}\.vma\.zst",name):
            fail("source_filename_unexpected")
        if not re.fullmatch(r"[0-9a-f]{64}",expected_hash):fail("bad_expected_hash")
        if not isinstance(bytes_expected,int) or not 100*1024**2<bytes_expected<40*1024**3:
            fail("unexpected_archive_size")
        target=DEST/name
        if target.is_symlink():fail("archive_target_symlink")
        if target.exists():
            if target.stat().st_size!=bytes_expected or sha_of(target)!=expected_hash:
                fail("different_preexisting_target")
        else:
            stage=DEST/(name+".partial-"+uuid.uuid4().hex[:12])
            if stage.exists():fail("stage_path_collision")
            cmd=SSH+[shlex.join(["cat",str(SOURCE/name)])]
            p=subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL)
            total=0;hashobj=hashlib.sha256()
            try:
                with stage.open("xb") as f:
                    while True:
                        chunk=p.stdout.read(4*1024*1024)
                        if not chunk:break
                        total+=len(chunk)
                        if total>bytes_expected:fail("unexpected_source_growth")
                        hashobj.update(chunk);f.write(chunk)
                    f.flush();os.fsync(f.fileno())
                code=p.wait(timeout=60)
                if code or total!=bytes_expected or hashobj.hexdigest()!=expected_hash:
                    fail("source_copy_digest_mismatch")
                os.chmod(stage,0o600)
                stage.rename(target)
            finally:
                if p.poll() is None:p.kill()
                if stage.exists():stage.unlink()
        verified.append({"name":name,"bytes":bytes_expected,"sha256":expected_hash,"stage":b["stage"]})
        print("JNS_PLANT_NODEC_REPLICA_VERIFIED="+json.dumps({"stage":b["stage"],"bytes":bytes_expected,"sha256_match":True}),flush=True)
    target=DEST/MANIFEST
    if target.is_symlink():fail("manifest_target_symlink")
    if target.exists():
        if target.read_bytes()!=raw:fail("different_preexisting_manifest")
    else:
        with target.open("xb") as f:f.write(raw);f.flush();os.fsync(f.fileno())
        os.chmod(target,0o600)
    print("JNS_PLANT_NODEC_REPLICATION_COMPLETE="+json.dumps({
        "backup_copies":len(verified),"all_sha256_verified":True,
        "source_guest_stopped":True,"nodec_nfs_archive_present":True,
        "nodec_local_vm_created":False,"recorder_modified":False,
        "restore_tested":False},sort_keys=True),flush=True)
if __name__=="__main__":main()
