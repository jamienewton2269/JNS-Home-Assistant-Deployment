BEGIN;
-- Configurable mooring seniority sanction policy. Run after migration 023.
CREATE TABLE IF NOT EXISTS club.mooring_seniority_policy (
 policy_id smallint PRIMARY KEY DEFAULT 1 CHECK(policy_id=1),
 default_sanction_months integer NOT NULL DEFAULT 6 CHECK(default_sanction_months BETWEEN 1 AND 36),
 updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 updated_by text NOT NULL DEFAULT 'migration-024'
);
INSERT INTO club.mooring_seniority_policy(policy_id) VALUES(1) ON CONFLICT DO NOTHING;
-- Existing explicit end dates remain authoritative. A missing end date
-- uses the configurable policy duration, not an indefinite sanction.
CREATE OR REPLACE VIEW club.member_mooring_seniority AS
 SELECT m.id AS member_id, m.joined_on,
 EXISTS (
   SELECT 1 FROM club.seniority_decisions d
   CROSS JOIN club.mooring_seniority_policy p
   WHERE d.member_id=m.id
     AND d.decision='suspend'
     AND d.effective_from<=CURRENT_DATE
     AND CURRENT_DATE < COALESCE(d.effective_until + 1,
             (d.effective_from + make_interval(months=>p.default_sanction_months))::date)
     AND NOT EXISTS (
       SELECT 1 FROM club.seniority_decisions r
       WHERE r.member_id=m.id AND r.decision='reinstate'
         AND r.effective_from<=CURRENT_DATE
         AND r.effective_from>=d.effective_from
         AND r.recorded_at>d.recorded_at
     )
 ) AS seniority_suspended
 FROM club.member_profiles m;
-- Allocation key: zero effective seniority while sanctioned, full
-- chronological seniority restored afterwards. Missing join dates
-- cannot silently gain priority.
CREATE OR REPLACE VIEW club.mooring_allocation_priority AS
 SELECT s.member_id,s.joined_on,s.seniority_suspended,
 CASE WHEN s.seniority_suspended OR s.joined_on IS NULL THEN 0
      ELSE GREATEST(0,CURRENT_DATE-s.joined_on) END AS effective_seniority_days
 FROM club.member_mooring_seniority s;
REVOKE ALL ON club.mooring_seniority_policy FROM PUBLIC;
REVOKE ALL ON club.mooring_allocation_priority FROM PUBLIC;
COMMIT;
