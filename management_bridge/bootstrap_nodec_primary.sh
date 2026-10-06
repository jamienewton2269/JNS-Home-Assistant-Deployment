#!/usr/bin/env bash
set -euo pipefail

PUBKEY="${JNS_LAPTOP_PUBKEY:-}"
MGMT_USER="${JNS_MGMT_USER:-jns-mcp}"
APP_DIR="/opt/jns-management-bridge"
ETC_DIR="/etc/jns-management-bridge"

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run as root on Node C." >&2
  exit 1
fi

if [[ -z "$PUBKEY" || "$PUBKEY" != ssh-ed25519* ]]; then
  echo "Set JNS_LAPTOP_PUBKEY to the laptop's ssh-ed25519 public key." >&2
  exit 1
fi

echo "== Node C primary management bootstrap =="
echo "Host: $(hostname)"
echo "IP(s): $(hostname -I 2>/dev/null || true)"

export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq openssh-server openssh-client sudo curl python3 openssl >/dev/null

if ! id "$MGMT_USER" >/dev/null 2>&1; then
  useradd -m -s /bin/bash "$MGMT_USER"
fi
usermod -L "$MGMT_USER" || true

HOME_DIR="$(getent passwd "$MGMT_USER" | cut -d: -f6)"
install -d -m 0700 -o "$MGMT_USER" -g "$MGMT_USER" "$HOME_DIR/.ssh"
printf '%s\n' "$PUBKEY" > "$HOME_DIR/.ssh/authorized_keys"
chown "$MGMT_USER:$MGMT_USER" "$HOME_DIR/.ssh/authorized_keys"
chmod 0600 "$HOME_DIR/.ssh/authorized_keys"

cat > "/etc/ssh/sshd_config.d/90-jns-mcp.conf" <<EOF
Match User $MGMT_USER
    PubkeyAuthentication yes
    PasswordAuthentication no
    KbdInteractiveAuthentication no
    X11Forwarding no
    AllowTcpForwarding yes
    GatewayPorts no
    PermitTunnel no
EOF

sshd -t
systemctl enable --now ssh
systemctl reload ssh

cat > /etc/sudoers.d/jns-mcp-management <<EOF
$MGMT_USER ALL=(root) NOPASSWD: /usr/sbin/qm, /usr/sbin/pct, /usr/bin/pvesh, /usr/sbin/pvesm, /usr/sbin/vzdump, /usr/bin/systemctl, /usr/bin/journalctl, /usr/bin/ss, /usr/sbin/ip, /usr/bin/lsblk, /usr/bin/df, /usr/bin/find, /usr/bin/grep, /usr/bin/cat, /usr/bin/rsync, /usr/bin/cp, /opt/jns-management-bridge/start_temp_tunnel.sh, /opt/jns-management-bridge/stop_temp_tunnel.sh
EOF
chmod 0440 /etc/sudoers.d/jns-mcp-management
visudo -cf /etc/sudoers.d/jns-mcp-management >/dev/null

if [[ ! -f "$HOME_DIR/.ssh/jns_infra_ed25519" ]]; then
  sudo -u "$MGMT_USER" ssh-keygen -q -t ed25519 -N "" -f "$HOME_DIR/.ssh/jns_infra_ed25519" -C "jns-nodec-management"
fi

cat > "$HOME_DIR/.ssh/config" <<'EOF'
Host node-a
    HostName 10.10.10.225
    User root
    IdentityFile ~/.ssh/jns_infra_ed25519
    IdentitiesOnly yes
    StrictHostKeyChecking accept-new

Host node-b
    HostName 10.10.10.235
    User root
    IdentityFile ~/.ssh/jns_infra_ed25519
    IdentitiesOnly yes
    StrictHostKeyChecking accept-new
EOF
chown "$MGMT_USER:$MGMT_USER" "$HOME_DIR/.ssh/config"
chmod 0600 "$HOME_DIR/.ssh/config"

JNS_BRIDGE_USER="$MGMT_USER"   curl -fsSL "https://raw.githubusercontent.com/jamienewton2269/JNS-Home-Assistant-Deployment/main/management_bridge/install.sh"   -o /tmp/jns-management-bridge-install.sh
JNS_BRIDGE_USER="$MGMT_USER" bash /tmp/jns-management-bridge-install.sh
rm -f /tmp/jns-management-bridge-install.sh

cat > "$ETC_DIR/config.json" <<EOF
{
  "listen_host": "127.0.0.1",
  "listen_port": 8765,
  "command_timeout": 45,
  "max_output_bytes": 300000,
  "max_command_chars": 12000,
  "targets": {
    "node-c": {
      "mode": "local"
    },
    "node-a": {
      "mode": "ssh",
      "destination": "node-a",
      "identity_file": "$HOME_DIR/.ssh/jns_infra_ed25519"
    },
    "node-b": {
      "mode": "ssh",
      "destination": "node-b",
      "identity_file": "$HOME_DIR/.ssh/jns_infra_ed25519"
    }
  }
}
EOF
chown "$MGMT_USER:$MGMT_USER" "$ETC_DIR/config.json"
chmod 0600 "$ETC_DIR/config.json"
systemctl restart jns-management-bridge

cat > "$APP_DIR/enrol_onward_key.sh" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
MGMT_USER="${JNS_MGMT_USER:-jns-mcp}"
HOME_DIR="$(getent passwd "$MGMT_USER" | cut -d: -f6)"
host="${1:-}"
if [[ "$host" != "node-a" && "$host" != "node-b" ]]; then
  echo "Usage: $0 node-a|node-b" >&2
  exit 2
fi
exec ssh-copy-id -i "$HOME_DIR/.ssh/jns_infra_ed25519.pub" "$host"
EOF
chmod 0755 "$APP_DIR/enrol_onward_key.sh"

echo
echo "=== PRIMARY INGRESS READY ==="
echo "Laptop SSH target:"
echo "  $MGMT_USER@$(hostname -I | awk '{print $1}')"
echo
echo "Node C host key fingerprints:"
ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub || true
echo
echo "Node C onward public key (install on Node A/B root accounts):"
cat "$HOME_DIR/.ssh/jns_infra_ed25519.pub"
echo
echo "Bridge health:"
bridge_ok=0
for _ in 1 2 3 4 5 6 7 8 9 10; do
  if curl -fsS http://127.0.0.1:8765/health; then
    bridge_ok=1
    break
  fi
  sleep 0.5
done
if [[ "$bridge_ok" -ne 1 ]]; then
  echo "Bridge failed health check after 5 seconds." >&2
  systemctl --no-pager --full status jns-management-bridge || true
  journalctl -u jns-management-bridge -n 40 --no-pager || true
  exit 1
fi
echo
echo
echo "Proxmox inventory:"
qm list || true
pct list || true
echo
echo "If VM909 exists, this is the retained old HA reference copy:"
qm status 909 2>/dev/null || true
qm config 909 2>/dev/null | sed -n '1,30p' || true
echo
echo "To start the temporary HTTPS bridge for a Work-mode session:"
echo "  sudo $APP_DIR/start_temp_tunnel.sh"
