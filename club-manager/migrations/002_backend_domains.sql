BEGIN;
CREATE SCHEMA IF NOT EXISTS club;
CREATE TABLE IF NOT EXISTS club.households(
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), label text NOT NULL CHECK(length(label) BETWEEN 1 AND 120),
 created_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE IF NOT EXISTS club.member_profiles(
 id uuid PRIMARY KEY, household_id uuid REFERENCES club.households(id),
 category text NOT NULL CHECK(category IN ('Full','Family','Junior','Social','Honorary')),
 status text NOT NULL DEFAULT 'applicant' CHECK(status IN ('applicant','pending_approval','active','lapsed','resigned','suspended','erasure_pending','erased')),
 version integer NOT NULL DEFAULT 1 CHECK(version>0),
 updated_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE IF NOT EXISTS club.member_history(
 seq bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 member_id uuid NOT NULL,
 version integer NOT NULL,
 change_kind text NOT NULL,
 actor text NOT NULL,
 details jsonb NOT NULL,
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 UNIQUE(member_id,version));
CREATE TABLE IF NOT EXISTS club.vessels(
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), member_id uuid NOT NULL REFERENCES club.member_profiles(id),
 name text NOT NULL, sail_number text, length_metres numeric(7,2) CHECK(length_metres>0),
 created_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE IF NOT EXISTS club.fee_rules(
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), category text NOT NULL,
 financial_year integer NOT NULL CHECK(financial_year BETWEEN 2020 AND 2200),
 amount_pence bigint NOT NULL CHECK(amount_pence>=0), currency char(3) NOT NULL DEFAULT 'GBP',
 approved_by text NOT NULL, approved_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(category,financial_year));
CREATE TABLE IF NOT EXISTS club.invoices(
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), member_id uuid NOT NULL REFERENCES club.member_profiles(id),
 external_ref text UNIQUE, amount_pence bigint NOT NULL CHECK(amount_pence>=0),
 currency char(3) NOT NULL DEFAULT 'GBP',
 state text NOT NULL DEFAULT 'draft' CHECK(state IN ('draft','issued','paid','part_paid','void','disputed')),
 created_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE IF NOT EXISTS club.payment_events(
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), invoice_id uuid NOT NULL REFERENCES club.invoices(id),
 provider text NOT NULL, provider_event_id text NOT NULL, amount_pence bigint NOT NULL CHECK(amount_pence>=0),
 received_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(provider,provider_event_id));
CREATE TABLE IF NOT EXISTS club.sync_inbox(
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 source text NOT NULL CHECK(source IN ('joomla','accounting')),
 source_event_id text NOT NULL, subject_ref text,
 event_type text NOT NULL, encrypted_payload bytea,
 state text NOT NULL DEFAULT 'pending' CHECK(state IN ('pending','validated','rejected','applied','expired')),
 received_at timestamptz NOT NULL DEFAULT now(), processed_at timestamptz,
 UNIQUE(source,source_event_id));
CREATE TABLE IF NOT EXISTS club.sync_outbox(
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), destination text NOT NULL CHECK(destination IN ('joomla','accounting')),
 event_type text NOT NULL, restricted_payload jsonb NOT NULL,
 state text NOT NULL DEFAULT 'pending' CHECK(state IN ('pending','dispatched','acknowledged','failed')),
 created_at timestamptz NOT NULL DEFAULT now(), acknowledged_at timestamptz);
CREATE TABLE IF NOT EXISTS club.privacy_requests(
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), member_id uuid REFERENCES club.member_profiles(id),
 kind text NOT NULL CHECK(kind IN ('access','erasure','rectification','restriction','portability')),
 state text NOT NULL DEFAULT 'received' CHECK(state IN ('received','identity_check','review','approved','refused','completed')),
 requested_at timestamptz NOT NULL DEFAULT now(), deadline_at timestamptz NOT NULL,
 reviewed_by text, approval_reference text, completed_at timestamptz,
 CHECK(deadline_at >= requested_at));
CREATE TABLE IF NOT EXISTS club.security_incidents(
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), kind text NOT NULL,
 severity text NOT NULL CHECK(severity IN ('info','warning','critical')),
 state text NOT NULL DEFAULT 'open', observed_at timestamptz NOT NULL DEFAULT now(),
 evidence_digest text NOT NULL);
CREATE TABLE IF NOT EXISTS club.governance_approvals(
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), action text NOT NULL, requested_by text NOT NULL,
 approved_by text NOT NULL, approved_at timestamptz NOT NULL DEFAULT now(),
 CHECK(approved_by <> requested_by));
-- Deny ordinary application credentials direct table access.
REVOKE ALL ON ALL TABLES IN SCHEMA club FROM PUBLIC, clubmgr;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA club FROM PUBLIC, clubmgr;
-- Preserve existing narrow application contracts.
GRANT SELECT ON club.current_members TO clubmgr;
GRANT EXECUTE ON FUNCTION club.append_member(uuid,text,text,text,text) TO clubmgr;
GRANT EXECUTE ON FUNCTION club.audit_rows() TO clubmgr;
-- Baseline history protection. Independent immutable archive is a separate workstream.
CREATE OR REPLACE FUNCTION club.deny_history_mutation() RETURNS trigger
LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'history is append-only'; END $$;
DROP TRIGGER IF EXISTS member_history_guard ON club.member_history;
CREATE TRIGGER member_history_guard BEFORE UPDATE OR DELETE ON club.member_history
FOR EACH ROW EXECUTE FUNCTION club.deny_history_mutation();
COMMIT;
