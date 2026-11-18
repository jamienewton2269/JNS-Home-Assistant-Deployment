"""Isolated Yard/Boat Manager QR registration, trailer inspections.
All owner/inspection results require authorised simulation officer session.
"""
from contextlib import closing
from uuid import UUID
from datetime import date
from sim_workflow import session_token
from sim_labels import issue as issue_label, lookup as lookup_label, png as qr_png

def query(factory,sql,args):
 with closing(factory()) as conn:
  with conn:
   with conn.cursor() as cur:
    cur.execute(sql,args)
    return cur.fetchone()[0]

def operation(factory,path,method,cookie='',body=None):
 if method=='GET' and path=='/sim/ybm/assets':
  return query(factory,'SELECT simtest.ybm_assets(%s)',(session_token(cookie),))
 if method=='GET' and path=='/sim/ybm/history':
  if not isinstance(body,str) or len(body)>48:raise ValueError('Invalid registration')
  return query(factory,'SELECT simtest.ybm_inspection_history(%s,%s)',(session_token(cookie),body))
 if method=='GET' and path=='/sim/ybm/lookup':
  return lookup_label(factory,cookie,body)
 if method!='POST' or not isinstance(body,dict):raise ValueError('Invalid request')
 if path=='/sim/ybm/issue':
  if set(body)!={'registration'}:raise ValueError('Invalid request')
  return issue_label(factory,cookie,body['registration'])
 if path=='/sim/ybm/inspect':
  if set(body)!={'registration','outcome','notes','next_due'}:raise ValueError('Unexpected inspection fields')
  reg,outcome,notes,due=(body[x] for x in ('registration','outcome','notes','next_due'))
  if not isinstance(reg,str) or not isinstance(outcome,str) or not isinstance(notes,str) or len(notes)>1000:
   raise ValueError('Invalid inspection fields')
  if due is not None:
   if not isinstance(due,str):raise ValueError('Invalid next inspection date')
   date.fromisoformat(due)
  id=query(factory,'SELECT simtest.record_ybm_inspection(%s,%s,%s,%s,%s::date)',(session_token(cookie),reg,outcome,notes,due))
  return {'inspection_id':str(id)}
 raise ValueError('Unknown YBM operation')
