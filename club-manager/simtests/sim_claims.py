"""Simulation-only General Committee access requests. No document retrieval."""
from contextlib import closing
from uuid import UUID
from sim_workflow import session_token
def process(factory,path,method,cookie,body=None):
 token=session_token(cookie)
 if method=='GET':
  if path!='/sim/claims/state':raise ValueError('Unknown read')
  sql,args='SELECT simtest.gc_claim_status(%s)',(token,)
 else:
  if not isinstance(body,dict):raise ValueError('Invalid request')
  if path=='/sim/claims/request':
   if set(body)!=set(('insurance_id','reference','reason')):raise ValueError('Invalid claim request')
   UUID(body['insurance_id'])
   if not all(isinstance(body[k],str) and len(body[k])<=1500 for k in body):
    raise ValueError('Invalid fields')
   sql,args='SELECT simtest.gc_claim_request(%s,%s::uuid,%s,%s)',(token,body['insurance_id'],body['reference'],body['reason'])
  elif path=='/sim/claims/approve':
   if set(body)!={'request_id'}:raise ValueError('Invalid approval')
   UUID(body['request_id'])
   sql,args='SELECT simtest.gc_claim_approve(%s,%s::uuid)',(token,body['request_id'])
  else:raise ValueError('Unknown operation')
 with closing(factory()) as connection:
  with connection:
   with connection.cursor() as c:
    c.execute(sql,args)
    value=c.fetchone()[0]
 return str(value) if isinstance(value,UUID) else value
