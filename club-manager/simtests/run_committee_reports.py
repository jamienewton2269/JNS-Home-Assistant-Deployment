"""Weekly or monthly completed-period committee snapshots, synthetic only."""
import sys,json
from datetime import date,timedelta
from zoneinfo import ZoneInfo
from datetime import datetime
from contextlib import closing
import psycopg2
if len(sys.argv)!=2 or sys.argv[1] not in ('weekly','monthly'):
 raise SystemExit('Expected weekly or monthly')
kind=sys.argv[1]
today=datetime.now(ZoneInfo('Europe/London')).date()
if kind=='weekly':
 end=today-timedelta(days=today.weekday())
 start=end-timedelta(days=7)
else:
 end=today.replace(day=1)
 start=(end-timedelta(days=1)).replace(day=1)
with closing(psycopg2.connect('dbname=club_manager_simtest user=clubbeta')) as db:
 with db:
  with db.cursor() as cur:
   cur.execute('SELECT simtest.generate_committee_finance_report(%s,%s,%s)',(kind,start,end))
   result=cur.fetchone()[0]
   print(json.dumps({'period':kind,'start':str(start),'end':str(end),'created':result['created'],
       'invoices':result['summary']['invoices_issued'],
       'outstanding_pence':result['summary']['outstanding_pence']},sort_keys=True),flush=True)
