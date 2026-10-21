#!/usr/bin/env bash
set -Eeuo pipefail

SRC_ROOT="${1:?path to natural_automation_steward source required}"
CTID=221
CT_NAME=ha-steward
TEMPLATE='local:vztmpl/debian-13-standard_13.6-1_amd64.tar.zst'
BRIDGE_USER='root'
BRIDGE_WRAPPER='/usr/local/sbin/ha-steward-pve-wrapper'
created_ct=0

[[ $EUID -eq 0 ]] || { echo 'Run on Node B as root' >&2; exit 77; }
[[ -f "$SRC_ROOT/lxc/ha-steward-pve-wrapper" ]] || { echo 'source tree incomplete' >&2; exit 66; }

cleanup_failure() {
  rc=$?
  if [[ $rc -ne 0 && $created_ct -eq 1 ]]; then
    echo "STAGE_FAILED rc=$rc; removing newly-created CT$CTID" >&2
    pct stop "$CTID" >/dev/null 2>&1 || true
    pct destroy "$CTID" --purge 1 >/dev/null 2>&1 || true
  fi
  exit "$rc"
}
trap cleanup_failure EXIT

echo '=== install restricted host bridge ==='
install -o root -g root -m 0755 "$SRC_ROOT/lxc/ha-steward-pve-wrapper" "$BRIDGE_WRAPPER"

echo '=== validate wrapper directly ==='
"$BRIDGE_WRAPPER" status
payload="$(python3 -c 'import base64,json; raw=json.dumps(["ha","core","info"],separators=(",",":")).encode(); print(base64.urlsafe_b64encode(raw).decode().rstrip("="))')"
start="$("$BRIDGE_WRAPPER" "guest-exec $payload")"
pid="$(python3 -c 'import json,sys; print(int(json.loads(sys.argv[1])["pid"]))' "$start")"
final=''
for _ in $(seq 1 90); do
  status="$("$BRIDGE_WRAPPER" "guest-exec-status $pid")"
  exited="$(python3 -c 'import json,sys; d=json.loads(sys.argv[1]); print(1 if d.get("exited") else 0)' "$status")"
  if [[ $exited = 1 ]]; then
    final="$status"
    break
  fi
  sleep 1
done
[[ -n $final ]] || { echo 'restricted bridge test timed out' >&2; exit 124; }
python3 -c 'import json,sys; d=json.loads(sys.argv[1]); assert int(d.get("exitcode",-1)) == 0, d; print("RESTRICTED_BRIDGE_READ_TEST_OK")' "$final"
if "$BRIDGE_WRAPPER" 'guest-exec definitely-not-valid' >/dev/null 2>&1; then
  echo 'restricted wrapper accepted forbidden command' >&2
  exit 65
fi

echo '=== create/reuse CT221 ==='
if pct status "$CTID" >/dev/null 2>&1; then
  current_name="$(pct config "$CTID" | awk -F': ' '/^hostname:/{print $2}')"
  [[ $current_name = "$CT_NAME" ]] || { echo "CT$CTID already exists as $current_name" >&2; exit 73; }
else
  pct create "$CTID" "$TEMPLATE" \
    --hostname "$CT_NAME" \
    --ostype debian \
    --cores 1 \
    --memory 1024 \
    --swap 256 \
    --rootfs local-lvm:8 \
    --net0 'name=eth0,bridge=vmbr0,ip=dhcp,ip6=auto,type=veth' \
    --unprivileged 1 \
    --onboot 1
  created_ct=1
fi

pct set "$CTID" --onboot 1 --cores 1 --memory 1024 --swap 256
pct start "$CTID" >/dev/null 2>&1 || true

echo '=== wait for LXC network ==='
have_network=0
for _ in $(seq 1 90); do
  if pct exec "$CTID" -- sh -lc "ip -4 -o addr show dev eth0 | grep -q 'inet '" 2>/dev/null; then
    have_network=1
    break
  fi
  sleep 2
done
[[ $have_network -eq 1 ]] || { echo 'CT221 did not obtain DHCP address' >&2; exit 70; }
pct exec "$CTID" -- sh -lc 'hostname -f 2>/dev/null || hostname; ip -br addr; ip route; cat /etc/resolv.conf'

echo '=== install minimal runtime packages ==='
pct exec "$CTID" -- env DEBIAN_FRONTEND=noninteractive apt-get update
pct exec "$CTID" -- env DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends python3 openssh-client ca-certificates curl

