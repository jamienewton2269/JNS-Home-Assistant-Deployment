#!/usr/bin/env python3
"""JNS Solar CT212 MQTT preliminary snapshot archive to Node A.
Safe staging only: source broker continues running, destination not restored
or started; no DNS, onboot, network or service modifications.
"""
import re,shlex,subprocess,sys
SSH=["ssh","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes","-o","ConnectTimeout=6"]
def fail(reason):
 print("JNS_SOLAR_MQTT_STAGE_BLOCKED="+reason,flush=True);sys.exit(1)
def remote(host,script,timeout=180):
 try:p=subprocess.run(SSH+[host,shlex.join(["bash","-c",script])],capture_output=True,text=True,timeout=timeout)
 except (OSError,subprocess.TimeoutExpired):fail("remote_timeout")
 if p.returncode:fail(host+"_failure_"+str(p.returncode))
 return p.stdout
SOURCE=r'''
set -Eeuo pipefail
umask 077
test "$(hostname -s)" = nodeb
test "$(pct status 212)" = "status: running"
c="$(pct config 212)"
printf '%s\n' "$c" | grep -Fxq 'hostname: mqtt-infra-a'
printf '%s\n' "$c" | grep -Eq '^rootfs: vmdata:'
if printf '%s\n' "$c" | grep -Eq '^(mp[0-9]+|lxc.mount.entry|dev[0-9]+):'; then exit 73; fi
free="$(df -Pk /var/lib/vz/dump | awk 'NR==2{print $4}')"
test "$free" -ge 5242880
base=/var/lib/jns-solar/ct-mqtt-snapshots
install -d -m 0700 "$base"
dir="$(mktemp -d "$base/stage.XXXXXXXX")"
chmod 0700 "$dir"
if ! timeout 320 vzdump 212 --mode snapshot --compress zstd --dumpdir "$dir" >"$dir/private-backup.log" 2>&1; then exit 74; fi
shopt -s nullglob
set -- "$dir"/vzdump-lxc-212-*.tar.zst
test "$#" -eq 1
archive="$1"
test -f "$archive" && test ! -L "$archive"
bytes="$(stat -c '%s' "$archive")"
test "$bytes" -gt 10000 && test "$bytes" -lt 4294967296
sha="$(sha256sum "$archive" | awk '{print $1}')"
printf 'JNS_SNAPSHOT_METADATA=%s|%s|%s\n' "$archive" "$bytes" "$sha"
'''
def main():
 print("JNS_SOLAR_MQTT_NODEA_STAGING_START",flush=True)
 r=remote("nodea",'''set -eu
test "$(hostname -s)" = nodea
if pct config 230 >/dev/null 2>&1; then exit 77; fi
df -Pk /var/lib/vz/dump | awk 'NR==2 {if ($4<5242880) exit 78}'
test -x /usr/sbin/pct
echo JNS_TARGET_230_FREE
''',20)
 if "JNS_TARGET_230_FREE" not in r:fail("destination_not_free")
 r=remote("nodeb",SOURCE,375)
 match=re.search(r"^JNS_SNAPSHOT_METADATA=([A-Za-z0-9/._-]+)\|(\d+)\|([a-f0-9]{64})$",r,re.M)
 if not match:fail("backup_not_confirmed")
 path,size,sha=match.groups();size=int(size)
 if not path.startswith("/var/lib/jns-solar/ct-mqtt-snapshots/stage.") or size>4*1024**3:fail("invalid_archive_metadata")
 target_dir="/var/lib/jns-solar/ct-staging"
 dest=target_dir+"/mqtt-ct212-"+sha[:16]+".tar.zst";partial=dest+".partial"
 remote("nodea","set -Eeuo pipefail; test \"$(hostname -s)\" = nodea; install -d -m 0700 "+shlex.quote(target_dir)+"; test ! -e "+shlex.quote(dest)+"; test ! -e "+shlex.quote(partial),20)
 try:
  source=subprocess.Popen(SSH+["nodeb",shlex.join(["cat",path])],stdout=subprocess.PIPE,stderr=subprocess.DEVNULL)
  sink=subprocess.Popen(SSH+["nodea",shlex.join(["bash","-c","umask 077; cat > "+shlex.quote(partial)])],stdin=source.stdout,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
  source.stdout.close()
  to=sink.wait(timeout=250);fr=source.wait(timeout=250)
 except (OSError,subprocess.TimeoutExpired):fail("transfer_timeout")
 if to!=0 or fr!=0:fail("transfer_failure")
 verify="set -Eeuo pipefail; test \"$(hostname -s)\" = nodea; test ! -e "+shlex.quote(dest)+"; test \"$(stat -c %s "+shlex.quote(partial)+")\" = "+str(size)+"; test \"$(sha256sum "+shlex.quote(partial)+" | awk '{print $1}')\" = "+shlex.quote(sha)+"; chmod 0600 "+shlex.quote(partial)+"; mv -- "+shlex.quote(partial)+" "+shlex.quote(dest)+"; test ! -e /etc/pve/lxc/230.conf; echo VERIFIED"
 if "VERIFIED" not in remote("nodea",verify,45):fail("destination_verification")
 print("JNS_SOLAR_MQTT_BACKUP_STAGED_ON_NODEA=yes",flush=True)
 print("SOURCE_CT_RUNNING_UNCHANGED=yes",flush=True)
 print("DESTINATION_CT230_EXISTS=no",flush=True)
 print("ARCHIVE_BYTES="+str(size),flush=True)
 print("ARCHIVE_SHA256="+sha,flush=True)
 print("FINAL_QUIESCED_BACKUP_REQUIRED=yes",flush=True)
 print("JNS_SOLAR_MQTT_NODEA_STAGING_COMPLETE",flush=True)
if __name__=="__main__":main()
