BEGIN;
SELECT set_config('client_min_messages','notice',true);
DO $$
DECLARE
  m uuid := gen_random_uuid();
  v integer;
  e integer;
  d text;
  p text := repeat('0',64);
  r record;
BEGIN
  PERFORM club.append_member(m,'Synthetic Sailor','synthetic@example.invalid','Full','local-dev-admin');
  PERFORM club.append_member(m,'Synthetic Revised Sailor','synthetic@example.invalid','Social','local-dev-admin');
  SELECT version INTO v FROM club.current_members WHERE member_id=m;
  IF v <> 2 THEN RAISE EXCEPTION 'Expected version 2 got %',v; END IF;
  SELECT count(*) INTO e FROM club.audit_rows();
  IF e < 2 THEN RAISE EXCEPTION 'Expected at least two events'; END IF;
  FOR r IN SELECT * FROM club.audit_rows() ORDER BY seq LOOP
    IF r.prev_hash <> p THEN RAISE EXCEPTION 'Broken hash link at event %',r.seq; END IF;
    d := encode(digest(
      r.prev_hash||'|'||r.seq::text||'|'||r.member_id::text||'|'||r.action||'|'||r.payload||'|'||r.actor,
      'sha256'),'hex');
    IF d <> r.entry_hash THEN RAISE EXCEPTION 'Bad event digest at %',r.seq; END IF;
    p := r.entry_hash;
  END LOOP;
  BEGIN
    UPDATE club.event_log SET actor='malicious' WHERE member_id=m;
    RAISE EXCEPTION 'HISTORY MUTATION NOT BLOCKED';
  EXCEPTION WHEN raise_exception THEN
    IF SQLERRM = 'HISTORY MUTATION NOT BLOCKED' THEN RAISE; END IF;
    IF SQLERRM <> 'immutable history' THEN RAISE; END IF;
  END;
  RAISE NOTICE 'PASS: synthetic create/revise, current projection, hash-chain and mutation rejection';
END $$;
ROLLBACK;
