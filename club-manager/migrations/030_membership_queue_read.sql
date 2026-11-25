BEGIN;
CREATE OR REPLACE FUNCTION club.api_membership_queue(p_bearer text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,club AS $$
DECLARE actor uuid; reviewer boolean;
BEGIN
 reviewer:=club.officer_session_authorized(p_bearer,'members_approve');
 IF NOT reviewer AND NOT club.officer_session_authorized(p_bearer,'members_amend') THEN
 RAISE EXCEPTION 'Access denied' USING ERRCODE='42501'; END IF;
 SELECT account_id INTO STRICT actor FROM club.officer_api_sessions
 WHERE bearer_sha256=public.digest(convert_to(p_bearer,'UTF8'),'sha256')
 AND revoked_at IS NULL AND expires_at>clock_timestamp();
 RETURN (SELECT coalesce(jsonb_agg(to_jsonb(q)),'[]'::jsonb) FROM
 (SELECT id,subject_id,request_json,state,requested_at,
 reviewer AND requested_by<>actor::text AS can_review
 FROM club.officer_actions WHERE action_kind='membership_amendment'
 AND state='pending' AND (reviewer OR requested_by=actor::text)
 ORDER BY requested_at,id LIMIT 200) q);
END $$;
REVOKE ALL ON FUNCTION club.api_membership_queue(text) FROM PUBLIC,clubmgr,club_authn_service,club_authz_service;
GRANT EXECUTE ON FUNCTION club.api_membership_queue(text) TO club_api_service;
COMMIT;
