#!/usr/bin/env bash
set -euo pipefail
echo "=== PROVISION NODE C GITHUB RUNNER SSH IDENTITY ==="
echo "host=$(hostname) user=$(whoami) home=$HOME"
date -Is

mkdir -p "$HOME/.ssh"
chmod 700 "$HOME/.ssh"
KEY="$HOME/.ssh/id_ed25519"
if [ ! -f "$KEY" ]; then
  ssh-keygen -q -t ed25519 -N '' -C 'jns-nodec-github-gateway' -f "$KEY"
  echo "created=YES"
else
  echo "created=NO existing key retained"
fi
chmod 600 "$KEY"
chmod 644 "$KEY.pub"

cat > "$HOME/.ssh/config" <<'EOF'
Host nodea
  HostName 10.10.10.225
  User root
  IdentityFile ~/.ssh/id_ed25519
  IdentitiesOnly yes
  StrictHostKeyChecking accept-new

Host nodeb
  HostName 10.10.10.235
  User root
  IdentityFile ~/.ssh/id_ed25519
  IdentitiesOnly yes
  StrictHostKeyChecking accept-new
EOF
chmod 600 "$HOME/.ssh/config"

echo
echo "PUBLIC_KEY_BEGIN"
cat "$KEY.pub"
echo "PUBLIC_KEY_END"
echo
ssh-keygen -lf "$KEY.pub"

echo
echo "connectivity:"
for h in nodea nodeb; do
  echo "--- $h ---"
  ssh -o BatchMode=yes -o ConnectTimeout=5 "$h" 'echo CONNECTED; hostname; whoami; pveversion | head -1' 2>&1 || true
done
