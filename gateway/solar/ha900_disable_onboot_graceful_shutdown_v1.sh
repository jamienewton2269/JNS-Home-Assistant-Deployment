#!/usr/bin/env bash
# User authorised immediate VM900 retirement on Node A.
# Scope: HA900 ONLY. Safe orderly shutdown with no disk deletion or migration.
set -Eeuo pipefail
umask 077
[[ "$(id -u)" == 0 && "$(hostname -s)" == nodea ]] || { echo 'HA900_BLOCKED_wrong_host'; exit 77; }
command -v qm >/dev/null || { echo 'HA900_BLOCKED_no_qm'; exit 69; }
[[ -f /etc/pve/qemu-server/900.conf ]] || { echo 'HA900_BLOCKED_no_vm_config'; exit 66; }
name="$(qm config 900 | sed -n 's/^name: //p')"
case "$name" in
  homeassistant-recovery|homeassistant*recovery*|homeassistant*legacy*|homeassistant*900*) ;;
  *) echo "HA900_BLOCKED_name_mismatch"; exit 73 ;;
esac
echo "HA900_VERIFIED_SOURCE_NODE=nodea"
echo "HA900_VM_CONFIG_PRESENT=yes"
before="$(qm status 900)"
echo "HA900_BEFORE=$before"
# First prevent unattended resurrection after Node A reboots.
qm set 900 --onboot 0 >/dev/null
[[ "$(qm config 900 | sed -n 's/^onboot: //p')" == 0 ]] || {
  echo 'HA900_BLOCKED_onboot_did_not_disable'; exit 74;
}
echo "HA900_AUTOSTART_DISABLED=yes"
if [[ "$before" == 'status: running' ]]; then
  echo "HA900_GRACEFUL_SHUTDOWN_REQUESTED=yes"
  # ACPI/guest-agent shutdown, no force stop. Report block if not responsive.
  if ! timeout 215 qm shutdown 900 --timeout 180 >/dev/null 2>&1; then
    echo "HA900_SHUTDOWN_COMMAND_FAILED=yes"
  fi
fi
for _ in $(seq 1 18); do
  after="$(qm status 900)"
  [[ "$after" == 'status: stopped' ]] && break
  sleep 2
done
echo "HA900_AFTER=$after"
if [[ "$after" != 'status: stopped' ]]; then
  echo 'HA900_GRACEFUL_SHUTDOWN_INCOMPLETE=manual_escalation_required'
  exit 75
fi
test -f /etc/pve/qemu-server/900.conf
[[ "$(qm config 900 | sed -n 's/^onboot: //p')" == 0 ]]
echo "HA900_VM_STOPPED_VERIFIED=yes"
echo "HA900_AUTOSTART_DISABLED_VERIFIED=yes"
echo "HA900_DISKS_UNCHANGED=yes"
echo "HA900_COLD_REFERENCE_TRANSFER_PENDING=yes"
