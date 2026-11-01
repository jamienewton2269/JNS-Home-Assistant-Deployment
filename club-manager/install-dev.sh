#!/bin/sh
set -eu
export DEBIAN_FRONTEND=noninteractive
if [ "$(id -u)" -ne 0 ]; then echo "root required inside development CT"; exit 1; fi
test "$(hostname -s)" = club-manager-dev || { echo "wrong guest"; exit 1; }
echo "Installing Debian distribution packages..."
apt-get update -qq
apt-get install -y --no-install-recommends postgresql postgresql-contrib python3 python3-psycopg2 ca-certificates curl
if ! id clubmgr >/dev/null 2>&1; then
    useradd --system --home-dir /var/lib/jns-club-manager --shell /usr/sbin/nologin clubmgr
fi
install -d -o clubmgr -g clubmgr -m 0700 /var/lib/jns-club-manager
install -d -o root -g clubmgr -m 0750 /etc/jns-club-manager
install -d -o root -g root -m 0755 /opt/jns-club-manager
install -m 0755 /tmp/jns-club-manager-app.py /opt/jns-club-manager/app.py
if [ ! -s /etc/jns-club-manager/admin.secret ]; then
    python3 -c 'import secrets;print(secrets.token_urlsafe(36))' > /etc/jns-club-manager/admin.secret
fi
chown root:clubmgr /etc/jns-club-manager/admin.secret
chmod 0640 /etc/jns-club-manager/admin.secret
systemctl enable --now postgresql
# This database is created once; repeated deployment preserves all events.
if ! runuser -u postgres -- psql -Atqc "SELECT 1 FROM pg_roles WHERE rolname='clubmgr'" | grep -qx 1; then
    runuser -u postgres -- createuser --no-superuser --no-createdb --no-createrole clubmgr
fi
if ! runuser -u postgres -- psql -Atqc "SELECT 1 FROM pg_database WHERE datname='club_manager'" | grep -qx 1; then
    runuser -u postgres -- createdb --owner=postgres club_manager
fi
cat > /tmp/jns-club-manager-schema.sql <<'SQL'
BEGIN;
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE SCHEMA IF NOT EXISTS club AUTHORIZATION postgres;
REVOKE ALL ON SCHEMA club FROM PUBLIC;
REVOKE ALL ON DATABASE club_manager FROM PUBLIC;
GRANT CONNECT ON DATABASE club_manager TO clubmgr;
GRANT USAGE ON SCHEMA club TO clubmgr;

