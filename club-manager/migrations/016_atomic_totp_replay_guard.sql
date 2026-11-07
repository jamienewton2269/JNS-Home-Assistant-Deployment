BEGIN;
-- Track consumption of the TOTP time step independently of the secret.
-- The secret itself is held by the future isolated credential verifier.
ALTER TABLE club.officer_authenticator_registry
 ADD COLUMN IF NOT EXISTS last_accepted_totp_step bigint NOT NULL DEFAULT -1
 CHECK(last_accepted_totp_step >= -1);

DO $$ BEGIN
 IF NOT EXISTS(SELECT 1 FROM pg_roles WHERE rolname='club_authn_service')
 THEN CREATE ROLE club_authn_service NOLOGIN; END IF;
END $$;
GRANT USAGE ON SCHEMA club TO club_authn_service;

CREATE OR REPLACE FUNCTION club.consume_officer_totp_step(
 p_credential_id uuid, p_account_id uuid, p_step bigint)
RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,club AS $$
DECLARE updated_id uuid;
BEGIN
 IF p_credential_id IS NULL OR p_account_id IS NULL OR p_step IS NULL OR p_step < 0
 THEN RETURN false; END IF;
 UPDATE club.officer_authenticator_registry c
 SET last_accepted_totp_step=p_step
 FROM club.committee_accounts a
 WHERE c.id=p_credential_id
   AND c.account_id=p_account_id AND c.factor_type='totp'
   AND c.revoked_at IS NULL AND c.verified_at IS NOT NULL
   AND a.id=c.account_id AND a.account_state='active'
   AND c.last_accepted_totp_step < p_step
 RETURNING c.id INTO updated_id;
 RETURN updated_id IS NOT NULL;
END $$;

REVOKE EXECUTE ON FUNCTION club.consume_officer_totp_step(uuid,uuid,bigint)
 FROM PUBLIC,clubmgr,club_authz_service;
GRANT EXECUTE ON FUNCTION club.consume_officer_totp_step(uuid,uuid,bigint)
 TO club_authn_service;
-- A NOLOGIN role is deliberately not an application connection credential.
-- Future named-officer primary authentication, encrypted secret lookup,
-- rate limiting, actual TOTP verification and verified session issuance
-- must all be implemented before any use by an online login service.
COMMIT;
