BEGIN;
CREATE TABLE IF NOT EXISTS club.seniority_write_audit (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 officer_id uuid NOT NULL REFERENCES club.committee_accounts(id),
 operation text NOT NULL, target_id uuid,
 recorded_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
REVOKE ALL ON club.seniority_write_audit FROM PUBLIC,club_api_service,clubmgr;
CREATE OR REPLACE FUNCTION club.api_seniority_write(p_bearer text,p_action text,p_data jsonb)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,club AS $$
DECLARE actor uuid; target uuid; months integer; start_day date; end_day date;
BEGIN
 IF NOT club.officer_session_authorized(p_bearer,
 CASE WHEN p_action IN ('policy','decision') THEN 'moorings_manage' ELSE 'members_amend' END)
 THEN RAISE EXCEPTION 'Access denied' USING ERRCODE='42501'; END IF;
 SELECT account_id INTO STRICT actor FROM club.officer_api_sessions
 WHERE bearer_sha256=public.digest(convert_to(p_bearer,'UTF8'),'sha256')
 AND revoked_at IS NULL AND expires_at>clock_timestamp();
 CASE p_action
 WHEN 'join' THEN
  UPDATE club.member_profiles SET joined_on=(p_data->>'joined_on')::date
  WHERE id=(p_data->>'member_id')::uuid RETURNING id INTO STRICT target;
 WHEN 'party' THEN
  INSERT INTO club.working_parties(title,held_on) VALUES(p_data->>'title',(p_data->>'held_on')::date) RETURNING id INTO target;
 WHEN 'attendance' THEN
  INSERT INTO club.working_party_attendance(party_id,member_id,status,recorded_by)
  VALUES((p_data->>'party_id')::uuid,(p_data->>'member_id')::uuid,p_data->>'status',actor::text) RETURNING id INTO target;
 WHEN 'decision' THEN
  start_day:=(p_data->>'effective_from')::date;
  end_day:=NULLIF(p_data->>'effective_until','')::date;
  IF p_data->>'decision'='suspend' AND end_day IS NULL THEN
   SELECT default_sanction_months INTO STRICT months FROM club.mooring_seniority_policy WHERE policy_id=1;
   end_day:=(start_day+make_interval(months=>months))::date-1;
  END IF;
  INSERT INTO club.seniority_decisions(member_id,decision,effective_from,effective_until,reason,authorised_by)
  VALUES((p_data->>'member_id')::uuid,p_data->>'decision',start_day,end_day,p_data->>'reason',actor::text) RETURNING id INTO target;
 WHEN 'policy' THEN
  UPDATE club.mooring_seniority_policy SET default_sanction_months=(p_data->>'months')::integer,updated_at=clock_timestamp(),updated_by=actor::text WHERE policy_id=1;
 ELSE RAISE EXCEPTION 'Unknown operation' USING ERRCODE='22023';
 END CASE;
 INSERT INTO club.seniority_write_audit(officer_id,operation,target_id) VALUES(actor,p_action,target);
 RETURN jsonb_build_object('saved',true,'id',target);
END $$;
REVOKE ALL ON FUNCTION club.api_seniority_write(text,text,jsonb) FROM PUBLIC,clubmgr,club_authn_service,club_authz_service;
GRANT EXECUTE ON FUNCTION club.api_seniority_write(text,text,jsonb) TO club_api_service;
COMMIT;
