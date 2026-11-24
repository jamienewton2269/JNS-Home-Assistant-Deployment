BEGIN;
CREATE OR REPLACE FUNCTION club.api_membership_request(p_bearer text,p_data jsonb)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,club AS $$
DECLARE actor uuid; target uuid; request_id uuid; expected bigint; actual bigint;
BEGIN
 IF NOT club.officer_session_authorized(p_bearer,'members_amend') THEN
  RAISE EXCEPTION 'Access denied' USING ERRCODE='42501'; END IF;
 SELECT account_id INTO STRICT actor FROM club.officer_api_sessions
 WHERE bearer_sha256=public.digest(convert_to(p_bearer,'UTF8'),'sha256')
 AND revoked_at IS NULL AND expires_at>clock_timestamp();
 IF jsonb_typeof(p_data) IS DISTINCT FROM 'object' OR
 COALESCE(length(trim(p_data->>'name')),0) NOT BETWEEN 1 AND 120 OR
 COALESCE(length(trim(p_data->>'email')),0) NOT BETWEEN 3 AND 200 OR
 COALESCE(position('@' in p_data->>'email'),0)=0 OR
 COALESCE(p_data->>'category','') NOT IN ('Full','Family','Junior','Social','Honorary')
 THEN RAISE EXCEPTION 'Invalid membership details' USING ERRCODE='22023'; END IF;
 IF p_data->>'operation'='create' THEN
  target:=gen_random_uuid(); expected:=0;
 ELSIF p_data->>'operation'='amend' THEN
  target:=(p_data->>'member_id')::uuid;
  expected:=(p_data->>'version')::bigint;
  SELECT version INTO actual FROM club.current_members WHERE member_id=target;
  IF actual IS NULL OR expected IS DISTINCT FROM actual THEN
   RAISE EXCEPTION 'Membership version conflict' USING ERRCODE='22023'; END IF;
 ELSE RAISE EXCEPTION 'Unknown operation' USING ERRCODE='22023'; END IF;
 INSERT INTO club.officer_actions(action_kind,subject_id,request_json,requested_by)
 VALUES('membership_amendment',target,jsonb_build_object('operation',p_data->>'operation',
 'name',trim(p_data->>'name'),'email',trim(p_data->>'email'),'category',p_data->>'category',
 'expected_version',expected),actor::text) RETURNING id INTO request_id;
 RETURN jsonb_build_object('submitted',true,'request_id',request_id,'state','pending');
END $$;
REVOKE ALL ON FUNCTION club.api_membership_request(text,jsonb) FROM PUBLIC,clubmgr,club_authn_service,club_authz_service;
GRANT EXECUTE ON FUNCTION club.api_membership_request(text,jsonb) TO club_api_service;
COMMIT;