echo '=== install canonical Natural Automation + Steward source ==='
rm -rf /tmp/ha-steward-lxc-source
mkdir -p /tmp/ha-steward-lxc-source
cp -a "$SRC_ROOT" /tmp/ha-steward-lxc-source/natural_automation_steward
tar -C /tmp/ha-steward-lxc-source -czf /tmp/ha-steward-lxc-source.tgz natural_automation_steward
pct push "$CTID" /tmp/ha-steward-lxc-source.tgz /tmp/ha-steward-lxc-source.tgz
pct exec "$CTID" -- sh -lc 'rm -rf /tmp/ha-steward-src; mkdir -p /tmp/ha-steward-src; tar -xzf /tmp/ha-steward-lxc-source.tgz -C /tmp/ha-steward-src'
pct exec "$CTID" -- bash /tmp/ha-steward-src/natural_automation_steward/lxc/install-in-lxc.sh

echo '=== copy live Steward/audit/progress data consistently ==='
DATA_STAGE="$(mktemp -d /tmp/ha-steward-data.XXXXXX)"
cp -a /opt/natural-automation/data/. "$DATA_STAGE/"
rm -f "$DATA_STAGE/steward.db" "$DATA_STAGE/steward.db-wal" "$DATA_STAGE/steward.db-shm"
python3 - "$DATA_STAGE/steward.db" <<'PY'
import sqlite3,sys
src=sqlite3.connect('/opt/natural-automation/data/steward.db')
dst=sqlite3.connect(sys.argv[1])
src.backup(dst)
dst.close(); src.close()
PY
tar -C "$DATA_STAGE" -czf /tmp/ha-steward-data.tgz .
pct push "$CTID" /tmp/ha-steward-data.tgz /tmp/ha-steward-data.tgz
pct exec "$CTID" -- sh -lc 'rm -rf /opt/natural-automation/data/*; tar -xzf /tmp/ha-steward-data.tgz -C /opt/natural-automation/data; chown -R natural-automation:natural-automation /opt/natural-automation/data'
rm -rf "$DATA_STAGE"

echo '=== generate LXC-only bridge key ==='
pct exec "$CTID" -- sh -lc 'rm -f /etc/natural-automation/pve-bridge.key /etc/natural-automation/pve-bridge.key.pub; ssh-keygen -q -t ed25519 -N "" -C ha-steward-ct221 -f /etc/natural-automation/pve-bridge.key; chown natural-automation:natural-automation /etc/natural-automation/pve-bridge.key /etc/natural-automation/pve-bridge.key.pub; chmod 0600 /etc/natural-automation/pve-bridge.key; chmod 0644 /etc/natural-automation/pve-bridge.key.pub'
PUBKEY="$(pct exec "$CTID" -- cat /etc/natural-automation/pve-bridge.key.pub | tr -d '\r\n')"
[[ $PUBKEY == ssh-ed25519\ *\ ha-steward-ct221 ]] || { echo 'unexpected bridge public key' >&2; exit 65; }

echo '=== install forced-command bridge key on Node B ==='
install -d -o root -g root -m 0700 /root/.ssh
AUTH=/root/.ssh/authorized_keys
touch "$AUTH"
AUTH_TMP="$(mktemp /root/.ssh/authorized_keys.XXXXXX)"
grep -v 'ha-steward-ct221$' "$AUTH" > "$AUTH_TMP" || true
printf '%s %s\n' 'from="10.10.0.0/16",restrict,command="/usr/local/sbin/ha-steward-pve-wrapper"' "$PUBKEY" >> "$AUTH_TMP"
cat "$AUTH_TMP" > "$AUTH"
rm -f "$AUTH_TMP"
grep -q 'ha-steward-ct221
echo '=== resolve Node B by DNS from CT221 ==='
BRIDGE_HOST=''
for candidate in nodeb.jnsystems.xyz nodeb.home.arpa; do
  if pct exec "$CTID" -- getent ahosts "$candidate" >/dev/null 2>&1; then
    BRIDGE_HOST="$candidate"
    break
  fi
done
[[ -n $BRIDGE_HOST ]] || { echo 'No DNS name for Node B resolves from CT221; refusing IP-config fallback' >&2; exit 68; }
echo "bridge_dns=$BRIDGE_HOST"

echo '=== pin Node B SSH host key ==='
pct exec "$CTID" -- sh -lc "ssh-keyscan -T 5 -H '$BRIDGE_HOST' 2>/dev/null > /etc/natural-automation/known_hosts; test -s /etc/natural-automation/known_hosts; chown root:natural-automation /etc/natural-automation/known_hosts; chmod 0640 /etc/natural-automation/known_hosts"

echo '=== verify restricted SSH bridge from LXC ==='
pct exec "$CTID" -- runuser -u natural-automation -- ssh \
  -o BatchMode=yes \
  -o StrictHostKeyChecking=yes \
  -o UserKnownHostsFile=/etc/natural-automation/known_hosts \
  -o IdentitiesOnly=yes \
  -i /etc/natural-automation/pve-bridge.key \
  "$BRIDGE_USER@$BRIDGE_HOST" status

