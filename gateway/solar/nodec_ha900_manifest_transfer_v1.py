#!/usr/bin/env python3
"""Transfer pinned HA900 service manifest to private Node C staging.
No logs of manifest content, credentials, network addresses or private paths.
Read-only on Node A, writes only in Node C runner's restricted local staging.
NO cleanup, power operations, HA or VM changes.
"""
import hashlib,json,os,pathlib,shlex,subprocess,sys,tempfile,datetime

EXPECTED_SHA256="77555d0defa1574c7e4d22e63130a42e8958766264b713b2e9f361524a221e82"
MAX_BYTES=512*1024
SOURCE_CODE=r'''
import glob,hashlib,json,os,pathlib,sys
root=pathlib.Path("/var/lib/jns-solar/ha900/evidence")
if os.geteuid()!=0 or os.uname().nodename.split(".")[0]!="nodea":
    sys.exit(70)
files=sorted(root.glob("vm900-services-*.json"))
if not files:sys.exit(71)
matched=[]
for file in files:
    if file.is_symlink() or file.stat().st_size > 524288:continue
    data=file.read_bytes()
    if hashlib.sha256(data).hexdigest()=="77555d0defa1574c7e4d22e63130a42e8958766264b713b2e9f361524a221e82":
        matched.append(data)
if len(matched)!=1:sys.exit(72)
sys.stdout.buffer.write(matched[0])
'''
def fail(code):
    print("JNS_SOLAR_HA900_EVIDENCE_TRANSFER_BLOCKED="+code)
    sys.exit(1)
def main():
    if os.uname().nodename.split(".")[0]!="nodec":fail("wrong_host")
    if os.geteuid()==0:fail("expected_unprivileged_runner")
    remote=["ssh","-o","BatchMode=yes","-o","ConnectTimeout=6",
            "-o","StrictHostKeyChecking=yes","nodea",
            shlex.join(["python3","-c",SOURCE_CODE])]
    try:p=subprocess.run(remote,capture_output=True,timeout=30)
    except (OSError,subprocess.TimeoutExpired):fail("ssh_timeout")
    if p.returncode:fail("trusted_source_unavailable_or_unexpected_evidence")
    blob=p.stdout
    if not (0<len(blob)<=MAX_BYTES):fail("evidence_size_invalid")
    if hashlib.sha256(blob).hexdigest()!=EXPECTED_SHA256:fail("checksum_mismatch")
    try:manifest=json.loads(blob)
    except (ValueError,UnicodeError):fail("invalid_json")
    if manifest.get("schema")!="jns.solar.vm900.services.v1" or manifest.get("vmid")!=900:
        fail("manifest_schema_mismatch")
    if manifest.get("container_count")!=21 or manifest.get("running_count")!=19:
        fail("unexpected_service_count")
    if not manifest.get("cleanup_authorised") is False:fail("unsafe_cleanup_state")
    home=pathlib.Path.home()
    if home.is_symlink():fail("runner_home_symlink")
    target=home/".local"/"share"/"jns-solar"/"ha900"/"evidence"
    # Ensure every child is owned by runner, private and non-symlinked.
    node=home
    for child in (".local","share","jns-solar","ha900","evidence"):
        node=node/child
        if node.exists():
            if node.is_symlink() or not node.is_dir() or node.stat().st_uid!=os.geteuid():
                fail("unsafe_staging_directory")
            if child in ("jns-solar","ha900","evidence") and node.stat().st_mode & 0o077:
                fail("private_staging_directory_too_open")
        else:node.mkdir(mode=0o700)
    target_name="vm900-services-"+EXPECTED_SHA256[:16]+".json"
    dest=target/target_name
    if dest.exists():
        if dest.is_symlink() or hashlib.sha256(dest.read_bytes()).hexdigest()!=EXPECTED_SHA256:
            fail("existing_file_mismatch")
        if dest.stat().st_mode & 0o077:fail("evidence_permissions_too_open")
        print("JNS_SOLAR_HA900_EVIDENCE_ALREADY_STAGED_VERIFIED")
    else:
        fd,temp=tempfile.mkstemp(prefix=".incoming-",dir=str(target))
        try:
            with os.fdopen(fd,"wb") as f:
                f.write(blob);f.flush();os.fsync(f.fileno())
            os.chmod(temp,0o600)
            os.replace(temp,dest)
        finally:
            if os.path.exists(temp):os.unlink(temp)
        print("JNS_SOLAR_HA900_EVIDENCE_STAGED_ON_NODEC")
    print("EVIDENCE_SHA256="+EXPECTED_SHA256)
    print("EVIDENCE_CONTAINER_COUNT=21")
    print("EVIDENCE_RUNNING_CONTAINERS=19")
    print("EVIDENCE_STORED_IN_PRIVATE_RUNNER_AREA=yes")
    print("EVIDENCE_IMPORTED_INTO_ROOT_OWNED_STEWARD=no")
    print("FULL_BACKUP_VERIFIED=no")
    print("CLEANUP_AUTHORISED=no")
if __name__=="__main__":main()
