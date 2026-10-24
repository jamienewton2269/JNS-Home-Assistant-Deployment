#!/usr/bin/env bash
# JNS Solar: root-only one-time Node C Steward staging promotion.
# Installs an INERT, loopback-only, no-apply Steward shadow. Does not
# touch Node B live service or HA; does not activate a duplicate controller.
# Invoke only from an authorised Node C root shell after reviewing script.
set -Eeuo pipefail
umask 077
[[ "$(id -u)" == 0 && "$(hostname -s)" == nodec ]] || { echo 'BLOCKED wrong host or uid'; exit 77; }
command -v python3 >/dev/null && command -v systemctl >/dev/null || exit 69

SHA='517a78dc7ccfc3547181626b59c67fbddbd8a9155bf37d91d203a5c9042ec3e4'
USER_HOME="$(getent passwd github-runner | cut -d: -f6)"
[[ -n "$USER_HOME" && "$USER_HOME" == /* ]] || { echo 'BLOCKED runner location'; exit 65; }
ZIP="$USER_HOME/.local/share/jns-solar/steward/migration-stage/nodeb-steward-staged-517a78dc7ccfc354.zip"
[[ -f "$ZIP" && ! -L "$ZIP" ]] || { echo 'BLOCKED pinned archive absent'; exit 66; }
echo "$SHA  $ZIP" | sha256sum -c - >/dev/null || { echo 'BLOCKED archive checksum'; exit 65; }

SERVICE=/etc/systemd/system/jns-steward-shadow.service
[[ ! -e "$SERVICE" && ! -e /opt/natural-automation && ! -e /opt/real-progress ]] || {
  echo 'BLOCKED existing destination or service; no overwrite'; exit 73;
}
[[ -d /var/lib/jns-steward && ! -L /var/lib/jns-steward ]] || { echo 'BLOCKED root steward store'; exit 73; }
test "$(df -Pk /opt | awk 'NR==2{print $4}')" -ge 1048576 || {
  echo 'BLOCKED insufficient free space'; exit 75;
}
install -d -o root -g root -m 0700 /opt/jns-steward-shadow-stage
TEMP="$(mktemp -d /opt/jns-steward-shadow-stage/incoming.XXXXXXXX)"
trap 'test -z "$TEMP" || rm -rf -- "$TEMP"' EXIT

python3 - "$ZIP" "$TEMP" <<'PY'
import os,pathlib,sys,zipfile
src=pathlib.Path(sys.argv[1])
target=pathlib.Path(sys.argv[2])
allowed=("application/","real-progress/","systemd/")
with zipfile.ZipFile(src) as z:
 files=z.infolist()
 if not files or len(files)>160:raise SystemExit("BLOCKED invalid item count")
 for i in files:
  p=pathlib.PurePosixPath(i.filename)
  if i.is_dir() or p.is_absolute() or ".." in p.parts:raise SystemExit("BLOCKED unsafe item")
  if not i.filename.startswith(allowed):raise SystemExit("BLOCKED invalid archive entry")
  if ((i.external_attr>>16)&0o170000)==0o120000:raise SystemExit("BLOCKED symlink")
  if i.file_size>8*1024*1024:raise SystemExit("BLOCKED oversize file")
  destination=target/pathlib.Path(*p.parts)
  destination.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
  destination.write_bytes(z.read(i))
  os.chmod(destination,0o600)
for check in ("application/natural_automation.py","application/data/steward.db",
              "real-progress/real_progress.py"):
 if not (target/check).is_file():raise SystemExit("BLOCKED missing required files")
PY
python3 - "$TEMP/application/data/steward.db" <<'PY'
import sqlite3,sys
c=sqlite3.connect("file:"+sys.argv[1]+"?mode=ro",uri=True)
assert c.execute("pragma quick_check(1)").fetchone()[0]=="ok"
assert c.execute("select count(*) from sqlite_master").fetchone()[0]>=5
c.close()
PY
if ! id -u jns-steward >/dev/null 2>&1; then
  useradd --system --user-group --home-dir /nonexistent --no-create-home --shell /usr/sbin/nologin jns-steward
fi
mv "$TEMP/application" /opt/natural-automation
mv "$TEMP/real-progress" /opt/real-progress
chown -R root:root /opt/natural-automation /opt/real-progress
find /opt/natural-automation /opt/real-progress -type d -exec chmod 0755 '{}' +
find /opt/natural-automation /opt/real-progress -type f -exec chmod 0644 '{}' +
chown -R jns-steward:jns-steward /opt/natural-automation/data
chmod -R go-rwx /opt/natural-automation/data

cat > "$SERVICE" <<'UNIT'
[Unit]
Description=JNS Steward Solar Shadow (Node C, apply disabled)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=jns-steward
Group=jns-steward
WorkingDirectory=/opt/natural-automation
Environment=NA_BIND=127.0.0.1
Environment=NA_PORT=18109
Environment=NA_ENABLE_APPLY=0
Environment=NA_TARGET_ROLE=ha-general
Environment=NA_TARGET_NAMES=ha-s2-general,ha-general
Environment=NA_PROXMOX_HOSTS=nodea.home.arpa,nodeb.home.arpa
ExecStart=/usr/bin/python3 /opt/natural-automation/natural_automation.py
Restart=on-failure
RestartSec=5
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=full
ProtectHome=true
ReadWritePaths=/opt/natural-automation/data

[Install]
WantedBy=multi-user.target
UNIT
chmod 0644 "$SERVICE"
systemctl daemon-reload
systemctl start jns-steward-shadow.service
for n in 1 2 3 4 5 6 7 8 9 10; do
  if curl -fsS -o /dev/null --connect-timeout 2 --max-time 3 http://127.0.0.1:18109/; then
    echo 'JNS_NODEC_STEWARD_SHADOW_INSTALLED_OK'
    break
  fi
  if [[ "$n" == 10 ]]; then
    echo 'BLOCKED shadow HTTP check; stopped service, evidence retained'
    systemctl stop jns-steward-shadow.service || true
    exit 70
  fi
  sleep 1
done
test "$(systemctl is-active jns-steward-shadow.service)" = active
test "$(systemctl is-enabled jns-steward-shadow.service || true)" != enabled
# Root-side protection for prior HA900 inventory and retirement register.
HA900_SOURCE="$USER_HOME/.local/share/jns-solar/ha900/evidence"
MANIFEST="$HA900_SOURCE/vm900-services-77555d0defa1574c.json"
REGISTER="$HA900_SOURCE/HA900_SERVICE_RETIREMENT_REGISTER_PRIVATE.md"
if [[ -f "$MANIFEST" && -f "$REGISTER" && ! -L "$MANIFEST" && ! -L "$REGISTER" ]]; then
  printf '%s  %s\n' \
    77555d0defa1574c7e4d22e63130a42e8958766264b713b2e9f361524a221e82 "$MANIFEST" \
    71bac555d65ac726394ba89b89d4a1ff61e254182681799784497d8e4c068ec0 "$REGISTER" |
    sha256sum -c - >/dev/null
  install -d -o root -g root -m 0700 /var/lib/jns-steward/ha900/evidence
  install -o root -g root -m 0600 "$MANIFEST" /var/lib/jns-steward/ha900/evidence/
  install -o root -g root -m 0600 "$REGISTER" /var/lib/jns-steward/ha900/evidence/
  echo 'JNS_HA900_MANIFEST_IMPORTED_TO_ROOT_STORE=yes'
fi
echo 'NODEC_ONLY_LOOPBACK_LISTENER=yes'
echo 'AUTOMATION_APPLY_DISABLED=yes'
echo 'NODEC_SHADOW_AUTOSTART_DISABLED=yes'
echo 'NODEB_LIVE_UNCHANGED=yes'
echo 'REMAINING_CUTOVER_WORK=final_database_sync,restricted_ha_general_transport,acceptance_tests'
