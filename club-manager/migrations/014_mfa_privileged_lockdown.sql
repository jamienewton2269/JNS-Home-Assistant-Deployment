BEGIN;
-- Privileged access assurance: a role label never substitutes for named identity,
-- an explicit permission grant and a recently verified second factor.
CREATE TABLE IF NOT EXISTS club.officer_mfa_sessions (
 session_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 account_id uuid NOT NULL REFERENCES club.committee_accounts(id),
 method text NOT NULL CHECK (method IN ('totp','webauthn')),
 verified_at timestamptz NOT NULL,
 expires_at timestamptz NOT NULL,
 revoked_at timestamptz,
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 CHECK(expires_at>verified_at),
 CHECK(expires_at<=verified_at+interval '15 minutes'),
 CHECK(revoked_at IS NULL OR revoked_at>=created_at)
);
CREATE INDEX IF NOT EXISTS officer_mfa_account_idx ON club.officer_mfa_sessions(account_id,expires_at);
CREATE OR REPLACE FUNCTION club.has_privileged_access(
 p_account uuid,p_permission text,p_mfa_session uuid
) RETURNS boolean LANGUAGE sql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,club AS $$
 SELECT COALESCE(
   club.committee_has_permission(p_account,p_permission)
   AND EXISTS(
    SELECT 1 FROM club.officer_mfa_sessions s
    WHERE s.session_id=p_mfa_session
      AND s.account_id=p_account
      AND s.revoked_at IS NULL
      AND s.method IN ('totp','webauthn')
      AND s.verified_at<=clock_timestamp()
      AND s.verified_at>=clock_timestamp()-interval '15 minutes'
      AND s.expires_at>clock_timestamp()
   ),false)
$$;
REVOKE ALL ON club.officer_mfa_sessions FROM PUBLIC,clubmgr,club_authz_service;
REVOKE EXECUTE ON FUNCTION club.has_privileged_access(uuid,text,uuid) FROM PUBLIC,clubmgr,club_authz_service;
-- Current shared-password prototype cannot securely assert a named MFA identity.
-- Disable all earlier app entry points, including sensitive read functions.
REVOKE EXECUTE ON FUNCTION club.append_member(uuid,text,text,text,text) FROM clubmgr;
REVOKE EXECUTE ON FUNCTION club.create_disabled_committee_account(text,text,text) FROM clubmgr;
REVOKE EXECUTE ON FUNCTION club.list_committee_accounts() FROM clubmgr;
REVOKE EXECUTE ON FUNCTION club.admin_snapshot() FROM clubmgr;
REVOKE EXECUTE ON FUNCTION club.audit_rows() FROM clubmgr;
REVOKE SELECT ON club.current_members FROM clubmgr;
-- Do not grant MFA session creation, verification or privileged access to the
-- development role: future credential-bound authentication service is required.
COMMIT;
