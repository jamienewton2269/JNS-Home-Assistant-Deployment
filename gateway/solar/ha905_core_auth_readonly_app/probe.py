#!/usr/bin/env python3
"""Read-only HA905 Core API proxy test from a dedicated authorized app.

Exactly three fixed GET URLs; never print token, request body or response.
No configs, registry, POSTs, websockets, outputs or security integration calls.
"""
import json
import os
import re
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
def start_cancel_empty_esphome_flow(token,opener=urllib.request.urlopen):
 """Initialize ONLY the blank ESPHome user form, then delete that flow.

 Neither ESPHome host nor key is sent. No configure/submit step exists.
 Home Assistant's async_step_user(None) returns a form without hardware I/O.
 """
 if not token:return {"start":"token_absent","cancel":"not_attempted","blank_form":False}
 base="http://supervisor/core/api/config/config_entries/flow"
 req=urllib.request.Request(base,data=b'{"handler":"esphome"}',
     method="POST",headers={"Authorization":"Bearer "+token,
     "Content-Type":"application/json"})
 try:
  with opener(req,timeout=8) as response:
   start_status=response.status
   payload=response.read(12000)
 except urllib.error.HTTPError as e:
  return {"start":e.code if e.code in (400,401,403,404,405,409,422,429,500,502,503,504) else "other_status",
          "cancel":"not_attempted","blank_form":False}
 except (urllib.error.URLError,TimeoutError,OSError):
  return {"start":"transport_unavailable","cancel":"not_attempted","blank_form":False}
 # Never log or persist the form or flow identifier. Delete only a strict
 # validated ID returned by the actual Core flow-init endpoint.
 try:
  obj=json.loads(payload)
  flowid=obj.get("flow_id")
  clean=isinstance(flowid,str) and re.fullmatch(
      r"(?:[0-9A-HJKMNP-TV-Z]{26}|[0-9a-fA-F]{32})",flowid)
 except (ValueError,TypeError,AttributeError):clean=False
 if not clean:
  return {"start":start_status,"cancel":"identifier_invalid","blank_form":False}
 is_blank=(obj.get("type")=="form" and obj.get("step_id")=="user"
           and not obj.get("errors"))
 req=urllib.request.Request(base+"/"+flowid,method="DELETE",
     headers={"Authorization":"Bearer "+token})
 try:
  with opener(req,timeout=8) as response:
   cancel_status=response.status
 except urllib.error.HTTPError as e:
  cancel_status=e.code if e.code in (400,401,403,404,405,409,422,429,500,502,503,504) else "other_status"
 except (urllib.error.URLError,TimeoutError,OSError):
  cancel_status="transport_unavailable"
 return {"start":start_status,"cancel":cancel_status,"blank_form":is_blank}

def run(token,opener=urllib.request.urlopen):
 result={k:classify(v,token,opener) for k,v in ENDPOINTS}
 result["rejected_flow_post"]=invalid_flow_request(token,opener)
 flow=start_cancel_empty_esphome_flow(token,opener)
 result["esphome_blank_flow_start"]=flow["start"]
 result["esphome_blank_flow_cancel"]=flow["cancel"]
 result["esphome_blank_form"]=flow["blank_form"]
 return result
if __name__=="__main__":
 token=os.environ.get("SUPERVISOR_TOKEN","")
 print("JNS_HA905_CORE_AUTH_READONLY="+json.dumps({
    "token_present":bool(token),"statuses":run(token),
    "invalid_flow_post_sent":True,"no_device_details_sent":True,
    "used_security_output":False,"logged_token":False},sort_keys=True),flush=True)