echo '=== configure read-only staged service ==='
ENV_TMP="$(mktemp /tmp/ha-steward-env.XXXXXX)"
printf 'NA_PVE_BRIDGE_HOST=%s\nNA_ENABLE_APPLY=0\n' "$BRIDGE_HOST" > "$ENV_TMP"
pct push "$CTID" "$ENV_TMP" /etc/natural-automation/environment
rm -f "$ENV_TMP"
pct exec "$CTID" -- chown root:natural-automation /etc/natural-automation/environment
pct exec "$CTID" -- chmod 0640 /etc/natural-automation/environment
pct exec "$CTID" -- systemctl restart natural-automation.service

echo '=== staged service acceptance ==='
healthy=0
for _ in $(seq 1 45); do
  if pct exec "$CTID" -- curl -fsS --max-time 10 http://127.0.0.1:8099/api/status > /tmp/ha-steward-ct-status.json 2>/dev/null; then
    healthy=1
    break
  fi
  sleep 2
done
[[ $healthy -eq 1 ]] || { pct exec "$CTID" -- journalctl -u natural-automation -n 100 --no-pager || true; exit 71; }
cat /tmp/ha-steward-ct-status.json
python3 - /tmp/ha-steward-ct-status.json <<'PY'
import json,sys
d=json.load(open(sys.argv[1]))
assert d['ok'] is True, d
assert d['apply_enabled'] is False, d
assert d['target']['role']=='ha-general', d
assert d['target']['name'] in {'ha-s2-general','ha-general'}, d
assert d['target']['transport']=='restricted_ssh_bridge', d
assert d['entities'] > 0, d
print('STAGED_STATUS_OK',d['target'],d['entities'])
PY

pct exec "$CTID" -- curl -fsS -X POST -H 'Content-Type: application/json' -d '{}' http://127.0.0.1:8099/api/steward/status > /tmp/ha-steward-ct-steward.json
cat /tmp/ha-steward-ct-steward.json
python3 - /tmp/ha-steward-ct-steward.json <<'PY'
import json,sys
d=json.load(open(sys.argv[1]))
assert d['repairs'] >= 17, d
assert d['apply_enabled'] is False, d
print('STAGED_KNOWLEDGE_OK repairs=',d['repairs'])
PY

echo '=== staged analyse/progress smoke test ==='
start="$(pct exec "$CTID" -- curl -fsS -X POST -H 'Content-Type: application/json' -d '{"text":"turn on the kitchen worktop light at 16:35 for 5 mins"}' http://127.0.0.1:8099/api/analyse-start)"
job="$(python3 -c 'import json,sys; print(json.loads(sys.argv[1])["job_id"])' "$start")"
done_job=''
for _ in $(seq 1 80); do
  out="$(pct exec "$CTID" -- curl -fsS "http://127.0.0.1:8099/api/job?id=$job")"
  state="$(python3 -c 'import json,sys; print(json.loads(sys.argv[1]).get("status",""))' "$out")"
  if [[ $state == done || $state == error ]]; then
    done_job="$out"
    break
  fi
  sleep 1
done
[[ -n $done_job ]] || { echo 'analysis job timed out' >&2; exit 124; }
python3 - "$done_job" <<'PY'
import json,sys
d=json.loads(sys.argv[1])
assert d['status']=='done', d
r=d.get('result') or {}
assert r.get('apply_enabled') is False, r
print('STAGED_ANALYSE_OK action=',r.get('action'),'target=',(r.get('target') or {}).get('entity_id'))
PY

CT_IPV4="$(pct exec "$CTID" -- hostname -I | awk '{print $1}')"
echo "ctid=$CTID"
echo "ct_name=$CT_NAME"
echo "ct_ipv4=$CT_IPV4"
echo "bridge_dns=$BRIDGE_HOST"
echo 'HA_STEWARD_LXC_STAGE_OK'

trap - EXIT
 "$AUTH" || { echo 'forced-command key was not installed' >&2; exit 65; }

echo '=== resolve Node B by DNS from CT221 ==='
BRIDGE_HOST=''
for candidate in nodeb.jnsystems.xyz nodeb.home.arpa; do
  if pct exec "$CTID" -- getent ahosts "$candidate" >/dev/null 2>&1; then
    BRIDGE_HOST="$candidate"
    break
  fi
done
[[ -n $BRIDGE_HOST ]] || { echo 'No DNS name for Node B resolves from CT221; refusing IP-config fallback' >&2; exit 68; }
echo "bridge_dns=$BRIDGE_HOST"

