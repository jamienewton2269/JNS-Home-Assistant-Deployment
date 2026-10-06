#!/usr/bin/env bash
set -Eeuo pipefail

echo "=== CONTROLLED HA902 PROMOTION TEST ==="
date -Is

rollback() {
  set +e
  echo
  echo "=== ROLLBACK / RESTORE PRIMARY ==="
  ssh nodea 'if qm status 902 2>/dev/null | grep -q "^status: running$"; then qm shutdown 902 --timeout 90 || qm stop 902; fi; cfg=$(qm config 902 | sed -n "s/^net0: //p"); cfg=$(sed -E "s/,link_down=[01]//g" <<<"$cfg"); qm set 902 --net0 "$cfg,link_down=1" >/dev/null; qm set 902 --onboot 0 >/dev/null; qm status 902; qm config 902 | grep -E "^(net0|onboot):"'
  ssh nodeb 'if qm status 902 2>/dev/null | grep -q "^status: stopped$"; then qm start 902; fi; for i in $(seq 1 40); do qm guest cmd 902 ping >/dev/null 2>&1 && break; sleep 3; done; qm status 902; qm guest cmd 902 network-get-interfaces 2>/dev/null | grep -A8 -B3 "10.10.10.220" || true; systemctl enable --now jns-ha-replication.timer >/dev/null'
  echo "ROLLBACK_COMPLETE $(date -Is)"
}
trap rollback EXIT

echo "--- Freeze scheduled replication and force final incremental ---"
ssh nodeb 'systemctl disable --now jns-ha-replication.timer >/dev/null; while systemctl is-active --quiet jns-ha-replication.service; do sleep 2; done; systemctl start jns-ha-replication.service; for i in $(seq 1 120); do state=$(systemctl is-active jns-ha-replication.service || true); [ "$state" = inactive ] && break; [ "$state" = failed ] && exit 1; sleep 2; done; systemctl is-failed --quiet jns-ha-replication.service && exit 1 || true; echo FINAL_SYNC; cat /var/lib/jns-ha-replication/last-success; cat /var/lib/jns-ha-replication/last-success-time'

echo "--- Verify target remains fenced before source shutdown ---"
ssh nodea 'qm status 902 | grep -q "^status: stopped$"; qm config 902 | grep -Eq "^net0: .*link_down=1"; qm config 902 | grep -q "^onboot: 0$"; echo TARGET_FENCE_OK'

echo "--- Stop Node B primary ---"
ssh nodeb 'qm shutdown 902 --timeout 90 || qm stop 902; for i in $(seq 1 30); do qm status 902 | grep -q "^status: stopped$" && break; sleep 2; done; qm status 902 | grep -q "^status: stopped$"; echo SOURCE_STOPPED'

echo "--- Promote Node A standby ---"
ssh nodea 'cfg=$(qm config 902 | sed -n "s/^net0: //p"); cfg=$(sed -E "s/,link_down=[01]//g" <<<"$cfg"); qm set 902 --net0 "$cfg" >/dev/null; qm start 902; for i in $(seq 1 50); do qm guest cmd 902 ping >/dev/null 2>&1 && break; sleep 3; done; qm guest cmd 902 ping >/dev/null; echo TARGET_QGA_READY; qm guest cmd 902 network-get-interfaces'

echo "--- Validate promoted HA service ---"
for i in $(seq 1 40); do
  code=$(curl -m 3 -s -o /dev/null -w '%{http_code}' http://10.10.10.220:8123/ || true)
  echo "HTTP_CHECK_$i=$code"
  case "$code" in 200|301|302|401|403) break;; esac
  sleep 3
done
case "$code" in 200|301|302|401|403) ;; *) echo "HA HTTP validation failed: $code" >&2; exit 1;; esac
ssh nodea 'qm guest exec 902 -- /bin/bash -lc "ha core info 2>/dev/null | head -40"'
echo "PROMOTION_TEST_PASS $(date -Is) http=$code"

echo "--- Controlled rollback to Node B ---"
trap - EXIT
rollback

echo "--- Post-rollback service validation ---"
for i in $(seq 1 40); do
  code2=$(curl -m 3 -s -o /dev/null -w '%{http_code}' http://10.10.10.220:8123/ || true)
  echo "PRIMARY_HTTP_CHECK_$i=$code2"
  case "$code2" in 200|301|302|401|403) break;; esac
  sleep 3
done
case "$code2" in 200|301|302|401|403) ;; *) echo "Primary restore HTTP validation failed: $code2" >&2; exit 1;; esac
echo "CONTROLLED_PROMOTION_AND_ROLLBACK=PASS $(date -Is)"
