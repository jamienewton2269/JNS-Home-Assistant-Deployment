BEGIN;
CREATE TABLE IF NOT EXISTS club.officer_actions (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 action_kind text NOT NULL CHECK(action_kind IN ('membership_amendment','boat_amendment','mooring_booking','facility_booking','renewal_distribution','tariff_change')),
 subject_id uuid,
 request_json jsonb NOT NULL CHECK(jsonb_typeof(request_json)='object'),
 requested_by text NOT NULL CHECK(length(trim(requested_by))>0),
 state text NOT NULL DEFAULT 'pending' CHECK(state IN ('pending','approved','rejected','cancelled')),
 reviewed_by text,
 reviewed_at timestamptz,
 review_note text,
 requested_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 CHECK ((state='pending' AND reviewed_by IS NULL AND reviewed_at IS NULL)
    OR (state<>'pending' AND reviewed_by IS NOT NULL AND reviewed_at IS NOT NULL)),
 CHECK (reviewed_by IS NULL OR reviewed_by<>requested_by)
);
CREATE INDEX IF NOT EXISTS officer_actions_pending_idx
 ON club.officer_actions(requested_at) WHERE state='pending';
CREATE TABLE IF NOT EXISTS club.officer_action_events (
 seq bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 action_id uuid NOT NULL REFERENCES club.officer_actions(id),
 event_kind text NOT NULL CHECK(event_kind IN ('requested','approved','rejected','cancelled')),
 actor text NOT NULL,
 happened_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE OR REPLACE FUNCTION club.officer_action_protect() RETURNS trigger
 LANGUAGE plpgsql SET search_path=pg_catalog,club AS $$
BEGIN
 IF TG_OP='DELETE' THEN RAISE EXCEPTION 'Officer action deletion prohibited'; END IF;
 IF NEW.id<>OLD.id OR NEW.action_kind<>OLD.action_kind OR
    NEW.subject_id IS DISTINCT FROM OLD.subject_id OR
    NEW.request_json<>OLD.request_json OR NEW.requested_by<>OLD.requested_by OR
    NEW.requested_at<>OLD.requested_at THEN
   RAISE EXCEPTION 'Submitted officer action is immutable';
 END IF;
 IF OLD.state<>'pending' OR NEW.state NOT IN ('approved','rejected','cancelled')
 THEN RAISE EXCEPTION 'Invalid officer action state transition'; END IF;
 IF NEW.reviewed_by IS NULL OR NEW.reviewed_by=OLD.requested_by OR NEW.reviewed_at IS NULL
 THEN RAISE EXCEPTION 'Independent review required'; END IF;
 RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS officer_action_guard ON club.officer_actions;
CREATE TRIGGER officer_action_guard BEFORE UPDATE OR DELETE ON club.officer_actions
 FOR EACH ROW EXECUTE FUNCTION club.officer_action_protect();
CREATE OR REPLACE FUNCTION club.officer_event_append() RETURNS trigger
 LANGUAGE plpgsql SET search_path=pg_catalog,club AS $$
BEGIN
 IF TG_OP='INSERT' THEN
   INSERT INTO club.officer_action_events(action_id,event_kind,actor) VALUES(NEW.id,'requested',NEW.requested_by);
 ELSIF TG_OP='UPDATE' THEN
   INSERT INTO club.officer_action_events(action_id,event_kind,actor) VALUES(NEW.id,NEW.state,NEW.reviewed_by);
 END IF;
 RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS officer_action_event_trigger ON club.officer_actions;
CREATE TRIGGER officer_action_event_trigger AFTER INSERT OR UPDATE ON club.officer_actions
 FOR EACH ROW EXECUTE FUNCTION club.officer_event_append();
CREATE OR REPLACE FUNCTION club.officer_action_events_immutable() RETURNS trigger
 LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'Officer action event history immutable'; END $$;
DROP TRIGGER IF EXISTS officer_events_guard ON club.officer_action_events;
CREATE TRIGGER officer_events_guard BEFORE UPDATE OR DELETE ON club.officer_action_events
 FOR EACH ROW EXECUTE FUNCTION club.officer_action_events_immutable();
-- No application role is granted direct access. A per-officer identity and RBAC gate
-- must be implemented and validated before granting EXECUTE on any mutation wrapper.
REVOKE ALL ON club.officer_actions,club.officer_action_events FROM PUBLIC,clubmgr;
REVOKE ALL ON SEQUENCE club.officer_action_events_seq_seq FROM PUBLIC,clubmgr;
REVOKE EXECUTE ON FUNCTION club.officer_action_protect() FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION club.officer_event_append() FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION club.officer_action_events_immutable() FROM PUBLIC;
COMMIT;
