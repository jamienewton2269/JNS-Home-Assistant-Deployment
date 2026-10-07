#!/usr/bin/env bash
set -Eeuo pipefail

mkdir -p gateway/results
OUT=gateway/results/offline-vm900-snug-sofa-led-latest.txt

ssh -o BatchMode=yes -o ConnectTimeout=10 nodeb 'bash -s' >"$OUT" 2>&1 <<'NODEB'
set -Eeuo pipefail
VMID=900
echo '=== OFFLINE HOME ASSISTANT REFERENCE AUDIT ==='
date -Is
echo "host=$(hostname) vmid=$VMID"
qm status "$VMID"
test "$(qm status "$VMID" | awk '{print $2}')" = stopped || { echo 'REFUSED: VM900 is not stopped'; exit 41; }
qm config "$VMID"

diskline="$(qm config "$VMID" | awk -F': ' '/^(scsi|sata|virtio|ide)[0-9]+:/ && $2 !~ /media=cdrom/ {print $2; exit}')"
vol="${diskline%%,*}"
path="$(pvesm path "$vol")"
echo "disk_volume=$vol"
echo "disk_path=$path"

modprobe nbd max_part=16 || true
NBD=/dev/nbd7
qemu-nbd --disconnect "$NBD" >/dev/null 2>&1 || true
qemu-nbd --read-only --connect="$NBD" "$path"
trap 'umount /mnt/jns-ha-ref 2>/dev/null || true; qemu-nbd --disconnect "$NBD" 2>/dev/null || true; rmdir /mnt/jns-ha-ref 2>/dev/null || true' EXIT
partprobe "$NBD" || true
udevadm settle || true
lsblk -f "$NBD"

mkdir -p /mnt/jns-ha-ref
found=0
while read -r part fstype; do
  case "$fstype" in ext4|xfs) ;; *) continue ;; esac
  umount /mnt/jns-ha-ref 2>/dev/null || true
  if mount -o ro,noload "$part" /mnt/jns-ha-ref 2>/dev/null || mount -o ro "$part" /mnt/jns-ha-ref 2>/dev/null; then
    for ROOT in /mnt/jns-ha-ref/supervisor/homeassistant /mnt/jns-ha-ref/data/supervisor/homeassistant /mnt/jns-ha-ref/mnt/data/supervisor/homeassistant; do
      if [ -d "$ROOT/.storage" ]; then
        found=1
        echo "ha_root=$ROOT"
        python3 - "$ROOT" <<'PY'
import json, os, re, sys
root=sys.argv[1]
rx=re.compile(r'(snug|sofa|led)', re.I)
for rel,key in [
    ('.storage/core.area_registry','areas'),
    ('.storage/core.device_registry','devices'),
    ('.storage/core.entity_registry','entities'),
    ('.storage/core.config_entries','entries'),
]:
    p=os.path.join(root,rel)
    if not os.path.exists(p):
        continue
    try:
        obj=json.load(open(p,encoding='utf-8'))
    except Exception as e:
        print('ERROR',rel,e)
        continue
    items=obj.get('data',{}).get(key,[])
    print(f'--- {rel} matching items ---')
    for item in items:
        s=json.dumps(item,ensure_ascii=False)
        if rx.search(s):
            safe=dict(item)
            for k in list(safe):
                if any(x in k.lower() for x in ('password','token','secret','local_key','access_key','api_key')):
                    safe[k]='<REDACTED>'
            print(json.dumps(safe,ensure_ascii=False,sort_keys=True))

for rel in ('automations.yaml','scripts.yaml','.storage/lovelace','.storage/lovelace.dashboard_testing'):
    p=os.path.join(root,rel)
    if not os.path.exists(p):
        continue
    try:
        txt=open(p,encoding='utf-8',errors='ignore').read()
    except Exception:
        continue
    if rx.search(txt):
        print(f'--- text matches in {rel} ---')
        for i,line in enumerate(txt.splitlines(),1):
            if rx.search(line):
                print(f'{i}: {line[:500]}')
PY
        break
      fi
    done
    [ "$found" -eq 1 ] && break
  fi
done < <(lsblk -lnpo NAME,FSTYPE "$NBD" | tail -n +2)

[ "$found" -eq 1 ] || { echo 'No HA config root located'; exit 42; }
echo OFFLINE_REFERENCE_AUDIT_OK
NODEB

cat "$OUT"
