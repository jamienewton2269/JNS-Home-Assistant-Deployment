BEGIN;
-- WebAuthn challenge replay protection. Only an isolated NOLOGIN verifier
-- may create or consume ceremonies. Browser access is not provided.
CREATE TABLE IF NOT EXISTS club.officer_webauthn_challenges(
 challenge_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 account_id uuid NOT NULL REFERENCES club.committee_accounts(id),
 ceremony text NOT NULL CHECK(ceremony IN ('register','authenticate')),
 challenge_sha256 bytea NOT NULL CHECK(octet_length(challenge_sha256)=32),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 expires_at timestamptz NOT NULL,
 consumed_at timestamptz,
 CHECK(expires_at>created_at AND expires_at<=created_at+interval '5 minutes'),
 UNIQUE(challenge_sha256)
);
CREATE INDEX IF NOT EXISTS officer_webauthn_challenge_expiry_idx
 ON club.officer_webauthn_challenges(expires_at);
CREATE TABLE IF NOT EXISTS club.officer_webauthn_credentials(
 credential_id bytea PRIMARY KEY CHECK(octet_length(credential_id) BETWEEN 16 AND 1024),
 account_id uuid NOT NULL REFERENCES club.committee_accounts(id),
 public_key bytea NOT NULL CHECK(octet_length(public_key) BETWEEN 32 AND 8192),
 signature_counter bigint NOT NULL DEFAULT 0 CHECK(signature_counter>=0),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 revoked_at timestamptz
);
CREATE INDEX IF NOT EXISTS officer_webauthn_credential_owner_idx
 ON club.officer_webauthn_credentials(account_id);
CREATE OR REPLACE FUNCTION club.consume_webauthn_challenge(
 p_challenge_id uuid,p_account uuid,p_purpose text,p_challenge_sha256 bytea
) RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,club AS $$
DECLARE match_id uuid;
BEGIN
 IF p_challenge_id IS NULL OR p_account IS NULL OR p_purpose IS NULL OR
  p_challenge_sha256 IS NULL OR octet_length(p_challenge_sha256)<>32
 THEN RETURN false; END IF;
 UPDATE club.officer_webauthn_challenges c
 SET consumed_at=clock_timestamp()
 WHERE c.challenge_id=p_challenge_id
   AND c.account_id=p_account
   AND c.ceremony=p_purpose
   AND c.challenge_sha256=p_challenge_sha256
   AND c.consumed_at IS NULL AND c.expires_at>clock_timestamp()
 RETURNING c.challenge_id INTO match_id;
 RETURN match_id IS NOT NULL;
END $$;
-- Called only AFTER cryptographic WebAuthn assertion verification with
-- expected RP ID, origin, challenge, signature and user verification.
-- Synced passkeys may legitimately keep a zero signature counter.
CREATE OR REPLACE FUNCTION club.commit_webauthn_counter(
 p_account uuid,p_credential_id bytea,p_new_counter bigint
) RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,club AS $$
DECLARE v_id bytea;
BEGIN
 IF p_account IS NULL OR p_credential_id IS NULL
   OR p_new_counter IS NULL OR p_new_counter<0 THEN RETURN false; END IF;
 UPDATE club.officer_webauthn_credentials c SET signature_counter=p_new_counter
 FROM club.committee_accounts a
 WHERE c.credential_id=p_credential_id AND c.account_id=p_account
   AND c.revoked_at IS NULL
   AND a.id=c.account_id AND a.account_state='active'
   AND (p_new_counter>c.signature_counter OR
        (p_new_counter=0 AND c.signature_counter=0))
 RETURNING c.credential_id INTO v_id;
 RETURN v_id IS NOT NULL;
END $$;
REVOKE ALL ON club.officer_webauthn_challenges,club.officer_webauthn_credentials
 FROM PUBLIC,clubmgr,club_api_service,club_authz_service,club_authn_service;
REVOKE EXECUTE ON FUNCTION club.consume_webauthn_challenge(uuid,uuid,text,bytea)
 FROM PUBLIC,clubmgr,club_api_service,club_authz_service;
REVOKE EXECUTE ON FUNCTION club.commit_webauthn_counter(uuid,bytea,bigint)
 FROM PUBLIC,clubmgr,club_api_service,club_authz_service;
GRANT EXECUTE ON FUNCTION club.consume_webauthn_challenge(uuid,uuid,text,bytea)
 TO club_authn_service;
GRANT EXECUTE ON FUNCTION club.commit_webauthn_counter(uuid,bytea,bigint)
 TO club_authn_service;
-- Insertion of credentials and challenges remains owner-only until an
-- enrolment broker with independent authorisation is tested.
COMMIT;
