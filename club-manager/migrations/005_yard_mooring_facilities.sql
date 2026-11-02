BEGIN;
CREATE TABLE IF NOT EXISTS club.yard_assets (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 member_id uuid NOT NULL REFERENCES club.member_profiles(id),
 asset_type text NOT NULL CHECK(asset_type IN ('boat','yard_trailer')),
 label text NOT NULL CHECK(length(trim(label))>0),
 length_metres numeric(9,3) NOT NULL CHECK(length_metres>0),
 stored_on_site boolean NOT NULL DEFAULT true,
 created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS club.yard_tariffs (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 financial_year integer NOT NULL CHECK(financial_year BETWEEN 2020 AND 2200),
 asset_type text NOT NULL CHECK(asset_type IN ('boat','yard_trailer')),
 rate_basis text NOT NULL CHECK(rate_basis IN ('foot','metre')),
 pence_per_unit bigint NOT NULL CHECK(pence_per_unit>=0),
 approved_by text NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(financial_year, asset_type)
);
CREATE TABLE IF NOT EXISTS club.yard_charges (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 asset_id uuid NOT NULL REFERENCES club.yard_assets(id),
 financial_year integer NOT NULL,
 tariff_id uuid NOT NULL REFERENCES club.yard_tariffs(id),
 measured_metres numeric(9,3) NOT NULL CHECK(measured_metres>0),
 charge_pence bigint NOT NULL CHECK(charge_pence>=0),
 state text NOT NULL DEFAULT 'draft' CHECK(state IN ('draft','approved','invoiced','void')),
 UNIQUE(asset_id,financial_year)
);
CREATE TABLE IF NOT EXISTS club.mooring_locations (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 designation text NOT NULL UNIQUE,
 mooring_type text NOT NULL CHECK(mooring_type IN ('allocated','amenity','emergency')),
 active boolean NOT NULL DEFAULT true
);
CREATE TABLE IF NOT EXISTS club.mooring_allocations (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 location_id uuid NOT NULL REFERENCES club.mooring_locations(id),
 asset_id uuid NOT NULL REFERENCES club.yard_assets(id),
 season_year integer NOT NULL,
 valid_from date NOT NULL,
 valid_until date NOT NULL,
 state text NOT NULL DEFAULT 'proposed' CHECK(state IN ('proposed','approved','cancelled')),
 CHECK(valid_from<=valid_until),
 CHECK(EXTRACT(YEAR FROM valid_from)=season_year AND EXTRACT(YEAR FROM valid_until)=season_year),
 CHECK(valid_from>=make_date(season_year,3,1) AND valid_until<=make_date(season_year,11,30))
);
CREATE UNIQUE INDEX IF NOT EXISTS one_approved_seasonal_allocation
 ON club.mooring_allocations(location_id, season_year) WHERE state='approved';
CREATE TABLE IF NOT EXISTS club.mooring_bookings (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 location_id uuid NOT NULL REFERENCES club.mooring_locations(id),
 member_id uuid NOT NULL REFERENCES club.member_profiles(id),
 asset_id uuid REFERENCES club.yard_assets(id),
 starts_at timestamptz NOT NULL,
 ends_at timestamptz NOT NULL,
 state text NOT NULL DEFAULT 'requested' CHECK(state IN ('requested','approved','rejected','cancelled','completed')),
 tariff_mode text NOT NULL DEFAULT 'flat' CHECK(tariff_mode IN ('flat','metered')),
 flat_fee_pence bigint CHECK(flat_fee_pence>=0),
 meter_start numeric(15,3), meter_end numeric(15,3),
 meter_rate_pence bigint CHECK(meter_rate_pence>=0),
 created_at timestamptz NOT NULL DEFAULT now(),
 CHECK(ends_at>starts_at),
 CHECK(meter_end IS NULL OR (meter_start IS NOT NULL AND meter_end>=meter_start)),
 CHECK(tariff_mode <> 'metered' OR flat_fee_pence IS NULL)
);
CREATE TABLE IF NOT EXISTS club.clubhouse_facilities (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 name text NOT NULL UNIQUE, active boolean NOT NULL DEFAULT true
);
CREATE TABLE IF NOT EXISTS club.facility_bookings (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 facility_id uuid NOT NULL REFERENCES club.clubhouse_facilities(id),
 requested_by uuid REFERENCES club.member_profiles(id),
 event_title text NOT NULL,
 starts_at timestamptz NOT NULL, ends_at timestamptz NOT NULL,
 state text NOT NULL DEFAULT 'requested' CHECK(state IN ('requested','approved','rejected','cancelled')),
 fee_pence bigint CHECK(fee_pence>=0),
 CHECK(ends_at>starts_at)
);
-- Public users and the existing prototype identity must not access these tables.
REVOKE ALL ON ALL TABLES IN SCHEMA club FROM PUBLIC,clubmgr;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA club FROM PUBLIC,clubmgr;
GRANT SELECT ON club.current_members TO clubmgr;
COMMIT;
