BEGIN;
CREATE TABLE IF NOT EXISTS club.committee_accounts (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 display_name text NOT NULL CHECK(length(trim(display_name)) BETWEEN 2 AND 120),
 email text NOT NULL CHECK(length(email) BETWEEN 5 AND 254),
 account_state text NOT NULL DEFAULT 'disabled' CHECK(account_state IN ('disabled','invited','active','suspended')),
 created_by text NOT NULL,
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 UNIQUE(email)
);
CREATE TABLE IF NOT EXISTS club.committee_roles (
 role_code text PRIMARY KEY, description text NOT NULL
);
INSERT INTO club.committee_roles(role_code,description) VALUES
('membership_secretary','Membership Secretary'),
('treasurer','Treasurer'),
('committee','Commodore / General Committee'),
('system_administrator','System Administrator')
ON CONFLICT DO NOTHING;
CREATE TABLE IF NOT EXISTS club.committee_permissions (
 permission_code text PRIMARY KEY, description text NOT NULL
);
INSERT INTO club.committee_permissions(permission_code,description) VALUES
('members_view','View authorised membership records'),
('members_amend','Submit member amendments'),
('members_approve','Approve member amendments'),
('boats_manage','Manage boat and yard asset requests'),
('moorings_manage','Manage mooring requests'),
('clubhouse_manage','Manage clubhouse diary requests'),
('renewals_manage','Prepare annual renewals'),
('payments_view','View authorised financial summaries'),
('payments_reconcile','Reconcile verified payments'),
('tariffs_manage','Propose tariff changes'),
('gdpr_manage','Manage approved privacy requests'),
('audit_view','View authorised audit evidence'),
('accounts_create','Create disabled committee accounts'),
('accounts_grant','Approve and grant committee access')
ON CONFLICT DO NOTHING;
CREATE TABLE IF NOT EXISTS club.committee_role_grants (
 account_id uuid NOT NULL REFERENCES club.committee_accounts(id),
 role_code text NOT NULL REFERENCES club.committee_roles(role_code),
 approved_by text NOT NULL, granted_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 PRIMARY KEY(account_id,role_code)
);
CREATE TABLE IF NOT EXISTS club.committee_permission_grants (
 account_id uuid NOT NULL REFERENCES club.committee_accounts(id),
 permission_code text NOT NULL REFERENCES club.committee_permissions(permission_code),
 approved_by text NOT NULL, granted_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 PRIMARY KEY(account_id,permission_code)
);
CREATE OR REPLACE FUNCTION club.create_disabled_committee_account(
 p_name text,p_email text,p_actor text)
RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,club AS $$
DECLARE new_id uuid;
BEGIN
 IF length(trim(p_name)) NOT BETWEEN 2 AND 120 OR
    p_email IS NULL OR length(trim(p_email)) NOT BETWEEN 5 AND 254 OR
    position('@' in p_email)=0 OR
    p_actor<>'local-dev-admin' THEN
   RAISE EXCEPTION 'Invalid committee account request';
 END IF;
 INSERT INTO club.committee_accounts(display_name,email,created_by)
 VALUES(trim(p_name),lower(trim(p_email)),p_actor)
 RETURNING id INTO new_id;
 RETURN new_id;
END $$;
CREATE OR REPLACE FUNCTION club.list_committee_accounts()
RETURNS TABLE(id uuid,display_name text,email text,account_state text,roles text[],permissions text[])
LANGUAGE sql SECURITY DEFINER SET search_path=pg_catalog,club AS $$
 SELECT a.id,a.display_name,a.email,a.account_state,
 ARRAY(SELECT r.role_code FROM club.committee_role_grants r WHERE r.account_id=a.id ORDER BY r.role_code),
 ARRAY(SELECT p.permission_code FROM club.committee_permission_grants p WHERE p.account_id=a.id ORDER BY p.permission_code)
 FROM club.committee_accounts a ORDER BY a.created_at DESC
$$;
REVOKE ALL ON club.committee_accounts,club.committee_roles,club.committee_permissions,club.committee_role_grants,club.committee_permission_grants FROM PUBLIC,clubmgr;
REVOKE EXECUTE ON FUNCTION club.create_disabled_committee_account(text,text,text) FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION club.list_committee_accounts() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION club.create_disabled_committee_account(text,text,text) TO clubmgr;
GRANT EXECUTE ON FUNCTION club.list_committee_accounts() TO clubmgr;
-- No account activation or grant functions are provided to the development web app.
COMMIT;
