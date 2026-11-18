"""Only synthetic payment operations; separate simulation DB."""
from sim_workflow import session_token
from contextlib import closing
import psycopg2
ROUTES={
 '/sim/payments/issue':('SELECT simtest.issue_fee(%s,%s::uuid,%s::uuid,%s,%s::bigint)',('member_id','booking_id','description','amount_pence')),
 '/sim/payments/provider':('SELECT simtest.provider_receipt(%s,%s::uuid,%s,%s,%s::bigint,%s::bigint)',('fee_id','provider','external_event_id','gross_pence','provider_fee_pence')),
 '/sim/payments/reconcile':('SELECT simtest.reconcile_receipt(%s,%s::uuid,%s,%s::bigint)',('receipt_id','payout_ref','bank_net_pence')),
}
def operate(db_factory,route,method,cookie,body=None):
 token=session_token(cookie)
 if method=='GET':
  if route!='/sim/payments/state':raise ValueError('Unknown route')
  statement='SELECT simtest.payment_state(%s)'
  vals=(token,)
 else:
  if route not in ROUTES:raise ValueError('Unknown write')
  statement,keys=ROUTES[route]
  if not isinstance(body,dict) or set(body)!=set(keys):
   raise ValueError('Unexpected form fields')
  values=[]
  for key in keys:
   value=body[key]
   if key=='booking_id' and value is None:
    values.append(None);continue
   if not isinstance(value,str) or len(value)>180:
    raise ValueError('Invalid field')
   if key in ('amount_pence','gross_pence','provider_fee_pence','bank_net_pence'):
    if not value.isdecimal():raise ValueError('Invalid amount')
    value=int(value)
   values.append(value)
  vals=(token,*values)
 with closing(db_factory()) as conn:
  with conn:
   with conn.cursor() as c:
    c.execute(statement,vals)
    value=c.fetchone()[0]
 return value