echo '=== pin Node B SSH host key ==='
pct exec "$CTID" -- sh -lc "ssh-keyscan -T 5 -H '$BRIDGE_HOST' 2>/dev/null > /etc/natural-automation/known_hosts; test -s /etc/natural-automation/known_hosts; chown root:natural-automation /etc/natural-automation/known_hosts; chmod 0640 /etc/natural-automation/known_hosts"

echo '=== verify restricted SSH bridge from LXC ==='
pct exec "$CTID" -- runuser -u natural-automation -- ssh \
  -o BatchMode=yes \
  -o StrictHostKeyChecking=yes \
  -o UserKnownHostsFile=/etc/natural-automation/known_hosts \
  -o IdentitiesOnly=yes \
  -i /etc/natural-automation/pve-bridge.key \
  "$BRIDGE_USER@$BRIDGE_HOST" status

echo '=== configure read-only staged service ==='
ENV_TMP="$(mktemp /tmp/ha-steward-env.XXXXXX)"
printf 'NA_PVE_BRIDGE_HOST=%s\nNA_ENABLE_APPLY=0\n' "$BRIDGE_HOST" > "$ENV_TMP"
pct push "$CTID" "$ENV_TMP" /etc/natural-automation/environment
rm -f "$ENV_TMP"
pct exec "$CTID" -- chown root:natural-automation /etc/natural-automation/environment
pct exec "$CTID" -- chmod 0640 /etc/natural-automation/environment
pct exec "$CTID" -- systemctl restart natural-automation.service

echo '=== staged service acceptance ==='
healthy=0
for _ in $(seq 1 45); do
  if pct exec "$CTID" -- curl -fsS --max-time 10 http://127.0.0.1:8099/api/status > /tmp/ha-steward-ct-status.json 2>/dev/null; then
    healthy=1
    break
  fi
  sleep 2
done
[[ $healthy -eq 1 ]] || { pct exec "$CTID" -- journalctl -u natural-automation -n 100 --no-pager || true; exit 71; }
cat /tmp/ha-steward-ct-status.json
python3 - /tmp/ha-steward-ct-status.json <<'PY'
import json,sys
d=json.load(open(sys.argv[1]))
assert d['ok'] is True, d
assert d['apply_enabled'] is False, d
assert d['target']['role']=='ha-general', d
assert d['target']['name'] in {'ha-s2-general','ha-general'}, d
assert d['target']['transport']=='restricted_ssh_bridge', d
assert d['entities'] > 0, d
print('STAGED_STATUS_OK',d['target'],d['entities'])
PY

pct exec "$CTID" -- curl -fsS -X POST -H 'Content-Type: application/json' -d '{}' http://127.0.0.1:8099/api/steward/status > /tmp/ha-steward-ct-steward.json
cat /tmp/ha-steward-ct-steward.json
python3 - /tmp/ha-steward-ct-steward.json <<'PY'
import json,sys
d=json.load(open(sys.argv[1]))
assert d['repairs'] >= 17, d
assert d['apply_enabled'] is False, d
print('STAGED_KNOWLEDGE_OK repairs=',d['repairs'])
PY

echo '=== staged analyse/progress smoke test ==='
start="$(pct exec "$CTID" -- curl -fsS -X POST -H 'Content-Type: application/json' -d '{"text":"turn on the kitchen worktop light at 16:35 for 5 mins"}' http://127.0.0.1:8099/api/analyse-start)"
job="$(python3 -c 'import json,sys; print(json.loads(sys.argv[1])["job_id"])' "$start")"
done_job=''
for _ in $(seq 1 80); do
  out="$(pct exec "$CTID" -- curl -fsS "http://127.0.0.1:8099/api/job?id=$job")"
  state="$(python3 -c 'import json,sys; print(json.loads(sys.argv[1]).get("status",""))' "$out")"
  if [[ $state == done || $state == error ]]; then
    done_job="$out"
    break
  fi
  sleep 1
done
[[ -n $done_job ]] || { echo 'analysis job timed out' >&2; exit 124; }
python3 - "$done_job" <<'PY'
import json,sys
d=json.loads(sys.argv[1])
assert d['status']=='done', d
r=d.get('result') or {}
assert r.get('apply_enabled') is False, r
print('STAGED_ANALYSE_OK action=',r.get('action'),'target=',(r.get('target') or {}).get('entity_id'))
PY

CT_IPV4="$(pct exec "$CTID" -- hostname -I | awk '{print $1}')"
echo "ctid=$CTID"
echo "ct_name=$CT_NAME"
echo "ct_ipv4=$CT_IPV4"
echo "bridge_dns=$BRIDGE_HOST"
echo 'HA_STEWARD_LXC_STAGE_OK'

trap - EXIT
