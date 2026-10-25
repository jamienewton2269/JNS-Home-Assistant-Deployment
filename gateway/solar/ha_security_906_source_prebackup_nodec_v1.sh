#!/usr/bin/env bash
# JNS Solar HA-Security VM906: guarded PRELIMINARY backup.
# Run from Node C root; leaves HA-Security live and untouched.
set -Eeuo pipefail
umask 077
die(){ echo "VM906_BACKUP_BLOCKED=$1" >&2; exit 1; }
[[ "$(id -u)" == 0 && "$(hostname -s)" == nodec ]] || die wrong_host
[[ "$(qm status 906)" == 'status: running' ]] || die vm906_not_running
[[ "$(qm config 906 | sed -n 's/^name: //p')" == ha-security ]] || die source_identity_mismatch
[[ -f /etc/pve/qemu-server/906.conf ]] || die config_missing
if qm config 906 | grep -Eq '^(usb[0-9]+|hostpci[0-9]+|args|hookscript):'; then
 die passthrough_needs_review
fi
NFS=/mnt/pve/nfs-ct
findmnt -rn -M "$NFS" -t nfs,nfs4 >/dev/null || die nfs_not_mounted
[[ "$(df -Pk "$NFS" | awk 'NR==2{print $4}')" -ge 104857600 ]] || die insufficient_space
BASE="$NFS/JNS-Solar-Archives/HA-Security-906"
[[ ! -L "$NFS/JNS-Solar-Archives" && ! -L "$BASE" ]] || die symlink_refused
install -d -m 0700 "$BASE" || die nfs_directory_unavailable
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
DIR="$BASE/source-snapshot-$STAMP"
[[ ! -e "$DIR" ]] || die archive_collision
install -d -m 0700 "$DIR" || die private_archive_unavailable
qm config 906 > "$DIR/vm906-proxmox-original.conf"
chmod 0600 "$DIR/vm906-proxmox-original.conf"
echo "VM906_PRELIMINARY_NFS_BACKUP_STARTED=yes"
if ! timeout 2400 vzdump 906 --mode snapshot --compress zstd --dumpdir "$DIR" >"$DIR/private-vzdump.log" 2>&1; then
 die backup_failed_check_private_log
fi
shopt -s nullglob
set -- "$DIR"/vzdump-qemu-906-*.vma.zst
[[ "$#" == 1 ]] || die expected_single_backup_file
ARCHIVE="$1"
[[ -f "$ARCHIVE" && ! -L "$ARCHIVE" ]] || die archive_file_not_regular
[[ "$(stat -c %s "$ARCHIVE")" -ge 1048576 ]] || die archive_too_small
chmod 0600 "$ARCHIVE"
timeout 1200 zstd -q -t "$ARCHIVE" >"$DIR/private-zstd.log" 2>&1 || die backup_compression_test_failed
python3 - "$ARCHIVE" "$DIR/vm906-proxmox-original.conf" "$DIR/MANIFEST.json" <<'PY'
import datetime,hashlib,json,os,pathlib,sys
archive,config,manifest=map(pathlib.Path,sys.argv[1:])
def hash_file(p):
 h=hashlib.sha256()
 with p.open("rb") as f:
  for chunk in iter(lambda:f.read(4*1024*1024),b""):h.update(chunk)
 return h.hexdigest()
o={"schema":"jns.solar.vm906.source-snapshot.v1","vmid":906,
   "source_node":"nodec","target_node":"nodea",
   "source_vm_remained_running":True,
   "archive_name":archive.name,"bytes":archive.stat().st_size,
   "sha256":hash_file(archive),"config_sha256":hash_file(config),
   "zstd_integrity_passed":True,"final_quiesced_sync_required":True,
   "created_utc":datetime.datetime.now(datetime.timezone.utc).isoformat()}
with manifest.open("x") as f:json.dump(o,f,indent=2,sort_keys=True);f.write("\n")
os.chmod(manifest,0o600)
print("VM906_NFS_BACKUP_SHA256="+o["sha256"])
print("VM906_NFS_BACKUP_SIZE_BYTES="+str(o["bytes"]))
PY
[[ "$(qm status 906)" == 'status: running' ]] || die source_state_unexpected
echo "VM906_NFS_PRELIMINARY_BACKUP_VERIFIED=yes"
echo "VM906_PRODUCTION_SOURCE_UNCHANGED=yes"
echo "VM906_TARGET_NOT_STARTED=yes"
