BEGIN;
-- Policy only: no account, authenticator or privileged operation is activated.
CREATE TABLE IF NOT EXISTS club.security_policy (
 singleton boolean PRIMARY KEY DEFAULT true CHECK(singleton),
 preferred_factor text NOT NULL CHECK(preferred_factor='webauthn'),
 fallback_factor text NOT NULL CHECK(fallback_factor='totp'),
 minimum_independent_approvers smallint NOT NULL CHECK(minimum_independent_approvers>=2),
 privileged_session_minutes smallint NOT NULL CHECK(privileged_session_minutes BETWEEN 1 AND 15),
 direct_database_admin_mfa_required boolean NOT NULL DEFAULT true CHECK(direct_database_admin_mfa_required),
 updated_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
INSERT INTO club.security_policy(singleton,preferred_factor,fallback_factor,
 minimum_independent_approvers,privileged_session_minutes,direct_database_admin_mfa_required)
VALUES(true,'webauthn','totp',2,15,true)
ON CONFLICT(singleton) DO UPDATE SET
 preferred_factor='webauthn',fallback_factor='totp',
 minimum_independent_approvers=2,privileged_session_minutes=15,
 direct_database_admin_mfa_required=true,
 updated_at=clock_timestamp();

-- Credential records are intentionally provisioned only by an independent
-- future enrolment/verification service. No secret material is held here.
CREATE TABLE IF NOT EXISTS club.officer_authenticator_registry (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 account_id uuid NOT NULL REFERENCES club.committee_accounts(id),
 factor_type text NOT NULL CHECK(factor_type IN ('webauthn','totp')),
 credential_ref text NOT NULL CHECK(length(credential_ref) BETWEEN 8 AND 256),
 enrolled_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 verified_at timestamptz,
 revoked_at timestamptz,
 UNIQUE(factor_type,credential_ref),
 CHECK(revoked_at IS NULL OR revoked_at>=enrolled_at)
);

INSERT INTO club.committee_permissions(permission_code,description)
VALUES
 ('account_recovery_approve','Approve another officer account recovery after MFA'),
 ('database_maintenance_approve','Approve sensitive PostgreSQL maintenance after MFA')
ON CONFLICT(permission_code) DO NOTHING;

CREATE TABLE IF NOT EXISTS club.security_change_requests (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 change_kind text NOT NULL CHECK(change_kind IN ('account_recovery','database_maintenance')),
 subject_account_id uuid REFERENCES club.committee_accounts(id),
 requested_by uuid NOT NULL REFERENCES club.committee_accounts(id),
 justification text NOT NULL CHECK(length(trim(justification)) BETWEEN 10 AND 1000),
 status text NOT NULL DEFAULT 'pending'
  CHECK(status IN ('pending','cancelled','rejected','completed')),
 requested_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 expires_at timestamptz NOT NULL DEFAULT (clock_timestamp()+interval '24 hours'),
 CHECK(expires_at>requested_at AND expires_at<=requested_at+interval '24 hours'),
 CHECK(change_kind<>'account_recovery' OR subject_account_id IS NOT NULL)
);
CREATE TABLE IF NOT EXISTS club.security_change_approvals (
 request_id uuid NOT NULL REFERENCES club.security_change_requests(id),
 approver_id uuid NOT NULL REFERENCES club.committee_accounts(id),
 mfa_session_id uuid NOT NULL REFERENCES club.officer_mfa_sessions(session_id),
 approved_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 PRIMARY KEY(request_id,approver_id),
 UNIQUE(request_id,mfa_session_id)
);
CREATE OR REPLACE FUNCTION club.security_approval_guard()
RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog,club AS $$
DECLARE r record; s record; required_permission text;
BEGIN
 IF TG_OP<>'INSERT' THEN RAISE EXCEPTION 'Security approvals are immutable'; END IF;
 SELECT * INTO r FROM club.security_change_requests
  WHERE id=NEW.request_id FOR UPDATE;
 IF NOT FOUND OR r.status<>'pending' OR r.expires_at<=clock_timestamp()
  THEN RAISE EXCEPTION 'Security request is not pending'; END IF;
 IF NEW.approver_id=r.requested_by OR NEW.approver_id IS NOT DISTINCT FROM r.subject_account_id
  THEN RAISE EXCEPTION 'Requester or recovery subject cannot approve'; END IF;
 SELECT * INTO s FROM club.officer_mfa_sessions WHERE session_id=NEW.mfa_session_id;
 IF NOT FOUND OR s.account_id<>NEW.approver_id
    OR s.revoked_at IS NOT NULL
    OR s.verified_at>clock_timestamp()
    OR s.verified_at<clock_timestamp()-interval '15 minutes'
    OR s.expires_at<=clock_timestamp()
  THEN RAISE EXCEPTION 'Current named-officer MFA required'; END IF;
 required_permission:=CASE WHEN r.change_kind='account_recovery'
   THEN 'account_recovery_approve' ELSE 'database_maintenance_approve' END;
 IF NOT club.committee_has_permission(NEW.approver_id,required_permission)
  THEN RAISE EXCEPTION 'Explicit security approval permission required'; END IF;
 RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS security_approvals_insert_guard ON club.security_change_approvals;
CREATE TRIGGER security_approvals_insert_guard
BEFORE INSERT OR UPDATE OR DELETE ON club.security_change_approvals
FOR EACH ROW EXECUTE FUNCTION club.security_approval_guard();

-- This is a readiness predicate, not an executor. It never resets credentials
-- or runs database commands. Future broker must recheck it atomically.
CREATE OR REPLACE FUNCTION club.security_change_ready(p_request uuid)
RETURNS boolean LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,club AS $$
DECLARE r record; n integer; needed integer;
BEGIN
 SELECT * INTO r FROM club.security_change_requests WHERE id=p_request;
 IF NOT FOUND OR r.status<>'pending' OR r.expires_at<=clock_timestamp()
  THEN RETURN false; END IF;
 SELECT minimum_independent_approvers INTO needed FROM club.security_policy WHERE singleton=true;
 IF needed IS NULL THEN RETURN false; END IF;
 SELECT count(*) INTO n FROM club.security_change_approvals a
 JOIN club.officer_mfa_sessions s ON s.session_id=a.mfa_session_id
 WHERE a.request_id=p_request
  AND a.approver_id<>r.requested_by
  AND (r.subject_account_id IS NULL OR a.approver_id<>r.subject_account_id)
  AND s.account_id=a.approver_id AND s.revoked_at IS NULL
  AND s.verified_at<=clock_timestamp()
  AND s.verified_at>=clock_timestamp()-interval '15 minutes'
  AND s.expires_at>clock_timestamp()
  AND club.committee_has_permission(a.approver_id,
   CASE WHEN r.change_kind='account_recovery'
    THEN 'account_recovery_approve' ELSE 'database_maintenance_approve' END);
 RETURN n>=needed;
END $$;
REVOKE ALL ON club.security_policy,club.officer_authenticator_registry,
 club.security_change_requests,club.security_change_approvals FROM PUBLIC,clubmgr,club_authz_service;
REVOKE EXECUTE ON FUNCTION club.security_approval_guard() FROM PUBLIC,clubmgr,club_authz_service;
REVOKE EXECUTE ON FUNCTION club.security_change_ready(uuid) FROM PUBLIC,clubmgr,club_authz_service;
-- Deliberately no grants to the prototype or browser UI.
COMMIT;
