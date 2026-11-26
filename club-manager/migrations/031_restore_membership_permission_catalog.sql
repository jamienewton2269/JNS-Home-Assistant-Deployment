BEGIN;
INSERT INTO club.committee_permissions(permission_code,description) VALUES
('members_view','View authorised membership records'),
('members_amend','Submit member amendments'),
('members_approve','Approve member amendments'),
('moorings_manage','Manage mooring requests')
ON CONFLICT (permission_code) DO NOTHING;
COMMIT;
