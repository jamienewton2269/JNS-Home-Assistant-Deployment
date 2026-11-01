BEGIN;
-- PostgreSQL functions grant EXECUTE to PUBLIC unless explicitly revoked.
REVOKE EXECUTE ON ALL FUNCTIONS IN SCHEMA club FROM PUBLIC;
REVOKE ALL ON ALL TABLES IN SCHEMA club FROM PUBLIC, clubmgr;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA club FROM PUBLIC, clubmgr;
GRANT SELECT ON club.current_members TO clubmgr;
GRANT EXECUTE ON FUNCTION club.append_member(uuid,text,text,text,text) TO clubmgr;
GRANT EXECUTE ON FUNCTION club.audit_rows() TO clubmgr;
-- Prevent future functions from automatically becoming callable by PUBLIC.
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA club REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC;
COMMIT;
