BEGIN;
-- The challenge is a freshly generated public nonce (not a password/secret).
-- Store it for verification, tightly scoped to its officer and 5-minute expiry.
ALTER TABLE club.officer_webauthn_challenges
 ADD COLUMN IF NOT EXISTS challenge_bytes bytea;
DO $ BEGIN
 IF NOT EXISTS(SELECT 1 FROM pg_constraint WHERE conname='challenge_bytes_length'
   AND conrelid='club.officer_webauthn_challenges'::regclass) THEN
  ALTER TABLE club.officer_webauthn_challenges ADD CONSTRAINT challenge_bytes_length
   CHECK(challenge_bytes IS NULL OR octet_length(challenge_bytes) BETWEEN 32 AND 128);
 END IF;
END $;

CREATE OR REPLACE FUNCTION club.start_webauthn_challenge(
 p_account uuid, p_purpose text, p_nonce bytea)
RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,club AS $$
DECLARE v_id uuid;
BEGIN
 IF p_account IS NULL OR p_purpose NOT IN ('register','authenticate')
   OR (p_purpose='register' AND NOT club.can_enrol_officer_webauthn(p_account))
   OR p_nonce IS NULL OR octet_length(p_nonce) < 32 OR octet_length(p_nonce) > 128
   OR NOT EXISTS (SELECT 1 FROM club.committee_accounts a WHERE a.id=p_account AND a.account_state='active')
 THEN RAISE EXCEPTION 'WebAuthn ceremony unavailable' USING ERRCODE='42501'; END IF;
 -- For registration, the verifier must additionally enforce independent
 -- enrolment approval BEFORE calling this function. DB does not grant it.
 INSERT INTO club.officer_webauthn_challenges
  (account_id,ceremony,challenge_sha256,challenge_bytes,expires_at)
 VALUES(p_account,p_purpose,public.digest(p_nonce,'sha256'),p_nonce,clock_timestamp()+interval '5 minutes')
 RETURNING challenge_id INTO v_id;
 RETURN v_id;
END $$;

CREATE OR REPLACE FUNCTION club.claim_webauthn_challenge(
 p_id uuid,p_account uuid,p_purpose text)
RETURNS bytea LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,club AS $$
DECLARE v_nonce bytea;
BEGIN
 IF p_id IS NULL OR p_account IS NULL OR p_purpose NOT IN ('register','authenticate')
 THEN RETURN NULL; END IF;
 UPDATE club.officer_webauthn_challenges c
 SET consumed_at=clock_timestamp()
 WHERE c.challenge_id=p_id AND c.account_id=p_account
   AND c.ceremony=p_purpose
   AND c.challenge_bytes IS NOT NULL
   AND c.challenge_sha256=public.digest(c.challenge_bytes,'sha256')
   AND c.consumed_at IS NULL AND c.expires_at>clock_timestamp()
 RETURNING c.challenge_bytes INTO v_nonce;
 RETURN v_nonce;
END $$;

CREATE OR REPLACE FUNCTION club.register_verified_webauthn_credential(
 p_account uuid,p_credential_id bytea,p_public_key bytea,p_counter bigint)
RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,club AS $$
BEGIN
 IF p_account IS NULL OR NOT club.can_enrol_officer_webauthn(p_account)
  OR p_credential_id IS NULL OR p_public_key IS NULL
  OR octet_length(p_credential_id) NOT BETWEEN 16 AND 1024
  OR octet_length(p_public_key) NOT BETWEEN 32 AND 8192
  OR p_counter IS NULL OR p_counter < 0
  OR NOT EXISTS(SELECT 1 FROM club.committee_accounts
    WHERE id=p_account AND account_state='active')
 THEN RETURN false; END IF;
 -- The verifier MUST have validated the attestation and independent enrolment
 -- authorisation; only the isolated authn role may invoke this.
 INSERT INTO club.officer_webauthn_credentials
  (credential_id,account_id,public_key,signature_counter)
 VALUES(p_credential_id,p_account,p_public_key,p_counter);
 RETURN true;
END $$;

CREATE OR REPLACE FUNCTION club.verified_officer_webauthn_credentials(p_account uuid)
RETURNS TABLE(credential_id bytea,public_key bytea,signature_counter bigint)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,club AS $$
 SELECT c.credential_id,c.public_key,c.signature_counter
 FROM club.officer_webauthn_credentials c
 JOIN club.committee_accounts a ON a.id=c.account_id
 WHERE c.account_id=p_account AND c.revoked_at IS NULL
  AND a.account_state='active'
 ORDER BY c.created_at
$$;
CREATE OR REPLACE FUNCTION club.active_officer_for_authn(p_account uuid)
RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,club AS $$
 SELECT EXISTS(SELECT 1 FROM club.committee_accounts
  WHERE id=p_account AND account_state='active')
$$;

-- Enrolment is denied unless recovery has two distinct, current MFA-backed
-- officer approvals; bootstrap for the first authorised officer remains blocked.
CREATE OR REPLACE FUNCTION club.can_enrol_officer_webauthn(p_account uuid)
RETURNS boolean LANGUAGE sql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,club AS $
 SELECT EXISTS(
  SELECT 1 FROM club.security_change_requests r
  JOIN club.committee_accounts a ON a.id=r.subject_account_id
  WHERE a.id=p_account AND a.account_state='active'
   AND r.change_kind='account_recovery'
   AND r.status='pending' AND r.expires_at>clock_timestamp()
   AND club.security_change_ready(r.id)
 )
$;
REVOKE EXECUTE ON FUNCTION club.can_enrol_officer_webauthn(uuid)
 FROM PUBLIC,clubmgr,club_api_service,club_authz_service;
GRANT EXECUTE ON FUNCTION club.can_enrol_officer_webauthn(uuid)
 TO club_authn_service;

REVOKE EXECUTE ON FUNCTION club.start_webauthn_challenge(uuid,text,bytea) FROM PUBLIC,clubmgr,club_api_service,club_authz_service;
REVOKE EXECUTE ON FUNCTION club.claim_webauthn_challenge(uuid,uuid,text) FROM PUBLIC,clubmgr,club_api_service,club_authz_service;
REVOKE EXECUTE ON FUNCTION club.register_verified_webauthn_credential(uuid,bytea,bytea,bigint) FROM PUBLIC,clubmgr,club_api_service,club_authz_service;
REVOKE EXECUTE ON FUNCTION club.verified_officer_webauthn_credentials(uuid) FROM PUBLIC,clubmgr,club_api_service,club_authz_service;
REVOKE EXECUTE ON FUNCTION club.active_officer_for_authn(uuid) FROM PUBLIC,clubmgr,club_api_service,club_authz_service;
GRANT EXECUTE ON FUNCTION club.start_webauthn_challenge(uuid,text,bytea) TO club_authn_service;
GRANT EXECUTE ON FUNCTION club.claim_webauthn_challenge(uuid,uuid,text) TO club_authn_service;
GRANT EXECUTE ON FUNCTION club.register_verified_webauthn_credential(uuid,bytea,bytea,bigint) TO club_authn_service;
GRANT EXECUTE ON FUNCTION club.verified_officer_webauthn_credentials(uuid) TO club_authn_service;
GRANT EXECUTE ON FUNCTION club.active_officer_for_authn(uuid) TO club_authn_service;
-- Do not grant LOGIN or the authn service role to the old shared-password app.
COMMIT;
