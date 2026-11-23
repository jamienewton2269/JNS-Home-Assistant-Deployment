BEGIN;
-- Working party participation and mooring seniority: append-only decisions.
-- Membership start date is the source of chronological seniority.
ALTER TABLE club.member_profiles
  ADD COLUMN IF NOT EXISTS joined_on date;
CREATE TABLE IF NOT EXISTS club.working_parties (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 title text NOT NULL CHECK (length(trim(title)) BETWEEN 1 AND 160),
 held_on date NOT NULL,
 description text NOT NULL DEFAULT '',
 created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE TABLE IF NOT EXISTS club.working_party_attendance (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 party_id uuid NOT NULL REFERENCES club.working_parties(id),
 member_id uuid NOT NULL REFERENCES club.member_profiles(id),
 status text NOT NULL CHECK(status IN ('attended','excused','absent','declined')),
 notes text NOT NULL DEFAULT '',
 recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 recorded_by text NOT NULL CHECK(length(trim(recorded_by))>0),
 UNIQUE(party_id,member_id)
);
CREATE TABLE IF NOT EXISTS club.seniority_decisions (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 member_id uuid NOT NULL REFERENCES club.member_profiles(id),
 effective_from date NOT NULL,
 effective_until date,
 decision text NOT NULL CHECK(decision IN ('suspend','reinstate')),
 reason text NOT NULL,
 authorised_by text NOT NULL,
 recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 CHECK(effective_until IS NULL OR effective_until >= effective_from),
 CHECK(length(trim(reason))>0),
 CHECK(length(trim(authorised_by))>0)
);
-- A missed working party must never automatically suspend seniority.
-- Explicit officer decision required; chronology is never reset.
CREATE OR REPLACE VIEW club.member_mooring_seniority AS
 SELECT m.id AS member_id, m.joined_on,
 EXISTS (
   SELECT 1 FROM club.seniority_decisions d
   WHERE d.member_id=m.id
     AND d.decision='suspend'
     AND d.effective_from<=CURRENT_DATE
     AND (d.effective_until IS NULL OR d.effective_until>=CURRENT_DATE)
     AND NOT EXISTS (
       SELECT 1 FROM club.seniority_decisions r
       WHERE r.member_id=m.id AND r.decision='reinstate'
         AND r.effective_from<=CURRENT_DATE
         AND r.effective_from>=d.effective_from
         AND r.recorded_at>d.recorded_at
     )
 ) AS seniority_suspended
 FROM club.member_profiles m;
-- No general application grants: add narrow, audited service functions after officer RBAC acceptance.
REVOKE ALL ON club.working_parties, club.working_party_attendance, club.seniority_decisions FROM PUBLIC;
REVOKE ALL ON club.member_mooring_seniority FROM PUBLIC;
COMMIT;
