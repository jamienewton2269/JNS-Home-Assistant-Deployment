"""Synthetic-only write workflow endpoint, isolated in club_manager_simtest."""
from uuid import UUID
from datetime import date, datetime
from contextlib import closing
from http.cookies import SimpleCookie
import json
import psycopg2
from psycopg2.extras import register_uuid
register_uuid()

ROUTES={
 '/sim/api/member':('SELECT simtest.new_member(%s,%s,%s,%s)',('name','email','category')),
 '/sim/api/rate':('SELECT simtest.set_amenity_weekly_rate(%s,%s::date,%s::bigint)',('effective_from','weekly_pence')),
 '/sim/api/request':('SELECT simtest.request_amenity(%s,%s::uuid,%s::uuid,%s::timestamptz,%s::timestamptz)',('member_id','location_id','starts','ends')),
 '/sim/api/approve':('SELECT simtest.approve_amenity(%s,%s::uuid)',('booking_id',))
}
def session_token(cookie_header):
    cookie=SimpleCookie()
    if len(cookie_header)>4096: raise PermissionError('Invalid cookie')
    cookie.load(cookie_header)
    item=cookie.get('__Host-club_session')
    if not item or not 40<=len(item.value)<=256: raise PermissionError('Session required')
    return item.value

def execute(connection_factory,path,method,cookie_header,body=None):
    token=session_token(cookie_header)
    if method=='GET':
        if path!='/sim/api/state':raise KeyError('Unknown read')
        statement,args='SELECT simtest.workflow_state(%s)',(token,)
    else:
        statement,fields=ROUTES[path]
        if not isinstance(body,dict) or set(body)!=set(fields):
            raise ValueError('Unexpected form fields')
        vals=[]
        for field in fields:
            value=body[field]
            if not isinstance(value,str) or len(value)>200:
                raise ValueError('Invalid form value')
            if field=='weekly_pence':
                if not value.isdecimal() or int(value)>100000000:
                    raise ValueError('Invalid price')
                value=int(value)
            vals.append(value)
        statement,args=statement,(token,*vals)
    with closing(connection_factory()) as db:
        with db:
            with db.cursor() as cur:
                cur.execute(statement,args)
                value=cur.fetchone()[0]
    return value
