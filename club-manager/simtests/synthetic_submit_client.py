"""Test client for restricted synthetic member insurance submission over stdin."""
import json,sys,psycopg2
m=json.load(sys.stdin)
try:
 with psycopg2.connect('dbname=club_manager_simtest user=clubsubmit') as db:
  with db.cursor() as cur:
   cur.execute('select simtest.member_submit_insurance_synthetic(%s,%s,%s)',
    (m['token'],m['vessel'],m['key']))
   result=cur.fetchone()[0]
 print(json.dumps(result))
except Exception:
 print(json.dumps({'accepted':False,'reason':'db_rejected'}))
 sys.exit(1)
