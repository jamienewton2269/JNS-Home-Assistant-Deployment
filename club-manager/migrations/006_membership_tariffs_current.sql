BEGIN;
-- Rates supplied by the club remain in force pending the December General Meeting.
-- No future rate is automatically assumed or inserted.
CREATE TABLE IF NOT EXISTS club.membership_tariffs (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 category text NOT NULL,
 annual_pence bigint NOT NULL CHECK (annual_pence>=0),
 joining_pence bigint NOT NULL DEFAULT 0 CHECK (joining_pence>=0),
 effective_from date NOT NULL,
 effective_until date,
 source_note text NOT NULL,
 approved_by text NOT NULL,
 CHECK(effective_until IS NULL OR effective_until>=effective_from),
 UNIQUE(category,effective_from)
);
-- Effective in this system from the confirmation date; historical effective dates are not inferred.
-- Changes after GM need an explicit approved tariff.
INSERT INTO club.membership_tariffs(category,annual_pence,joining_pence,effective_from,source_note,approved_by)
VALUES
('Full',12000,5000,DATE '2026-11-02','BSC published membership application; unchanged pending December GM','Existing approved schedule'),
('Full Family',14000,5000,DATE '2026-11-02','BSC published membership application; unchanged pending December GM','Existing approved schedule'),
('Full Student',7000,5000,DATE '2026-11-02','BSC published membership application; unchanged pending December GM','Existing approved schedule'),
('House',4800,0,DATE '2026-11-02','BSC published membership application; unchanged pending December GM','Existing approved schedule'),
('House Family',5500,0,DATE '2026-11-02','BSC published membership application; unchanged pending December GM','Existing approved schedule')
ON CONFLICT (category,effective_from) DO NOTHING;
REVOKE ALL ON club.membership_tariffs FROM PUBLIC,clubmgr;
COMMIT;
