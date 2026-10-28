#!/usr/bin/env python3
"""Read-only HA905 Core API proxy test from a dedicated authorized app.

Exactly three fixed GET URLs; never print token, request body or response.
No configs, registry, POSTs, websockets, outputs or security integration calls.
"""
import json
import os
import urllib.error
import urllib.request

ENDPOINTS=(
 ("supervisor_info","http://supervisor/info"),
 ("core_root","http://supervisor/core/api/"),
 ("core_config","http://supervisor/core/api/config"),
)
def classify(url,token,opener=urllib.request.urlopen):
 if url not in [u for _,u in ENDPOINTS]:raise ValueError("unapproved_url")
 if not token:return "token_absent"
 req=urllib.request.Request(url,method="GET",
     headers={"Authorization":"Bearer "+token})
 try:
  with opener(req,timeout=8) as response:
   return response.status if response.status in (200,201,204,400,401,403,404,405,429,500,502,503,504) else "other_status"
 except urllib.error.HTTPError as e:
  return e.code if e.code in (400,401,403,404,405,429,500,502,503,504) else "other_status"
 except (urllib.error.URLError,TimeoutError,OSError):
  return "transport_unavailable"
def run(token,opener=urllib.request.urlopen):
 return {k:classify(v,token,opener) for k,v in ENDPOINTS}
if __name__=="__main__":
 token=os.environ.get("SUPERVISOR_TOKEN","")
 print("JNS_HA905_CORE_AUTH_READONLY="+json.dumps({
    "token_present":bool(token),"statuses":run(token),"read_only":True,
    "posted_config_flow":False,"used_security_output":False,
    "logged_token":False},sort_keys=True),flush=True)
