BEGIN;
-- Separate local peer-authenticated role for the new private beta service.
-- No password, no remote listening, no grants to legacy clubmgr.
DO $$ BEGIN
 IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='clubbeta') THEN
   CREATE ROLE clubbeta LOGIN INHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE
    NOREPLICATION NOBYPASSRLS;
 END IF;
END $$;
GRANT CONNECT ON DATABASE club_manager TO clubbeta;
GRANT USAGE ON SCHEMA club TO clubbeta;
GRANT club_authn_service, club_api_service TO clubbeta;

-- A logout browser request knows its own high-entropy session token but not
-- the officer's UUID. Revoke exactly that token and its MFA assertion.
CREATE OR REPLACE FUNCTION club.revoke_verified_beta_token(
 p_token_sha256 bytea
) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,club AS $$
DECLARE v_mfa uuid; v_id uuid;
BEGIN
 IF p_token_sha256 IS NULL OR octet_length(p_token_sha256)<>32 THEN RETURN false; END IF;
 UPDATE club.officer_api_sessions
 SET revoked_at=clock_timestamp()
 WHERE bearer_sha256=p_token_sha256 AND revoked_at IS NULL
 RETURNING id,mfa_session_id INTO v_id,v_mfa;
 IF v_id IS NULL THEN RETURN false; END IF;
 UPDATE club.officer_mfa_sessions SET revoked_at=clock_timestamp()
 WHERE session_id=v_mfa AND revoked_at IS NULL;
 RETURN true;
END $$;
REVOKE EXECUTE ON FUNCTION club.revoke_verified_beta_token(bytea)
 FROM PUBLIC,clubmgr,club_api_service,club_authz_service;
GRANT EXECUTE ON FUNCTION club.revoke_verified_beta_token(bytea)
 TO club_authn_service;
COMMIT;
