#!/usr/bin/env bash
set -Eeuo pipefail

echo "=== READ-ONLY INVENTORY: OFFLINE MONOLITH / SNUG SOFA LED ==="
date -Is
echo "Host: $(hostname -f 2>/dev/null || hostname)"

echo "--- Node C VM inventory ---"
qm list || true

mapfile -t CANDIDATES < <(
  qm list 2>/dev/null | awk 'NR>1 {print $1" "$2" "$3}' |
  awk 'tolower($2) ~ /(home|assistant|ha|monolith)/ || $1==900 {print $1}' |
  awk '!seen[$0]++'
)

if [ "${#CANDIDATES[@]}" -eq 0 ]; then
  echo "No obvious HA VM candidate found by name/VMID; listing all stopped VMs."
  mapfile -t CANDIDATES < <(qm list 2>/dev/null | awk 'NR>1 && $3=="stopped" {print $1}')
fi

echo "Candidates: ${CANDIDATES[*]:-none}"

modprobe nbd max_part=16 2>/dev/null || true

inspect_vm() {
  local vmid="$1"
  local status name cfg diskline vol path nbd mnt
  status="$(qm status "$vmid" 2>/dev/null | awk '{print $2}')"
  name="$(qm config "$vmid" 2>/dev/null | awk -F': ' '$1=="name"{print $2; exit}')"
  echo
  echo "=== VM $vmid name=${name:-unknown} status=${status:-unknown} ==="
  if [ "$status" != "stopped" ]; then
    echo "SKIP: VM is not stopped; reference audit will not touch a running VM."
    return 0
  fi
  qm config "$vmid" | sed -n '1,220p'

  diskline="$(qm config "$vmid" | awk -F': ' '/^(scsi|sata|virtio|ide)[0-9]+:/ && $2 !~ /media=cdrom/ {print $2; exit}')"
  vol="${diskline%%,*}"
  if [ -z "$vol" ]; then
    echo "No data disk found."
    return 0
  fi
  path="$(pvesm path "$vol" 2>/dev/null || true)"
  echo "Primary disk volume: $vol"
  echo "Resolved path: ${path:-UNRESOLVED}"
  if [ -z "$path" ] || [ ! -e "$path" ]; then
    echo "Cannot resolve disk path; skipping filesystem inspection."
    return 0
  fi

  nbd=""
  for d in /dev/nbd{0..7}; do
    [ -b "$d" ] || continue
    if ! lsblk -n "$d" 2>/dev/null | grep -q .; then nbd="$d"; break; fi
  done
  if [ -z "$nbd" ]; then
    echo "No free NBD device available."
    return 0
  fi

  mnt="/mnt/jns-ha-ref-$vmid"
  mkdir -p "$mnt"
  qemu-nbd --read-only --connect="$nbd" "$path"
  partprobe "$nbd" 2>/dev/null || true
  udevadm settle 2>/dev/null || true

  cleanup_one() {
    umount "$mnt" 2>/dev/null || true
    qemu-nbd --disconnect "$nbd" 2>/dev/null || true
    rmdir "$mnt" 2>/dev/null || true
  }
  trap cleanup_one RETURN

  echo "--- Partitions ---"
  lsblk -f "$nbd" || true

  local parts=()
  mapfile -t parts < <(lsblk -lnpo NAME,FSTYPE "$nbd" | awk '$2 ~ /ext4|xfs/ {print $1}' | tac)
  for part in "${parts[@]}"; do
    if mount -o ro,noload "$part" "$mnt" 2>/dev/null || mount -o ro "$part" "$mnt" 2>/dev/null; then
      echo "--- Mounted $part read-only ---"
      local haroot=""
      for p in         "$mnt/supervisor/homeassistant"         "$mnt/data/supervisor/homeassistant"         "$mnt/mnt/data/supervisor/homeassistant"; do
        if [ -d "$p/.storage" ]; then haroot="$p"; break; fi
      done
      if [ -z "$haroot" ]; then
        haroot="$(find "$mnt" -maxdepth 5 -type d -path '*/supervisor/homeassistant/.storage' -printf '%h\n' 2>/dev/null | head -1 || true)"
      fi
      if [ -n "$haroot" ] && [ -d "$haroot/.storage" ]; then
        echo "HA config root: $haroot"
        echo "--- Matching text: snug / sofa / led ---"
        grep -RniE --binary-files=without-match           '(snug.{0,80}(sofa|led|light)|sofa.{0,80}(snug|led|light)|snug sofa|sofa led)'           "$haroot/.storage" "$haroot/configuration.yaml" "$haroot/automations.yaml" "$haroot/scripts.yaml"           2>/dev/null | head -300 || true

        echo "--- Broader Snug registry matches ---"
        grep -niE '"(name|name_by_user|entity_id|original_name|area_id|platform|domain)".{0,120}snug|snug'           "$haroot/.storage/core.entity_registry"           "$haroot/.storage/core.device_registry"           "$haroot/.storage/core.config_entries"           2>/dev/null | head -300 || true

        echo "--- Relevant registry/config-entry context via Python ---"
        python3 - "$haroot" <<'PY'
import json, os, re, sys
root=sys.argv[1]
needle=re.compile(r'(snug|sofa|led)', re.I)
files=[
 '.storage/core.entity_registry',
 '.storage/core.device_registry',
 '.storage/core.config_entries',
 '.storage/core.area_registry',
]
for rel in files:
    p=os.path.join(root,rel)
    if not os.path.exists(p):
        continue
    try:
        obj=json.load(open(p,encoding='utf-8'))
    except Exception as e:
        print(f'JSON_READ_ERROR {rel}: {e}')
        continue
    data=obj.get('data',{})
    items=[]
    for key in ('entities','devices','entries','areas'):
        if isinstance(data.get(key),list):
            items=data[key]
            break
    print(f'FILE {rel} ITEMS {len(items)}')
    for item in items:
        s=json.dumps(item,ensure_ascii=False)
        if needle.search(s):
            # Redact common credential/token fields but retain integration identity and host/device metadata.
            safe=dict(item)
            for k in list(safe):
                if any(x in k.lower() for x in ('password','token','secret','access_token','refresh_token','api_key')):
                    safe[k]='<REDACTED>'
            print(json.dumps(safe,ensure_ascii=False,sort_keys=True))
PY
        umount "$mnt" 2>/dev/null || true
        qemu-nbd --disconnect "$nbd" 2>/dev/null || true
        trap - RETURN
        rmdir "$mnt" 2>/dev/null || true
        return 0
      fi
      umount "$mnt" 2>/dev/null || true
    fi
  done

  qemu-nbd --disconnect "$nbd" 2>/dev/null || true
  trap - RETURN
  rmdir "$mnt" 2>/dev/null || true
  echo "No Home Assistant data partition found on VM $vmid."
}

for vmid in "${CANDIDATES[@]}"; do
  inspect_vm "$vmid"
done

echo
echo "READ_ONLY_INVENTORY_COMPLETE $(date -Is)"