CREATE TABLE IF NOT EXISTS club.event_log (
  seq bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  prev_hash text NOT NULL,
  entry_hash text NOT NULL UNIQUE,
  member_id uuid NOT NULL,
  action text NOT NULL CHECK (action IN ('CREATE','REVISE')),
  payload jsonb NOT NULL,
  actor text NOT NULL,
  recorded_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
REVOKE ALL ON club.event_log FROM PUBLIC;
REVOKE ALL ON club.event_log FROM clubmgr;

CREATE OR REPLACE FUNCTION club.append_member(
  p_id uuid, p_name text, p_email text, p_category text, p_actor text
) RETURNS bigint
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, club
AS $$
DECLARE
  v_seq bigint;
  v_prev text;
  v_action text;
  v_payload jsonb;
  v_digest text;
BEGIN
  IF length(p_name) NOT BETWEEN 1 AND 120 OR length(p_email) NOT BETWEEN 3 AND 200
     OR position('@' in p_email) = 0
     OR p_category NOT IN ('Full','Family','Junior','Social')
     OR p_actor <> 'local-dev-admin' THEN
    RAISE EXCEPTION 'invalid development record';
  END IF;
  PERFORM pg_advisory_xact_lock(7812201);
  IF EXISTS (SELECT 1 FROM club.event_log WHERE member_id=p_id) THEN
    v_action := 'REVISE';
  ELSE
    v_action := 'CREATE';
  END IF;
  SELECT entry_hash INTO v_prev FROM club.event_log ORDER BY seq DESC LIMIT 1;
  v_prev := coalesce(v_prev, repeat('0',64));
  v_payload := jsonb_build_object('name',p_name,'email',p_email,'category',p_category);
  v_seq := nextval(pg_get_serial_sequence('club.event_log', 'seq'));
  v_digest := encode(digest(v_prev || '|' || v_seq::text || '|' || p_id::text || '|' ||
                           v_action || '|' || v_payload::text || '|' || p_actor, 'sha256'),'hex');
  INSERT INTO club.event_log(seq,prev_hash,entry_hash,member_id,action,payload,actor)
  OVERRIDING SYSTEM VALUE VALUES (v_seq,v_prev,v_digest,p_id,v_action,v_payload,p_actor);
  RETURN v_seq;
END $$;
REVOKE ALL ON FUNCTION club.append_member(uuid,text,text,text,text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION club.append_member(uuid,text,text,text,text) TO clubmgr;

CREATE OR REPLACE VIEW club.current_members AS
SELECT DISTINCT ON (member_id)
    member_id, payload->>'name' AS display_name,
    payload->>'email' AS email, payload->>'category' AS category,
    (SELECT count(*) FROM club.event_log n WHERE n.member_id=e.member_id) AS version
FROM club.event_log e ORDER BY member_id,seq DESC;
REVOKE ALL ON club.current_members FROM PUBLIC;
GRANT SELECT ON club.current_members TO clubmgr;

CREATE OR REPLACE FUNCTION club.audit_rows()
RETURNS TABLE(seq bigint,entry_hash text,prev_hash text,member_id uuid,action text,payload text,actor text)
LANGUAGE sql SECURITY DEFINER SET search_path = pg_catalog, club
AS $$ SELECT e.seq,e.entry_hash,e.prev_hash,e.member_id,e.action,e.payload::text,e.actor FROM club.event_log e ORDER BY e.seq $$;
REVOKE ALL ON FUNCTION club.audit_rows() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION club.audit_rows() TO clubmgr;

CREATE OR REPLACE FUNCTION club.prevent_change() RETURNS trigger
LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'immutable history'; END $$;
DROP TRIGGER IF EXISTS lock_history ON club.event_log;
CREATE TRIGGER lock_history BEFORE UPDATE OR DELETE ON club.event_log
FOR EACH ROW
EXECUTE FUNCTION club.prevent_change();
-- NOTE: this development ledger is tamper-evident only, not independently immutable.
COMMIT;
SQL
# The append function requires SECURITY DEFINER privileges; audit table is not writable by the app account.
runuser -u postgres -- psql -v ON_ERROR_STOP=1 -d club_manager -f /tmp/jns-club-manager-schema.sql
# Audit query must use the scoped function rather than direct table access.
python3 - <<'PY'
p="/opt/jns-club-manager/app.py"
s=open(p).read().replace("SELECT seq, entry_hash, prev_hash, member_id, action, payload::text, actor FROM club.event_log ORDER BY seq","SELECT seq, entry_hash, prev_hash, member_id, action, payload, actor FROM club.audit_rows()")
open(p,"w").write(s)
PY
cat > /etc/systemd/system/jns-club-manager-dev.service <<'UNIT'
[Unit]
Description=JNS Club Manager localhost development prototype
After=network.target postgresql.service
Requires=postgresql.service
[Service]
Type=simple
User=clubmgr
Group=clubmgr
WorkingDirectory=/var/lib/jns-club-manager
ExecStart=/usr/bin/python3 /opt/jns-club-manager/app.py
Restart=on-failure
RestartSec=3
NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=strict
ProtectHome=yes
ProtectKernelTunables=yes
ProtectControlGroups=yes
ReadWritePaths=/var/lib/jns-club-manager
CapabilityBoundingSet=
LockPersonality=yes
RestrictSUIDSGID=yes
UMask=0077
[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload
systemctl enable --now jns-club-manager-dev
systemctl restart jns-club-manager-dev
echo "=== WAITING FOR APPLICATION HEALTH CHECK ==="
READY=0
for attempt in 1 2 3 4 5 6 7 8 9 10 11 12; do
    if curl --connect-timeout 2 --max-time 3 --fail --silent http://127.0.0.1:8765/healthz; then
        echo
        READY=1
        break
    fi
    sleep 2
done
if [ "$READY" -ne 1 ]; then
    echo 'ERROR: Club Manager health endpoint unavailable.'
    echo '=== APPLICATION UNIT STATUS ==='
    systemctl status jns-club-manager-dev --no-pager --full || true
    echo '=== APPLICATION JOURNAL ==='
    journalctl -u jns-club-manager-dev --no-pager -n 80 || true
    echo '=== POSTGRESQL STATUS ==='
    systemctl status postgresql --no-pager --full || true
    echo '=== LISTENERS ==='
    ss -lnt || true
    exit 1
fi
echo "=== SERVICE ==="
systemctl --no-pager --full status jns-club-manager-dev | head -n 20
echo "=== LOCAL PORT ==="
ss -ltn | grep '127.0.0.1:8765'
echo "=== DEPLOYMENT SUCCESS ==="
echo "This is a synthetic-data-only prototype. Do not enter real member information."
