BEGIN;
-- A replay counter is meaningful only after the trusted authentication service
-- has cryptographically verified TOTP and bound the credential to a named officer.
-- No direct access is granted to the existing Basic Auth app or any LOGIN role.
CREATE TABLE IF NOT EXISTS club.officer_totp_replay_state(
 credential_id uuid PRIMARY KEY REFERENCES club.officer_authenticator_registry(id),
 last_accepted_step bigint NOT NULL CHECK(last_accepted_step>=0),
 accepted_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE OR REPLACE FUNCTION club.claim_totp_step(
 p_account uuid,p_credential uuid,p_step bigint
) RETURNS boolean LANGUAGE plpgsql VOLATILE SECURITY DEFINER
 SET search_path=pg_catalog,club AS $$
DECLARE changed integer;
BEGIN
 IF p_account IS NULL OR p_credential IS NULL OR p_step IS NULL OR p_step<0 THEN RETURN false; END IF;
 IF NOT EXISTS(
  SELECT 1 FROM club.committee_accounts a
   JOIN club.officer_authenticator_registry c ON c.account_id=a.id
   WHERE a.id=p_account AND a.account_state='active'
     AND c.id=p_credential AND c.factor_type='totp'
     AND c.verified_at IS NOT NULL AND c.verified_at<=clock_timestamp()
     AND c.revoked_at IS NULL
 ) THEN RETURN false; END IF;
 INSERT INTO club.officer_totp_replay_state AS r(credential_id,last_accepted_step)
 VALUES(p_credential,p_step)
 ON CONFLICT(credential_id) DO UPDATE
 SET last_accepted_step=EXCLUDED.last_accepted_step,
     accepted_at=clock_timestamp()
 WHERE r.last_accepted_step<EXCLUDED.last_accepted_step;
 GET DIAGNOSTICS changed=ROW_COUNT;
 RETURN changed=1;
END $$;
REVOKE ALL ON club.officer_totp_replay_state FROM PUBLIC,clubmgr,club_authz_service;
REVOKE EXECUTE ON FUNCTION club.claim_totp_step(uuid,uuid,bigint) FROM PUBLIC,clubmgr;
GRANT EXECUTE ON FUNCTION club.claim_totp_step(uuid,uuid,bigint) TO club_authz_service;
-- club_authz_service is NOLOGIN and must be granted only to a separately
-- audited MFA verifier service AFTER its credential validation is integrated.
COMMIT;
