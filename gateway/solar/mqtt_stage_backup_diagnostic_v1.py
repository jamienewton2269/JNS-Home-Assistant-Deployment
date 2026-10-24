#!/usr/bin/env python3
"""Safe read-only diagnosis of last private Node B CT212 vzdump log.
Outputs categories only; no protected backups/log lines/paths disclosed.
"""
import base64,json,shlex,subprocess
REMOTE=r'''
from pathlib import Path
import json,re
root=Path("/var/lib/jns-solar/ct-mqtt-snapshots")
logs=sorted(root.glob("stage.*/private-backup.log"),key=lambda p:p.stat().st_mtime,reverse=True)
out={"found":bool(logs)}
if logs:
 text=logs[0].read_text(errors="replace")[-250000:]
 cats={
  "backup_started":r"starting new backup job|Starting Backup of CT",
  "guest_snapshot_created":r"create (storage )?snapshot|snapshot mode",
  "snapshot_unsupported":r"snapshot.*not supported|does not support snapshots",
  "guest_read_permission":r"permission denied|operation not permitted",
  "filesystem_readonly":r"Read-only file system",
  "disk_space_exhausted":r"No space left on device",
  "unknown_storage":r"storage .*does not exist|unable to activate storage",
  "mount_error":r"mount failed|can't mount|unmount failed",
  "zfs_snapshot_error":r"zfs.*(failed|error)|snapshot.*(failed|error)",
  "vzdump_backup_error":r"ERROR:|command .* failed|TASK ERROR",
  "temporary_directory_problem":r"tmpdir|vzdump\.tmp",
  "archive_write_error":r"tar: .*error|zstd: .*error|failed to write",
  "lock_collision":r"can't lock|already locked",
  "ct_stop_detected":r"stopping CT|stop container",
 }
 out["categories"]=[k for k,rx in cats.items() if re.search(rx,text,re.I)]
 out["line_count"]=len(text.splitlines())
 out["contains_error"]="ERROR" in text.upper() or "failed" in text.lower()
 # Categorise errors and a final non-sensitive token group; never print raw log.
 errorlines=[l for l in text.splitlines() if re.search(r"error|fail|abort",l,re.I)]
 out["error_line_count"]=len(errorlines)
 out["last_error_flags"]={
   "generic_command_failure":any("command" in x.lower() for x in errorlines[-5:]),
   "snapshot":any("snapshot" in x.lower() for x in errorlines[-5:]),
   "disk":any("disk" in x.lower() for x in errorlines[-5:]),
   "mount":any("mount" in x.lower() for x in errorlines[-5:]),
   "tar":any("tar" in x.lower() for x in errorlines[-5:]),
 }
print("JNS_CT212_BACKUP_DIAG="+json.dumps(out,sort_keys=True))
'''
def main():
 encoded=base64.b64encode(REMOTE.encode()).decode()
 args=["ssh","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes","nodeb",
 shlex.join(["python3","-c","exec(__import__('base64').b64decode('"+encoded+"'))"])]
 try:r=subprocess.run(args,capture_output=True,text=True,timeout=25)
 except (OSError,subprocess.TimeoutExpired):print("JNS_CT212_DIAG_BLOCKED=ssh_timeout");return
 for l in r.stdout.splitlines():
  if l.startswith("JNS_CT212_BACKUP_DIAG="):print(l)
 if r.returncode:print("JNS_CT212_DIAG_BLOCKED=remote_exit_"+str(r.returncode))
if __name__=="__main__":main()
