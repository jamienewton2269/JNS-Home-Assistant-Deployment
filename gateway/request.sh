#!/usr/bin/env bash
set -euo pipefail

echo "=== INSTALL NEW HA ZFS REPLICATION ENGINE ==="

cat > /tmp/jns-ha-replica-receiver <<'WRAP'
#!/usr/bin/env bash
set -euo pipefail
cmd="${SSH_ORIGINAL_COMMAND:-}"
valid_dataset() { [[ "$1" =~ ^vmdata/vm-(902|903|905)-disk-[0-9]+$ ]]; }
valid_snap() { [[ "$1" =~ ^jns-repl-[0-9]{8}T[0-9]{6}$ ]]; }
case "$cmd" in
  probe)
    echo "JNS-HA-REPLICA-RECEIVER OK"
    ;;
  "vm-status "*)
    vmid="${cmd#vm-status }"; [[ "$vmid" =~ ^(902|903|905)$ ]] || exit 64
    qm status "$vmid" 2>/dev/null || echo "status: absent"
    ;;
  "snapshots "*)
    ds="${cmd#snapshots }"; valid_dataset "$ds" || exit 64
    zfs list -H -t snapshot -o name -s creation -r "$ds" 2>/dev/null || true
    ;;
  "dataset-exists "*)
    ds="${cmd#dataset-exists }"; valid_dataset "$ds" || exit 64
    zfs list -H "$ds" >/dev/null 2>&1
    ;;
  "rename-old "*)
    rest="${cmd#rename-old }"; ds="${rest%% *}"; suffix="${rest#* }"
    valid_dataset "$ds" || exit 64
    [[ "$suffix" =~ ^pre-jns-[0-9]{8}T[0-9]{6}$ ]] || exit 64
    if zfs list -H "$ds" >/dev/null 2>&1; then
      zfs rename "$ds" "vmdata/${ds#vmdata/}.${suffix}"
    fi
    ;;
  "receive "*)
    ds="${cmd#receive }"; valid_dataset "$ds" || exit 64
    exec zfs receive -u -F "$ds"
    ;;
  "destroy-snapshot "*)
    full="${cmd#destroy-snapshot }"; ds="${full%@*}"; snap="${full#*@}"
    valid_dataset "$ds" || exit 64; valid_snap "$snap" || exit 64
    zfs destroy "$ds@$snap" 2>/dev/null || true
    ;;
  "install-config "*)
    vmid="${cmd#install-config }"; [[ "$vmid" =~ ^(902|903|905)$ ]] || exit 64
    if qm status "$vmid" 2>/dev/null | grep -q '^status: running$'; then
      echo "refusing config update while target VM is running" >&2; exit 79
    fi
    tmp="/etc/pve/qemu-server/.${vmid}.jns-replica.tmp"
    cat > "$tmp"
    grep -Eq '^scsi0: vmdata:vm-'${vmid}'-disk-[0-9]+' "$tmp" || { rm -f "$tmp"; exit 65; }
    grep -Eq '^net0:' "$tmp" || { rm -f "$tmp"; exit 65; }
    grep -Eq '^(usb|hostpci)[0-9]+:' "$tmp" && { rm -f "$tmp"; echo "passthrough device refused" >&2; exit 77; }
    sed -E -i 's/^onboot:.*/onboot: 0/' "$tmp"
    grep -q '^onboot:' "$tmp" || echo 'onboot: 0' >> "$tmp"
    sed -E -i '/^net0:/ s/,link_down=[01]//g; /^net0:/ s/$/,link_down=1/' "$tmp"
    cp -a "/etc/pve/qemu-server/${vmid}.conf" "/root/${vmid}.conf.pre-jns-replica" 2>/dev/null || true
    mv "$tmp" "/etc/pve/qemu-server/${vmid}.conf"
    qm set "$vmid" --onboot 0 >/dev/null
    qm status "$vmid"
    qm config "$vmid" | grep -E '^(name|memory|balloon|cores|net0|scsi0|efidisk0|onboot|startup|tags):'
    ;;
  *)
    echo "JNS HA replica receiver: command refused" >&2
    exit 64
    ;;
esac
WRAP
scp /tmp/jns-ha-replica-receiver nodea:/usr/local/sbin/jns-ha-replica-receiver
ssh nodea 'chmod 700 /usr/local/sbin/jns-ha-replica-receiver'

cat > /tmp/jns-ha-replicate <<'SEND'
#!/usr/bin/env bash
set -Eeuo pipefail
exec 9>/run/lock/jns-ha-replication.lock
flock -n 9 || exit 0

TARGET="root@10.10.10.225"
KEY="/root/.ssh/jns_ha_replication"
SSH=(ssh -i "$KEY" -o BatchMode=yes -o ConnectTimeout=8 -o ServerAliveInterval=10 -o ServerAliveCountMax=3 "$TARGET")
STATE_DIR=/var/lib/jns-ha-replication
mkdir -p "$STATE_DIR"
stamp="$(date +%Y%m%dT%H%M%S)"
snap="jns-repl-$stamp"
log="$STATE_DIR/last-run.log"
exec > >(tee "$log") 2>&1

