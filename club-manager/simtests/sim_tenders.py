"""Additional tender allocations and annual charges: simulation DB exclusively."""
from contextlib import closing
from sim_workflow import session_token
from uuid import UUID

def operate(factory,route,method,cookie,body=None):
 token=session_token(cookie)
 if method=='GET':
  if route!='/sim/tenders/state':raise ValueError('Unknown tender state')
  statement,args='SELECT simtest.tender_state(%s)',(token,)
 else:
  if not isinstance(body,dict):raise ValueError('Invalid payload')
  if route=='/sim/tenders/allocate':
   if set(body)!={'member_id','label'}:raise ValueError('Invalid allocation')
   UUID(body['member_id'])
   if not isinstance(body['label'],str) or len(body['label'])>100:raise ValueError('Invalid label')
   statement,args='SELECT simtest.assign_tender(%s,%s::uuid,%s)',(token,body['member_id'],body['label'])
  elif route=='/sim/tenders/rate':
   if set(body)!={'year','amount_pence'}:raise ValueError('Invalid tariff')
   if not all(isinstance(body[k],str) and body[k].isdecimal() for k in ('year','amount_pence')):raise ValueError('Invalid price')
   statement,args='SELECT simtest.set_tender_rate(%s,%s::integer,%s::bigint)',(token,int(body['year']),int(body['amount_pence']))
  elif route=='/sim/tenders/invoice':
   if set(body)!={'year'} or not isinstance(body['year'],str) or not body['year'].isdecimal():raise ValueError('Invalid year')
   statement,args='SELECT simtest.generate_tender_charges(%s,%s::integer)',(token,int(body['year']))
  else:raise ValueError('Unknown tender operation')
 with closing(factory()) as conn:
  with conn:
   with conn.cursor() as cur:
    cur.execute(statement,args)
    return cur.fetchone()[0]
