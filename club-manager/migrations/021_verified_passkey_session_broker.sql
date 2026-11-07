BEGIN;
-- The application verifier MUST validate WebAuthn signature, RP, origin,
-- challenge and user verification using upstream py_webauthn BEFORE calling.
-- This operation is granted only to the isolated NOLOGIN authn role and
-- cannot be invoked through the legacy web application.
CREATE OR REPLACE FUNCTION club.complete_verified_webauthn_login(
 p_account uuid,p_credential_id bytea,p_bearer_sha256 bytea
) RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,club AS $$
DECLARE v_mfa uuid;
        v_api uuid;
BEGIN
 IF p_account IS NULL OR p_credential_id IS NULL OR p_bearer_sha256 IS NULL
   OR octet_length(p_bearer_sha256)<>32
   OR NOT EXISTS (
    SELECT 1 FROM club.officer_webauthn_credentials c
    JOIN club.committee_accounts a ON a.id=c.account_id
    WHERE c.account_id=p_account
      AND c.credential_id=p_credential_id
      AND c.revoked_at IS NULL
      AND a.account_state='active'
   )
 THEN RAISE EXCEPTION 'Verified named-officer credential required'
    USING ERRCODE='42501'; END IF;
 INSERT INTO club.officer_mfa_sessions(
   account_id,method,verified_at,expires_at)
 VALUES(p_account,'webauthn',statement_timestamp(),
        statement_timestamp()+interval '15 minutes')
 RETURNING session_id INTO v_mfa;
 v_api:=club.issue_officer_api_session(p_account,v_mfa,p_bearer_sha256);
 RETURN v_api;
END $$;

CREATE OR REPLACE FUNCTION club.revoke_officer_api_session(
 p_account uuid,p_bearer_sha256 bytea
) RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,club AS $$
DECLARE v_id uuid;
BEGIN
 IF p_account IS NULL OR p_bearer_sha256 IS NULL OR octet_length(p_bearer_sha256)<>32
 THEN RETURN false; END IF;
 UPDATE club.officer_api_sessions s
 SET revoked_at=clock_timestamp()
 WHERE s.account_id=p_account
  AND s.bearer_sha256=p_bearer_sha256
  AND s.revoked_at IS NULL
 RETURNING s.id INTO v_id;
 RETURN v_id IS NOT NULL;
END $$;

REVOKE EXECUTE ON FUNCTION club.complete_verified_webauthn_login(uuid,bytea,bytea)
 FROM PUBLIC,clubmgr,club_api_service,club_authz_service;
REVOKE EXECUTE ON FUNCTION club.revoke_officer_api_session(uuid,bytea)
 FROM PUBLIC,clubmgr,club_api_service,club_authz_service;
GRANT EXECUTE ON FUNCTION club.complete_verified_webauthn_login(uuid,bytea,bytea)
 TO club_authn_service;
GRANT EXECUTE ON FUNCTION club.revoke_officer_api_session(uuid,bytea)
 TO club_authn_service;
COMMIT;
