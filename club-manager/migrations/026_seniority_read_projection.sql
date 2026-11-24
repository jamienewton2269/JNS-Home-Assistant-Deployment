BEGIN;
CREATE OR REPLACE FUNCTION club.api_seniority_for_officer(p_bearer text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,club AS $$
BEGIN
 IF NOT club.officer_session_authorized(p_bearer,'members_view') THEN
 RAISE EXCEPTION 'Access denied' USING ERRCODE='42501'; END IF;
 RETURN jsonb_build_object(
 'parties',COALESCE((SELECT jsonb_agg(to_jsonb(p) ORDER BY p.held_on DESC) FROM (SELECT id,title,held_on FROM club.working_parties) p),'[]'::jsonb),
 'members',COALESCE((SELECT jsonb_agg(to_jsonb(m)) FROM club.mooring_allocation_priority m),'[]'::jsonb),
 'default_months',(SELECT default_sanction_months FROM club.mooring_seniority_policy WHERE policy_id=1));
END $$;
REVOKE ALL ON FUNCTION club.api_seniority_for_officer(text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION club.api_seniority_for_officer(text) TO club_api_service;
COMMIT;
