#!/usr/bin/env bash
# One-time Node C installer for the narrowly scoped CT130 deploy gate.
set -Eeuo pipefail

fail() { echo "INSTALL BLOCKED: $*" >&2; exit 1; }
[[ $EUID -eq 0 ]] || fail "run as root on Node C"

repo_root="$(cd "$(dirname "$0")" && pwd)"
wrapper="$repo_root/jns-netmon-deploy-v0.3.28.sh"
expected=867419b4043127068c9f926d3176ab23172c2357358aa0e08678b9f972a0ebb8

[[ -f "$wrapper" ]] || fail "deploy wrapper is missing"
actual="$(sha256sum "$repo_root/../payloads/jns-netmon-web-repair-v0.3.28.sh" | cut -d ' ' -f1)"
[[ "$actual" == "$expected" ]] || fail "repository payload does not match pinned v0.3.28 SHA-256"

if [[ -e /usr/local/sbin/jns-netmon-deploy ]]; then
  existing="$(sha256sum /usr/local/sbin/jns-netmon-deploy | cut -d ' ' -f1)"
  candidate="$(sha256sum "$wrapper" | cut -d ' ' -f1)"
  [[ "$existing" == "$candidate" ]] || fail "/usr/local/sbin/jns-netmon-deploy already exists with different contents; refusing to replace it"
else
  install -o root -g root -m 0755 "$wrapper" /usr/local/sbin/jns-netmon-deploy
fi

echo "Installed root:root 0755 /usr/local/sbin/jns-netmon-deploy"
echo "Pinned payload SHA-256: $expected"
echo "No sudoers or CT130 files were changed by this installer."
