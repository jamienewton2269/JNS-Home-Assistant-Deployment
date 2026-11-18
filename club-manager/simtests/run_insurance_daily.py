"""Synthetic-only insurance scan. No email delivery and no PDF retrieval."""
import json
from contextlib import closing
import psycopg2
with closing(psycopg2.connect('dbname=club_manager_simtest user=clubbeta')) as db:
 with db:
  with db.cursor() as cur:
   cur.execute('SELECT simtest.run_insurance_automation()')
   result=cur.fetchone()[0]
   cur.execute('SELECT simtest.vault_envelope_health()')
   vault=cur.fetchone()[0]
   print(json.dumps({'report_date':result['report_date'],
       'missing':result['summary']['missing'],
       'expiring':result['summary']['renewal_due'],
       'expired':result['summary']['expired'],
       'reminders_queued':result['reminders_queued'],
       'vault_envelopes':vault['total'],'vault_structural_issues':vault['structural_issues']},sort_keys=True),flush=True)