echo "START $(date -Is)"
"${SSH[@]}" probe

for vmid in 902 903 905; do
  echo "=== VM $vmid ==="
  qm status "$vmid" | grep -q '^status: running$' || { echo "SKIP source VM not running"; continue; }
  target_status="$("${SSH[@]}" "vm-status $vmid" || true)"
  echo "target: $target_status"
  grep -q '^status: running$' <<<"$target_status" && { echo "ERROR target VM $vmid is running; refusing replication"; exit 79; }

  mapfile -t datasets < <(zfs list -H -o name | grep -E "^vmdata/vm-${vmid}-disk-[0-9]+$" | sort)
  (("${#datasets[@]}" > 0)) || { echo "ERROR no source datasets for VM $vmid"; exit 66; }

  frozen=0
  if timeout 8s qm guest cmd "$vmid" fsfreeze-freeze >/dev/null 2>&1; then
    frozen=1
    echo "guest filesystem frozen"
  else
    echo "guest freeze unavailable; using crash-consistent ZFS snapshot"
  fi
  thaw() {
    if [ "$frozen" -eq 1 ]; then
      timeout 8s qm guest cmd "$vmid" fsfreeze-thaw >/dev/null 2>&1 || true
      frozen=0
      echo "guest filesystem thawed"
    fi
  }
  trap thaw RETURN

  for ds in "${datasets[@]}"; do
    zfs snapshot "$ds@$snap"
  done
  thaw
  trap - RETURN

  for ds in "${datasets[@]}"; do
    src_snaps="$(zfs list -H -t snapshot -o name -s creation -r "$ds" | sed -n "s#^$ds@##p" | grep '^jns-repl-' || true)"
    dst_snaps="$("${SSH[@]}" "snapshots $ds" | sed -n "s#^$ds@##p" | grep '^jns-repl-' || true)"
    prev=""
    while read -r s; do
      [ -n "$s" ] && grep -qxF "$s" <<<"$dst_snaps" && prev="$s"
    done <<<"$src_snaps"

    if [ -z "$prev" ]; then
      if "${SSH[@]}" "dataset-exists $ds" >/dev/null 2>&1; then
        "${SSH[@]}" "rename-old $ds pre-jns-$stamp"
        echo "$ds: preserved old target dataset"
      fi
      echo "$ds: full send"
      zfs send -p "$ds@$snap" | "${SSH[@]}" "receive $ds"
    else
      echo "$ds: incremental from $prev"
      zfs send -p -i "$ds@$prev" "$ds@$snap" | "${SSH[@]}" "receive $ds"
    fi
  done

  qm config "$vmid" | "${SSH[@]}" "install-config $vmid"

  for ds in "${datasets[@]}"; do
    mapfile -t olds < <(zfs list -H -t snapshot -o name -s creation -r "$ds" | sed -n "s#^$ds@##p" | grep '^jns-repl-' | head -n -4 || true)
    for old in "${olds[@]}"; do
      zfs destroy "$ds@$old" 2>/dev/null || true
      "${SSH[@]}" "destroy-snapshot $ds@$old" || true
    done
  done
  echo "VM $vmid replicated at $snap"
done

echo "$snap" > "$STATE_DIR/last-success"
date -Is > "$STATE_DIR/last-success-time"
echo "SUCCESS $(date -Is) $snap"
SEND

scp /tmp/jns-ha-replicate nodeb:/usr/local/sbin/jns-ha-replicate
ssh nodeb 'chmod 700 /usr/local/sbin/jns-ha-replicate; mkdir -p /var/lib/jns-ha-replication'

cat > /tmp/jns-ha-replication.service <<'UNIT'
[Unit]
Description=JNS HA Node B to Node A fenced ZFS replication
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
ExecStart=/usr/local/sbin/jns-ha-replicate
TimeoutStartSec=1800
Nice=10
IOSchedulingClass=best-effort
IOSchedulingPriority=7
UNIT

cat > /tmp/jns-ha-replication.timer <<'TIMER'
[Unit]
Description=Refresh JNS HA fenced standbys every five minutes

[Timer]
OnBootSec=2min
OnUnitActiveSec=5min
AccuracySec=20s
Persistent=true
Unit=jns-ha-replication.service

[Install]
WantedBy=timers.target
TIMER

scp /tmp/jns-ha-replication.service /tmp/jns-ha-replication.timer nodeb:/etc/systemd/system/
ssh nodeb 'systemctl daemon-reload; systemctl enable --now jns-ha-replication.timer; systemctl start --no-block jns-ha-replication.service; systemctl --no-pager status jns-ha-replication.timer | head -20; echo; systemctl --no-pager status jns-ha-replication.service | head -30 || true'

echo "=== ENGINE INSTALLED ==="
