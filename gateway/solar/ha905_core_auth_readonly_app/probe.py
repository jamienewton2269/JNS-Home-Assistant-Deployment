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
def invalid_flow_request(token,opener=urllib.request.urlopen):
 """Test POST authorization without creating any configuration flow.

 Core 2026.9.4 config_entries/flow requires the handler field. Deliberately
 omit it; schema validation must reject this fixed payload before flow init.
 No valid integration ID, device address, key, password or output is sent.
 """
 if not token:return "token_absent"
 url="http://supervisor/core/api/config/config_entries/flow"
 payload=b'{"jns_diagnostic_missing_required_handler":true}'
 req=urllib.request.Request(url,data=payload,method="POST",
     headers={"Authorization":"Bearer "+token,"Content-Type":"application/json"})
 try:
  with opener(req,timeout=8) as response:
   # HTTP 2xx would mean our negative test did not reject and MUST NOT
   # count as a permission success. Do not read response data.
   return response.status if response.status in (200,201,204,400,401,403,404,405,422,429,500,502,503,504) else "other_status"
 except urllib.error.HTTPError as e:
  return e.code if e.code in (400,401,403,404,405,422,429,500,502,503,504) else "other_status"
 except (urllib.error.URLError,TimeoutError,OSError):
  return "transport_unavailable"
def run(token,opener=urllib.request.urlopen):
 result={k:classify(v,token,opener) for k,v in ENDPOINTS}
 result["rejected_flow_post"]=invalid_flow_request(token,opener)
 return result
if __name__=="__main__":
 token=os.environ.get("SUPERVISOR_TOKEN","")
 print("JNS_HA905_CORE_AUTH_READONLY="+json.dumps({
    "token_present":bool(token),"statuses":run(token),"read_only":True,
    "posted_config_flow":False,"used_security_output":False,
    "logged_token":False},sort_keys=True),flush=True)
