BEGIN;
-- Authentication is NOT provided by this function. The caller must be a trusted
-- independently authenticated service in a future release.
CREATE OR REPLACE FUNCTION club.committee_has_permission(p_account uuid,p_permission text)
RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,club AS $$
 SELECT EXISTS (
  SELECT 1 FROM club.committee_accounts a
  JOIN club.committee_permission_grants g ON g.account_id=a.id
  JOIN club.committee_permissions p ON p.permission_code=g.permission_code
  WHERE a.id=p_account AND a.account_state='active'
    AND p.permission_code=p_permission
 )
$$;
-- Explicit grants, not role names, convey privileges.
-- A committee role label never implicitly enables access.
REVOKE EXECUTE ON FUNCTION club.committee_has_permission(uuid,text) FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION club.committee_has_permission(uuid,text) FROM clubmgr;
DO $$ BEGIN
 IF NOT EXISTS(SELECT 1 FROM pg_roles WHERE rolname='club_authz_service') THEN
  CREATE ROLE club_authz_service NOLOGIN;
 END IF;
END $$;
GRANT USAGE ON SCHEMA club TO club_authz_service;
GRANT EXECUTE ON FUNCTION club.committee_has_permission(uuid,text) TO club_authz_service;
-- Account state and explicit grants can only be changed by the DB owner for now.
-- Do not expose grant or activation functions before officer MFA and dual approval.
COMMIT;
