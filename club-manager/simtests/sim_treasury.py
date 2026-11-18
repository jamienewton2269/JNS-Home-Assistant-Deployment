"""SIMULATION ONLY: checkout preview tokens, refund/dispute events and treasurer summary.
No outbound provider API, no payment credentials, no genuine settlement source.
"""
from sim_workflow import session_token
from contextlib import closing
import hashlib,secrets,re,json
from uuid import UUID

PROVIDERS=('stripe','paypal','sumup','quickbooks_payments')
def query(factory,statement,args):
 with closing(factory()) as db:
  with db:
   with db.cursor() as cur:
    cur.execute(statement,args)
    return cur.fetchone()[0]

def operate(factory,path,method,cookie='',payload=None):
 if path=='/sim/checkout-preview' and method=='GET':
  if not isinstance(payload,str) or not re.fullmatch(r'[A-Za-z0-9_-]{40,100}',payload):
   return None
  return query(factory,'SELECT simtest.checkout_preview(%s)',(hashlib.sha256(payload.encode()).digest(),))
 token=session_token(cookie)
 if method=='GET':
  if path!='/sim/treasury/state': raise ValueError('Unknown query')
  return query(factory,'SELECT simtest.treasurer_state(%s)',(token,))
 if not isinstance(payload,dict): raise ValueError('Invalid body')
 if path=='/sim/treasury/import-settlements':
  if set(payload)!={'events'} or not isinstance(payload['events'],list) or not 1<=len(payload['events'])<=20:
   raise ValueError('Require 1–20 simulated settlement events')
  return query(factory,'SELECT simtest.import_settlement_events(%s,%s::jsonb)',(token,json.dumps(payload['events'])))
 if path=='/sim/treasury/import':
  if set(payload)!={'events'} or not isinstance(payload['events'],list) or not 1<=len(payload['events'])<=20:
   raise ValueError('Require 1–20 simulated provider events')
  batch=json.dumps(payload['events'])
  return query(factory,'SELECT simtest.import_provider_events(%s,%s::jsonb)',(token,batch))
 if path=='/sim/treasury/checkout':
  if set(payload)!={'fee_id','provider'} or payload['provider'] not in PROVIDERS: raise ValueError('Invalid checkout selection')
  UUID(payload['fee_id'])
  secret=secrets.token_urlsafe(32)
  link_id=query(factory,'SELECT simtest.create_checkout(%s,%s::uuid,%s,%s::bytea)',(token,payload['fee_id'],payload['provider'],hashlib.sha256(secret.encode()).digest()))
  return {'id':str(link_id),'url':'/sim/checkout?t='+secret}
 if path=='/sim/treasury/adjust':
  if set(payload)!={'receipt_id','event_type','event_id','amount_pence'}: raise ValueError('Invalid adjustment payload')
  if payload['event_type'] not in ('refund','dispute_open','dispute_resolved'):raise ValueError('Invalid event type')
  UUID(payload['receipt_id'])
  event=payload['event_id']
  amount=payload['amount_pence']
  if not isinstance(event,str) or not 5<=len(event)<=100 or not isinstance(amount,str) or not amount.isdecimal(): raise ValueError('Invalid adjustment values')
  item=query(factory,'SELECT simtest.record_adjustment(%s,%s::uuid,%s,%s,%s::bigint)',(token,payload['receipt_id'],payload['event_type'],event,int(amount)))
  return {'id':str(item)}
 raise ValueError('Unknown operation')
