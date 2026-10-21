#!/usr/bin/env bash
# Root-owned, no-argument deploy gate for the pinned CT130 v0.3.28 update.
set -Eeuo pipefail

readonly VMID=130
readonly EXPECTED_HOSTNAME=jns-netmon01
readonly EXPECTED_SHA256=867419b4043127068c9f926d3176ab23172c2357358aa0e08678b9f972a0ebb8
readonly PAYLOAD=/home/github-runner/actions-runner/_work/JNS-Home-Assistant-Deployment/JNS-Home-Assistant-Deployment/gateway/payloads/jns-netmon-web-repair-v0.3.28.sh

fail() { echo "NETMON DEPLOY BLOCKED: $*" >&2; exit 1; }

[[ $# -eq 0 ]] || fail "this wrapper accepts no arguments"
[[ $EUID -eq 0 ]] || fail "must be invoked through the approved sudoers rule"
command -v pct >/dev/null || fail "Proxmox pct command is unavailable"
command -v pvesm >/dev/null || fail "Proxmox storage status command is unavailable"
[[ -f "$PAYLOAD" ]] || fail "pinned v0.3.28 payload is not in the Node C runner checkout"

actual_sha="$(sha256sum "$PAYLOAD" | cut -d ' ' -f1)"
[[ "$actual_sha" == "$EXPECTED_SHA256" ]] || fail "payload SHA-256 mismatch (got $actual_sha)"

config="$(pct config "$VMID")" || fail "cannot read CT130 configuration"
grep -Fxq "hostname: $EXPECTED_HOSTNAME" <<<"$config" || fail "VMID 130 is not the expected $EXPECTED_HOSTNAME container"
grep -q '^status: running$' < <(pct status "$VMID") || fail "CT130 is not running"

rootfs_line="$(grep '^rootfs: ' <<<"$config" || true)"
[[ -n "$rootfs_line" ]] || fail "CT130 rootfs storage is not configured"
storage_id="${rootfs_line#rootfs: }"
storage_id="${storage_id%%:*}"
[[ "$storage_id" =~ ^[A-Za-z0-9_.-]+$ ]] || fail "could not safely identify CT130 rootfs storage"
usage="$(pvesm status --storage "$storage_id" | python3 -c 'import sys; rows=[x.split() for x in sys.stdin.read().splitlines()[1:] if x.strip()]; print(rows[0][-1].rstrip("%") if len(rows)==1 else "")')"
[[ "$usage" =~ ^[0-9]+([.][0-9]+)?$ ]] || fail "could not determine storage usage for $storage_id"
python3 - "$usage" <<'PY'
import sys
usage=float(sys.argv[1])
if usage >= 85:
    print(f"NETMON DEPLOY BLOCKED: CT130 storage is {usage:.1f}% used; free space before reapplying.", file=sys.stderr)
    raise SystemExit(1)
print(f"CT130 rootfs storage preflight: {usage:.1f}% used")
PY

echo "Deploying pinned Network Monitor v0.3.28 to CT130 ($EXPECTED_HOSTNAME)."
exec /bin/bash "$PAYLOAD"
