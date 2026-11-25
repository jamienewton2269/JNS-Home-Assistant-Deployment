BEGIN;
CREATE OR REPLACE FUNCTION club.api_membership_review(p_bearer text,p_request uuid,p_approve boolean,p_note text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,club AS $$
DECLARE actor uuid; req club.officer_actions%ROWTYPE; actual bigint; expected bigint;
 v_seq bigint; v_prev text; v_action text; v_payload jsonb; v_digest text;
BEGIN
 IF NOT club.officer_session_authorized(p_bearer,'members_approve') THEN
  RAISE EXCEPTION 'Access denied' USING ERRCODE='42501'; END IF;
 SELECT account_id INTO STRICT actor FROM club.officer_api_sessions
 WHERE bearer_sha256=public.digest(convert_to(p_bearer,'UTF8'),'sha256')
 AND revoked_at IS NULL AND expires_at>clock_timestamp();
 SELECT * INTO STRICT req FROM club.officer_actions WHERE id=p_request FOR UPDATE;
 IF req.action_kind<>'membership_amendment' OR req.state<>'pending' OR req.requested_by=actor::text
 THEN RAISE EXCEPTION 'Independent pending membership review required' USING ERRCODE='42501'; END IF;
 IF p_approve IS NULL OR length(coalesce(p_note,''))>2000 THEN
 RAISE EXCEPTION 'Invalid review' USING ERRCODE='22023'; END IF;
 IF p_approve THEN
  PERFORM pg_advisory_xact_lock(7812201);
  expected:=(req.request_json->>'expected_version')::bigint;
  SELECT version INTO actual FROM club.current_members WHERE member_id=req.subject_id;
  IF expected IS NULL OR coalesce(actual,0)<>expected THEN
   RAISE EXCEPTION 'Membership version conflict' USING ERRCODE='22023'; END IF;
  IF req.request_json->>'operation'='create' AND expected=0 THEN
   v_action:='CREATE';
   INSERT INTO club.member_profiles(id,category,status) VALUES(req.subject_id,req.request_json->>'category','active');
  ELSIF req.request_json->>'operation'='amend' AND expected>0 THEN
   v_action:='REVISE';
   UPDATE club.member_profiles SET category=req.request_json->>'category',version=version+1,updated_at=clock_timestamp() WHERE id=req.subject_id;
   IF NOT FOUND THEN RAISE EXCEPTION 'Missing membership profile'; END IF;
  ELSE RAISE EXCEPTION 'Unsupported membership request' USING ERRCODE='22023'; END IF;
  v_payload:=jsonb_build_object('name',req.request_json->>'name','email',req.request_json->>'email','category',req.request_json->>'category');
  SELECT entry_hash INTO v_prev FROM club.event_log ORDER BY seq DESC LIMIT 1;
  v_prev:=coalesce(v_prev,repeat('0',64));
  v_seq:=nextval(pg_get_serial_sequence('club.event_log','seq'));
  v_digest:=encode(public.digest(v_prev||'|'||v_seq::text||'|'||req.subject_id::text||'|'||v_action||'|'||v_payload::text||'|'||actor::text,'sha256'),'hex');
  INSERT INTO club.event_log(seq,prev_hash,entry_hash,member_id,action,payload,actor)
  OVERRIDING SYSTEM VALUE VALUES(v_seq,v_prev,v_digest,req.subject_id,v_action,v_payload,actor::text);
 END IF;
 UPDATE club.officer_actions SET state=CASE WHEN p_approve THEN 'approved' ELSE 'rejected' END,
 reviewed_by=actor::text,reviewed_at=clock_timestamp(),review_note=p_note WHERE id=p_request;
 RETURN jsonb_build_object('reviewed',true,'state',CASE WHEN p_approve THEN 'approved' ELSE 'rejected' END);
END $$;
REVOKE ALL ON FUNCTION club.api_membership_review(text,uuid,boolean,text) FROM PUBLIC,clubmgr,club_authn_service,club_authz_service;
GRANT EXECUTE ON FUNCTION club.api_membership_review(text,uuid,boolean,text) TO club_api_service;
COMMIT;
