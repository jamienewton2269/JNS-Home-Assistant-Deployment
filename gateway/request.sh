#!/usr/bin/env bash
set -euo pipefail

echo "=== INSTALL RESTRICTED HA REPLICATION CHANNEL ==="

ssh nodeb 'bash -s' <<'NODEB'
set -euo pipefail
install -d -m 700 /root/.ssh
if [ ! -f /root/.ssh/jns_ha_replication ]; then
  ssh-keygen -q -t ed25519 -N "" -f /root/.ssh/jns_ha_replication -C jns-ha-replication-nodeb
fi
chmod 600 /root/.ssh/jns_ha_replication
chmod 644 /root/.ssh/jns_ha_replication.pub
cat /root/.ssh/jns_ha_replication.pub
NODEB

PUB="$(ssh nodeb 'cat /root/.ssh/jns_ha_replication.pub')"

cat > /tmp/jns-ha-replica-receiver <<'WRAP'
#!/usr/bin/env bash
set -euo pipefail
cmd="${SSH_ORIGINAL_COMMAND:-}"
valid_dataset() {
  [[ "$1" =~ ^vmdata/vm-(902|903|905)-disk-[0-9]+$ ]]
}
case "$cmd" in
  probe)
    echo "JNS-HA-REPLICA-RECEIVER OK"
    ;;
  "vm-status "*)
    vmid="${cmd#vm-status }"
    [[ "$vmid" =~ ^(902|903|905)$ ]] || exit 64
    qm status "$vmid" 2>/dev/null || echo "status: absent"
    ;;
  "snapshots "*)
    ds="${cmd#snapshots }"
    valid_dataset "$ds" || exit 64
    zfs list -H -t snapshot -o name -s creation -r "$ds" 2>/dev/null || true
    ;;
  "dataset-exists "*)
    ds="${cmd#dataset-exists }"
    valid_dataset "$ds" || exit 64
    zfs list -H "$ds" >/dev/null 2>&1
    ;;
  "rename-old "*)
    rest="${cmd#rename-old }"
    ds="${rest%% *}"
    suffix="${rest#* }"
    valid_dataset "$ds" || exit 64
    [[ "$suffix" =~ ^pre-jns-[0-9]{8}T[0-9]{6}$ ]] || exit 64
    if zfs list -H "$ds" >/dev/null 2>&1; then
      zfs rename "$ds" "vmdata/${ds#vmdata/}.${suffix}"
    fi
    ;;
  "receive "*)
    ds="${cmd#receive }"
    valid_dataset "$ds" || exit 64
    exec zfs receive -u -F "$ds"
    ;;
  "install-config "*)
    vmid="${cmd#install-config }"
    [[ "$vmid" =~ ^(902|903|905)$ ]] || exit 64
    if qm status "$vmid" 2>/dev/null | grep -q '^status: running$'; then
      echo "refusing config update while target VM is running" >&2
      exit 79
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
ssh nodea 'chmod 700 /usr/local/sbin/jns-ha-replica-receiver; install -d -m 700 /root/.ssh'
ENTRY="restrict,command=\"/usr/local/sbin/jns-ha-replica-receiver\" $PUB"
printf '%s\n' "$ENTRY" | ssh nodea 'grep -F "jns-ha-replication-nodeb" /root/.ssh/authorized_keys >/dev/null 2>&1 || cat >> /root/.ssh/authorized_keys; chmod 600 /root/.ssh/authorized_keys'

echo
echo "=== TEST RESTRICTED CHANNEL ==="
ssh nodeb 'timeout 8s ssh -i /root/.ssh/jns_ha_replication -o BatchMode=yes -o StrictHostKeyChecking=accept-new -o ConnectTimeout=5 root@10.10.10.225 probe'
