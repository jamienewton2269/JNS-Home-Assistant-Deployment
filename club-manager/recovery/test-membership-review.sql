BEGIN;
DO $$
DECLARE a uuid; b uuid; m uuid; token_a text:=encode(public.gen_random_bytes(32),'hex'); token_b text:=encode(public.gen_random_bytes(32),'hex'); q uuid; q2 uuid; target uuid; result jsonb;
BEGIN
 INSERT INTO club.committee_accounts(display_name,email,account_state,created_by) VALUES('Synthetic requester',gen_random_uuid()||'@example.invalid','active','regression') RETURNING id INTO a;
 INSERT INTO club.committee_accounts(display_name,email,account_state,created_by) VALUES('Synthetic reviewer',gen_random_uuid()||'@example.invalid','active','regression') RETURNING id INTO b;
 INSERT INTO club.committee_permission_grants(account_id,permission_code,approved_by) SELECT x,p,'regression' FROM unnest(ARRAY[a,b]) x CROSS JOIN unnest(ARRAY['members_view','members_amend','members_approve']) p;
 INSERT INTO club.officer_mfa_sessions(account_id,method,verified_at,expires_at) VALUES(a,'webauthn',clock_timestamp(),clock_timestamp()+interval '10 minutes') RETURNING session_id INTO m;
 PERFORM club.issue_officer_api_session(a,m,public.digest(convert_to(token_a,'UTF8'),'sha256'));
 INSERT INTO club.officer_mfa_sessions(account_id,method,verified_at,expires_at) VALUES(b,'webauthn',clock_timestamp(),clock_timestamp()+interval '10 minutes') RETURNING session_id INTO m;
 PERFORM club.issue_officer_api_session(b,m,public.digest(convert_to(token_b,'UTF8'),'sha256'));
 result:=club.api_membership_request(token_a,'{"operation":"create","name":"Synthetic test member","email":"test@example.invalid","category":"Full"}');
 q:=(result->>'request_id')::uuid;
 SELECT subject_id INTO STRICT target FROM club.officer_actions WHERE id=q;
 IF EXISTS(SELECT 1 FROM club.current_members WHERE member_id=target) THEN RAISE EXCEPTION 'Premature creation'; END IF;
 BEGIN
 PERFORM club.api_membership_review(token_a,q,true,'self');
 RAISE EXCEPTION 'Self approval accepted';
 EXCEPTION WHEN insufficient_privilege THEN NULL; END;
 PERFORM club.api_membership_review(token_b,q,true,'test approval');
 IF NOT EXISTS(SELECT 1 FROM club.current_members WHERE member_id=target AND version=1) THEN RAISE EXCEPTION 'Creation missing'; END IF;
 RAISE NOTICE 'PASS creation and independent approval';
 result:=club.api_membership_request(token_a,jsonb_build_object('operation','amend','member_id',target,'version',1,'name','Synthetic amended','email','test@example.invalid','category','Family'));
 q:=(result->>'request_id')::uuid;
 result:=club.api_membership_request(token_a,jsonb_build_object('operation','amend','member_id',target,'version',1,'name','Synthetic stale','email','test@example.invalid','category','Full'));
 q2:=(result->>'request_id')::uuid;
 PERFORM club.api_membership_review(token_b,q,true,'test amendment');
 IF NOT EXISTS(SELECT 1 FROM club.current_members WHERE member_id=target AND version=2 AND category='Family') THEN RAISE EXCEPTION 'Amendment missing'; END IF;
 BEGIN
 PERFORM club.api_membership_review(token_b,q2,true,'stale');
 RAISE EXCEPTION 'Stale amendment accepted';
 EXCEPTION WHEN invalid_parameter_value THEN NULL; END;
 PERFORM club.api_membership_review(token_b,q2,false,'reject stale');
 IF (SELECT count(*) FROM club.event_log WHERE member_id=target)<>2 THEN RAISE EXCEPTION 'Ledger count mismatch'; END IF;
 IF (SELECT count(*) FROM club.officer_action_events WHERE action_id IN(q,q2))<>4 THEN RAISE EXCEPTION 'Approval audit mismatch'; END IF;
 RAISE NOTICE 'PASS amendment, conflict, rejection and audit';
END $$;
ROLLBACK;
