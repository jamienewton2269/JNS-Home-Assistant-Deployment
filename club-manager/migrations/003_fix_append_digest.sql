BEGIN;
CREATE OR REPLACE FUNCTION club.append_member(
  p_id uuid, p_name text, p_email text, p_category text, p_actor text
) RETURNS bigint
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, club
AS $$
DECLARE
  v_seq bigint;
  v_prev text;
  v_action text;
  v_payload jsonb;
  v_digest text;
BEGIN
  IF length(p_name) NOT BETWEEN 1 AND 120 OR length(p_email) NOT BETWEEN 3 AND 200
     OR position('@' in p_email) = 0
     OR p_category NOT IN ('Full','Family','Junior','Social')
     OR p_actor <> 'local-dev-admin' THEN
    RAISE EXCEPTION 'invalid development record';
  END IF;
  PERFORM pg_advisory_xact_lock(7812201);
  IF EXISTS (SELECT 1 FROM club.event_log WHERE member_id=p_id) THEN
    v_action := 'REVISE';
  ELSE
    v_action := 'CREATE';
  END IF;
  SELECT entry_hash INTO v_prev FROM club.event_log ORDER BY seq DESC LIMIT 1;
  v_prev := coalesce(v_prev, repeat('0',64));
  v_payload := jsonb_build_object('name',p_name,'email',p_email,'category',p_category);
  v_seq := nextval(pg_get_serial_sequence('club.event_log', 'seq'));
  v_digest := encode(public.digest(v_prev || '|' || v_seq::text || '|' || p_id::text || '|' ||
                           v_action || '|' || v_payload::text || '|' || p_actor, 'sha256'),'hex');
  INSERT INTO club.event_log(seq,prev_hash,entry_hash,member_id,action,payload,actor)
  OVERRIDING SYSTEM VALUE VALUES (v_seq,v_prev,v_digest,p_id,v_action,v_payload,p_actor);
  RETURN v_seq;
END $$;
COMMIT;
