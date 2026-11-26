BEGIN;
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
COMMIT;
