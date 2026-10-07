#!/usr/bin/env bash
set -Eeuo pipefail
echo "runner_user=$(id -un)"
echo "sudo_rule:"
sudo -n -l
echo "wrapper_metadata:"
if [[ -e /usr/local/sbin/jns-netmon-deploy ]]; then
  stat -c 'mode=%a owner=%U:%G executable=%A' /usr/local/sbin/jns-netmon-deploy
  sha256sum /usr/local/sbin/jns-netmon-deploy
else
  echo "wrapper_missing"
fi
echo "runner_workspace_script_candidates:"
for f in /opt/jns-netmon-release/jns-netmon-web-repair-v0.3.28.sh /opt/jns-netmon-deploy/jns-netmon-web-repair-v0.3.28.sh /usr/local/lib/jns-netmon/deploy.sh /usr/local/sbin/jns-netmon-deploy; do
  [[ -e "$f" ]] && stat -c '%n mode=%a owner=%U:%G readable=%A' "$f"
done
