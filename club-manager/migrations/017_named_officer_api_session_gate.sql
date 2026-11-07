BEGIN;
-- Named officer sessions: a hash of a 256-bit random bearer secret is stored,
-- never the bearer secret. Session creation remains a trusted-verifier operation.
CREATE TABLE IF NOT EXISTS club.officer_api_sessions (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 account_id uuid NOT NULL REFERENCES club.committee_accounts(id),
 mfa_session_id uuid NOT NULL REFERENCES club.officer_mfa_sessions(session_id),
 bearer_sha256 bytea NOT NULL UNIQUE CHECK(octet_length(bearer_sha256)=32),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 expires_at timestamptz NOT NULL,
 revoked_at timestamptz,
 CHECK(expires_at>created_at),
 CHECK(expires_at<=created_at+interval '15 minutes')
);
CREATE INDEX IF NOT EXISTS officer_api_sessions_account_idx
 ON club.officer_api_sessions(account_id,expires_at);

DO $$ BEGIN
 IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='club_api_service') THEN
  CREATE ROLE club_api_service NOLOGIN;
 END IF;
END $$;
GRANT USAGE ON SCHEMA club TO club_api_service;

-- This function is ONLY granted to the future credential-verification service.
-- Creating an mfa_session_id requires separately verified WebAuthn/TOTP evidence.
CREATE OR REPLACE FUNCTION club.issue_officer_api_session(
 p_account uuid, p_mfa_session uuid, p_bearer_hash bytea
) RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,club AS $$
DECLARE v_id uuid;
BEGIN
 IF p_bearer_hash IS NULL OR octet_length(p_bearer_hash)<>32 THEN
  RAISE EXCEPTION 'Invalid session secret digest';
 END IF;
 IF NOT EXISTS (
  SELECT 1 FROM club.officer_mfa_sessions m
  JOIN club.committee_accounts a ON a.id=m.account_id
  WHERE m.session_id=p_mfa_session AND m.account_id=p_account
    AND a.account_state='active' AND m.revoked_at IS NULL
    AND m.verified_at<=clock_timestamp()
    AND m.verified_at>=clock_timestamp()-interval '15 minutes'
    AND m.expires_at>clock_timestamp()
 ) THEN
  RAISE EXCEPTION 'Verified named-officer MFA required';
 END IF;
 INSERT INTO club.officer_api_sessions(account_id,mfa_session_id,bearer_sha256,expires_at)
 VALUES(p_account,p_mfa_session,p_bearer_hash,
   LEAST(clock_timestamp()+interval '15 minutes',
      (SELECT expires_at FROM club.officer_mfa_sessions WHERE session_id=p_mfa_session)))
 RETURNING id INTO v_id;
 RETURN v_id;
END $$;

CREATE OR REPLACE FUNCTION club.officer_session_authorized(
 p_bearer text,p_permission text
) RETURNS boolean LANGUAGE sql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,club AS $$
 SELECT COALESCE(
  p_bearer IS NOT NULL AND length(p_bearer) BETWEEN 40 AND 256
  AND p_permission IS NOT NULL
  AND EXISTS (
   SELECT 1 FROM club.officer_api_sessions s
   WHERE s.bearer_sha256=public.digest(convert_to(p_bearer,'UTF8'),'sha256')
     AND s.revoked_at IS NULL AND s.expires_at>clock_timestamp()
     AND club.has_privileged_access(s.account_id,p_permission,s.mfa_session_id)
  ), false)
$$;

-- Account suspension / permission revocation / MFA revocation remain effective
-- even with a previously issued session, as evaluated on EVERY API call.
CREATE OR REPLACE FUNCTION club.api_members_for_officer(p_bearer text)
RETURNS jsonb LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,club AS $$
DECLARE v_rows jsonb;
BEGIN
 IF NOT club.officer_session_authorized(p_bearer,'members_view') THEN
   RAISE EXCEPTION 'Access denied' USING ERRCODE='42501';
 END IF;
 SELECT COALESCE(jsonb_agg(to_jsonb(m)), '[]'::jsonb)
 INTO v_rows FROM (
  SELECT member_id,display_name,email,category,version
  FROM club.current_members ORDER BY display_name,member_id LIMIT 100
 ) m;
 RETURN v_rows;
END $$;

CREATE OR REPLACE FUNCTION club.api_dashboard_for_officer(p_bearer text)
RETURNS jsonb LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,club AS $$
BEGIN
 IF NOT club.officer_session_authorized(p_bearer,'members_view') THEN
   RAISE EXCEPTION 'Access denied' USING ERRCODE='42501';
 END IF;
 RETURN club.admin_snapshot();
END $$;

REVOKE ALL ON club.officer_api_sessions FROM PUBLIC,clubmgr,club_api_service,club_authz_service,club_authn_service;
REVOKE EXECUTE ON FUNCTION club.issue_officer_api_session(uuid,uuid,bytea)
 FROM PUBLIC,clubmgr,club_api_service,club_authz_service;
GRANT EXECUTE ON FUNCTION club.issue_officer_api_session(uuid,uuid,bytea)
 TO club_authn_service;
REVOKE EXECUTE ON FUNCTION club.officer_session_authorized(text,text)
 FROM PUBLIC,clubmgr,club_authz_service,club_authn_service;
REVOKE EXECUTE ON FUNCTION club.api_members_for_officer(text)
 FROM PUBLIC,clubmgr,club_authz_service,club_authn_service;
REVOKE EXECUTE ON FUNCTION club.api_dashboard_for_officer(text)
 FROM PUBLIC,clubmgr,club_authz_service,club_authn_service;
GRANT EXECUTE ON FUNCTION club.officer_session_authorized(text,text) TO club_api_service;
GRANT EXECUTE ON FUNCTION club.api_members_for_officer(text) TO club_api_service;
GRANT EXECUTE ON FUNCTION club.api_dashboard_for_officer(text) TO club_api_service;
-- Roles remain NOLOGIN; no HTTP service or user sessions are enabled.
COMMIT;
