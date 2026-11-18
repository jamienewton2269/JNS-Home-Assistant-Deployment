"""Synthetic finance tariff functions: role restricted to ITAdmin2.
Production club database and tariffs are never accessed.
"""
from contextlib import closing
from sim_workflow import session_token
def operate(db_factory,route,method,cookie,body=None):
 token=session_token(cookie)
 if method=='GET':
  if route!='/sim/finance/state': raise ValueError('Invalid route')
  statement,args='SELECT simtest.finance_rates(%s)',(token,)
 else:
  if not isinstance(body,dict):raise ValueError('JSON object required')
  if route=='/sim/finance/amenity':
   if set(body)!={'effective_from','weekly_pence'}:raise ValueError('Invalid form')
   date,amount=body['effective_from'],body['weekly_pence']
   if not isinstance(date,str) or not isinstance(amount,str) or not amount.isdecimal():raise ValueError('Invalid data')
   statement,args='SELECT simtest.set_amenity_weekly_rate(%s,%s::date,%s::bigint)',(token,date,int(amount))
  elif route=='/sim/finance/location':
   if set(body)!={'location_id','effective_from','weekly_pence'}:raise ValueError('Invalid form')
   location,date,amount=body['location_id'],body['effective_from'],body['weekly_pence']
   if not all(isinstance(v,str) for v in (location,date,amount)) or not amount.isdecimal():raise ValueError('Invalid location tariff')
   statement,args='SELECT simtest.set_location_weekly_rate(%s,%s::uuid,%s::date,%s::bigint)',(token,location,date,int(amount))
  elif route=='/sim/finance/tender':
   if set(body)!={'financial_year','amount_pence'}:raise ValueError('Invalid tender tariff')
   year,amount=body['financial_year'],body['amount_pence']
   if not isinstance(year,str) or not year.isdecimal() or not isinstance(amount,str) or not amount.isdecimal():raise ValueError('Invalid tender price')
   statement,args='SELECT simtest.set_tender_rate(%s,%s::integer,%s::bigint)',(token,int(year),int(amount))
  elif route=='/sim/finance/membership':
   if set(body)!={'financial_year','category','amount_pence'}:raise ValueError('Invalid form')
   year,category,amount=body['financial_year'],body['category'],body['amount_pence']
   if not isinstance(year,str) or not year.isdecimal() or not isinstance(category,str) or not isinstance(amount,str) or not amount.isdecimal():raise ValueError('Invalid data')
   statement,args='SELECT simtest.set_membership_rate(%s,%s::integer,%s,%s::bigint)',(token,int(year),category,int(amount))
  else:raise ValueError('Invalid route')
 with closing(db_factory()) as conn:
  with conn:
   with conn.cursor() as cur:
    cur.execute(statement,args)
    return cur.fetchone()[0]
