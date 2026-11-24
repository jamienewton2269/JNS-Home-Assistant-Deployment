BEGIN;
DO $test$
DECLARE
 m uuid;
 p uuid;
 original_days integer;
BEGIN
 SELECT id INTO STRICT m FROM club.member_profiles ORDER BY id LIMIT 1;
 UPDATE club.member_profiles SET joined_on=CURRENT_DATE-3650 WHERE id=m;
 DELETE FROM club.seniority_decisions WHERE member_id=m;
 SELECT effective_seniority_days INTO original_days FROM club.mooring_allocation_priority WHERE member_id=m;
 IF original_days<>3650 THEN RAISE EXCEPTION 'Baseline seniority failed'; END IF;
 INSERT INTO club.working_parties(title,held_on) VALUES('Synthetic acceptance test',CURRENT_DATE) RETURNING id INTO p;
 INSERT INTO club.working_party_attendance(party_id,member_id,status,recorded_by) VALUES(p,m,'declined','synthetic-test');
 IF (SELECT seniority_suspended FROM club.member_mooring_seniority WHERE member_id=m) THEN RAISE EXCEPTION 'Attendance incorrectly triggered sanction'; END IF;
 INSERT INTO club.seniority_decisions(member_id,effective_from,decision,reason,authorised_by) VALUES(m,CURRENT_DATE,'suspend','Synthetic test','synthetic-test');
 IF (SELECT effective_seniority_days FROM club.mooring_allocation_priority WHERE member_id=m)<>0 THEN RAISE EXCEPTION 'Zero seniority failed'; END IF;
 INSERT INTO club.seniority_decisions(member_id,effective_from,decision,reason,authorised_by) VALUES(m,CURRENT_DATE,'reinstate','Synthetic test','synthetic-test');
 IF (SELECT effective_seniority_days FROM club.mooring_allocation_priority WHERE member_id=m)<>original_days THEN RAISE EXCEPTION 'Reinstatement failed'; END IF;
 DELETE FROM club.seniority_decisions WHERE member_id=m;
 INSERT INTO club.seniority_decisions(member_id,effective_from,decision,reason,authorised_by) VALUES(m,(CURRENT_DATE-interval '7 months')::date,'suspend','Synthetic expired test','synthetic-test');
 IF (SELECT effective_seniority_days FROM club.mooring_allocation_priority WHERE member_id=m)<>original_days THEN RAISE EXCEPTION 'Expiry failed'; END IF;
 UPDATE club.mooring_seniority_policy SET default_sanction_months=12 WHERE policy_id=1;
 IF (SELECT default_sanction_months FROM club.mooring_seniority_policy WHERE policy_id=1)<>12 THEN RAISE EXCEPTION 'Policy write failed'; END IF;
 RAISE NOTICE 'PASS: joining date, attendance, zero seniority, reinstatement, expiry and policy write';
END
$test$;
ROLLBACK;
