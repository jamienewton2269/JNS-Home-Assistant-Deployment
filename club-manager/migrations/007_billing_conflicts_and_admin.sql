BEGIN;
CREATE EXTENSION IF NOT EXISTS btree_gist;
-- Range constraints protect against concurrent approval races.
ALTER TABLE club.mooring_bookings
  DROP CONSTRAINT IF EXISTS mooring_no_approved_overlap;
ALTER TABLE club.mooring_bookings
  ADD CONSTRAINT mooring_no_approved_overlap
  EXCLUDE USING gist (location_id WITH =, tstzrange(starts_at,ends_at,'[)') WITH &&)
  WHERE (state IN ('approved','completed'));
ALTER TABLE club.facility_bookings
  DROP CONSTRAINT IF EXISTS facility_no_approved_overlap;
ALTER TABLE club.facility_bookings
  ADD CONSTRAINT facility_no_approved_overlap
  EXCLUDE USING gist (facility_id WITH =, tstzrange(starts_at,ends_at,'[)') WITH &&)
  WHERE (state = 'approved');
-- Approved allocations cannot conflict by asset, even at two distinct berths.
CREATE UNIQUE INDEX IF NOT EXISTS one_approved_mooring_per_asset_year
 ON club.mooring_allocations(asset_id,season_year) WHERE state='approved';
-- Bill from the stored measured length, without assuming any price or whole-foot rounding.
-- Rounds the monetary result to the nearest penny; no length rounding.
CREATE OR REPLACE FUNCTION club.preview_yard_charge(p_asset uuid,p_year integer)
RETURNS TABLE(asset_label text,rate_basis text,length_units numeric,rate_pence bigint,total_pence bigint)
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,club AS $$
DECLARE a record; t record; v_length numeric;
BEGIN
 SELECT * INTO a FROM club.yard_assets WHERE id=p_asset;
 IF NOT FOUND THEN RAISE EXCEPTION 'Unknown asset'; END IF;
 IF NOT a.stored_on_site THEN RAISE EXCEPTION 'Asset is not stored on site'; END IF;
 SELECT * INTO t FROM club.yard_tariffs WHERE financial_year=p_year AND asset_type=a.asset_type;
 IF NOT FOUND THEN RAISE EXCEPTION 'No approved yard rate for asset type and year'; END IF;
 v_length:=CASE WHEN t.rate_basis='foot' THEN a.length_metres / 0.3048 ELSE a.length_metres END;
 RETURN QUERY SELECT a.label,t.rate_basis,v_length,t.pence_per_unit,
   round(v_length*t.pence_per_unit,0)::bigint;
END $$;
CREATE OR REPLACE FUNCTION club.issue_yard_charge(p_asset uuid,p_year integer)
RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,club AS $$
DECLARE p record; t uuid; charge_id uuid;
BEGIN
 SELECT * INTO p FROM club.preview_yard_charge(p_asset,p_year);
 SELECT y.id INTO t FROM club.yard_tariffs y JOIN club.yard_assets a ON a.asset_type=y.asset_type
 WHERE a.id=p_asset AND y.financial_year=p_year;
 INSERT INTO club.yard_charges(asset_id,financial_year,tariff_id,measured_metres,charge_pence)
 SELECT a.id,p_year,t,a.length_metres,p.total_pence FROM club.yard_assets a WHERE id=p_asset
 ON CONFLICT (asset_id,financial_year) DO NOTHING RETURNING id INTO charge_id;
 IF charge_id IS NULL THEN RAISE EXCEPTION 'Annual charge already exists'; END IF;
 RETURN charge_id;
END $$;
-- Restrict DB write primitives to a named future officer service role; not prototype app.
DO $$ BEGIN
 IF NOT EXISTS(SELECT 1 FROM pg_roles WHERE rolname='club_officer') THEN
    CREATE ROLE club_officer NOLOGIN;
 END IF;
END $$;
GRANT USAGE ON SCHEMA club TO club_officer;
REVOKE EXECUTE ON FUNCTION club.preview_yard_charge(uuid,integer) FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION club.issue_yard_charge(uuid,integer) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION club.preview_yard_charge(uuid,integer) TO club_officer;
GRANT EXECUTE ON FUNCTION club.issue_yard_charge(uuid,integer) TO club_officer;
CREATE OR REPLACE FUNCTION club.admin_snapshot()
RETURNS jsonb LANGUAGE sql SECURITY DEFINER SET search_path=pg_catalog,club AS $$
 SELECT jsonb_build_object(
 'yard_assets',(SELECT count(*) FROM club.yard_assets),
 'approved_mooring_bookings',(SELECT count(*) FROM club.mooring_bookings WHERE state='approved'),
 'pending_mooring_requests',(SELECT count(*) FROM club.mooring_bookings WHERE state='requested'),
 'pending_facility_requests',(SELECT count(*) FROM club.facility_bookings WHERE state='requested'),
 'yard_tariffs',(SELECT coalesce(jsonb_agg(jsonb_build_object('year',financial_year,'asset_type',asset_type,'basis',rate_basis,'pence_per_unit',pence_per_unit) ORDER BY financial_year,asset_type),'[]'::jsonb) FROM club.yard_tariffs),
 'member_tariffs',(SELECT coalesce(jsonb_agg(jsonb_build_object('category',category,'annual_pence',annual_pence,'joining_pence',joining_pence) ORDER BY category),'[]'::jsonb) FROM club.membership_tariffs WHERE effective_until IS NULL)
 ) $$;
REVOKE EXECUTE ON FUNCTION club.admin_snapshot() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION club.admin_snapshot() TO clubmgr;
-- Never let the public or shared prototype account execute fee creation.
REVOKE ALL ON ALL TABLES IN SCHEMA club FROM PUBLIC,clubmgr;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA club FROM PUBLIC,clubmgr;
GRANT SELECT ON club.current_members TO clubmgr;
COMMIT;
