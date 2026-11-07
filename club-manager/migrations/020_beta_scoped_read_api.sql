BEGIN;
-- Limited beta read projections. No direct table grants, write functions or
-- payment provider operations are introduced.
CREATE OR REPLACE FUNCTION club.api_moorings_for_officer(p_bearer text)
RETURNS jsonb LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,club AS $$
DECLARE result jsonb;
BEGIN
 IF NOT club.officer_session_authorized(p_bearer,'moorings_manage') THEN
  RAISE EXCEPTION 'Access denied' USING ERRCODE='42501';
 END IF;
 SELECT jsonb_build_object(
   'yard_assets',(SELECT count(*) FROM club.yard_assets),
   'locations',(SELECT COALESCE(jsonb_agg(to_jsonb(x)),'[]'::jsonb)
      FROM (SELECT designation,mooring_type,active FROM club.mooring_locations
            ORDER BY designation LIMIT 100) x),
   'bookings',(SELECT COALESCE(jsonb_agg(to_jsonb(x)),'[]'::jsonb)
      FROM (SELECT b.id,l.designation,b.starts_at,b.ends_at,b.state,
                   b.tariff_mode
            FROM club.mooring_bookings b
            JOIN club.mooring_locations l ON l.id=b.location_id
            ORDER BY b.starts_at DESC LIMIT 100) x),
   'allocations',(SELECT count(*) FROM club.mooring_allocations WHERE state='approved')
 ) INTO result;
 RETURN result;
END $$;

CREATE OR REPLACE FUNCTION club.api_clubhouse_for_officer(p_bearer text)
RETURNS jsonb LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,club AS $$
DECLARE result jsonb;
BEGIN
 IF NOT club.officer_session_authorized(p_bearer,'clubhouse_manage') THEN
  RAISE EXCEPTION 'Access denied' USING ERRCODE='42501';
 END IF;
 SELECT jsonb_build_object(
  'facilities',(SELECT COALESCE(jsonb_agg(to_jsonb(x)),'[]'::jsonb)
      FROM (SELECT name,active FROM club.clubhouse_facilities
            ORDER BY name LIMIT 100) x),
  'bookings',(SELECT COALESCE(jsonb_agg(to_jsonb(x)),'[]'::jsonb)
      FROM (SELECT b.id,f.name AS facility,b.event_title,b.starts_at,b.ends_at,
                   b.state,b.fee_pence
            FROM club.facility_bookings b
            JOIN club.clubhouse_facilities f ON f.id=b.facility_id
            ORDER BY b.starts_at DESC LIMIT 100) x)
 ) INTO result;
 RETURN result;
END $$;

CREATE OR REPLACE FUNCTION club.api_renewals_for_officer(p_bearer text)
RETURNS jsonb LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,club AS $$
DECLARE result jsonb;
BEGIN
 IF NOT club.officer_session_authorized(p_bearer,'renewals_manage') THEN
  RAISE EXCEPTION 'Access denied' USING ERRCODE='42501';
 END IF;
 SELECT jsonb_build_object(
  'campaigns',(SELECT COALESCE(jsonb_agg(to_jsonb(x)),'[]'::jsonb)
      FROM (SELECT renewal_year,state FROM club.renewal_campaigns
            ORDER BY renewal_year DESC LIMIT 20) x),
  'invoice_counts',(SELECT COALESCE(jsonb_object_agg(state,n),'{}'::jsonb)
      FROM (SELECT state,count(*) AS n FROM club.renewal_invoices GROUP BY state) x),
  'invoiced_pence',(SELECT COALESCE(sum(amount_pence),0) FROM club.renewal_invoices
     WHERE state NOT IN ('void')),
  'paid_pence',(SELECT COALESCE(sum(amount_paid_pence),0) FROM club.renewal_invoices
     WHERE state NOT IN ('void'))
 ) INTO result;
 RETURN result;
END $$;

CREATE OR REPLACE FUNCTION club.api_committee_for_officer(p_bearer text)
RETURNS jsonb LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,club AS $$
DECLARE result jsonb;
BEGIN
 IF NOT club.officer_session_authorized(p_bearer,'accounts_grant') THEN
  RAISE EXCEPTION 'Access denied' USING ERRCODE='42501';
 END IF;
 SELECT jsonb_build_object(
  'accounts',(SELECT COALESCE(jsonb_agg(to_jsonb(x)),'[]'::jsonb)
      FROM (SELECT a.id,a.display_name,a.account_state,
                   (SELECT COALESCE(jsonb_agg(r.role_code),'[]'::jsonb)
                    FROM club.committee_role_grants r WHERE r.account_id=a.id) AS roles
            FROM club.committee_accounts a
            ORDER BY a.created_at DESC LIMIT 100) x)
 ) INTO result;
 RETURN result;
END $$;

CREATE OR REPLACE FUNCTION club.api_security_for_officer(p_bearer text)
RETURNS jsonb LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,club AS $$
DECLARE result jsonb;
BEGIN
 IF NOT club.officer_session_authorized(p_bearer,'audit_view') THEN
  RAISE EXCEPTION 'Access denied' USING ERRCODE='42501';
 END IF;
 SELECT jsonb_build_object(
   'preferred_factor',p.preferred_factor,
   'fallback_factor',p.fallback_factor,
   'minimum_independent_approvers',p.minimum_independent_approvers,
   'privileged_session_minutes',p.privileged_session_minutes,
   'pending_approval_requests',(SELECT count(*) FROM club.security_change_requests
     WHERE status='pending' AND expires_at>clock_timestamp())
 ) INTO result FROM club.security_policy p WHERE p.singleton=true;
 RETURN COALESCE(result,'{}'::jsonb);
END $$;

REVOKE EXECUTE ON FUNCTION club.api_moorings_for_officer(text)
 FROM PUBLIC,clubmgr,club_authz_service,club_authn_service;
REVOKE EXECUTE ON FUNCTION club.api_clubhouse_for_officer(text)
 FROM PUBLIC,clubmgr,club_authz_service,club_authn_service;
REVOKE EXECUTE ON FUNCTION club.api_renewals_for_officer(text)
 FROM PUBLIC,clubmgr,club_authz_service,club_authn_service;
REVOKE EXECUTE ON FUNCTION club.api_committee_for_officer(text)
 FROM PUBLIC,clubmgr,club_authz_service,club_authn_service;
REVOKE EXECUTE ON FUNCTION club.api_security_for_officer(text)
 FROM PUBLIC,clubmgr,club_authz_service,club_authn_service;
GRANT EXECUTE ON FUNCTION club.api_moorings_for_officer(text) TO club_api_service;
GRANT EXECUTE ON FUNCTION club.api_clubhouse_for_officer(text) TO club_api_service;
GRANT EXECUTE ON FUNCTION club.api_renewals_for_officer(text) TO club_api_service;
GRANT EXECUTE ON FUNCTION club.api_committee_for_officer(text) TO club_api_service;
GRANT EXECUTE ON FUNCTION club.api_security_for_officer(text) TO club_api_service;
COMMIT;
