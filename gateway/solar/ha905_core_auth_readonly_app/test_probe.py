#!/usr/bin/env python3
"""Offline-only permission and redaction tests for the JNS Core auth probe."""
import importlib.util
import pathlib
import urllib.error
import unittest
ROOT=pathlib.Path(__file__).parent
spec=importlib.util.spec_from_file_location("jns_auth_readonly",ROOT/"probe.py")
mod=importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
class Response:
 status=200
 def __enter__(self):return self
 def __exit__(self,*a):return None
 def read(self,*a):raise AssertionError("response body read")
class Tests(unittest.TestCase):
 def test_three_gets_token_and_zero_response_body_reads(self):
  calls=[]
  def opener(req,timeout):
   calls.append((req.full_url,req.get_method(),req.get_header("Authorization"),timeout,req.data))
   if req.get_method()=="POST" and b"jns_diagnostic_missing_required_handler" in req.data:
    raise urllib.error.HTTPError(req.full_url,400,"schema requires handler",{},None)
   if req.get_method()=="POST" and req.data==b'{"handler":"esphome"}':
    class FormResponse(Response):
     def read(self,*args):
      return b'{"type":"form","step_id":"user","flow_id":"01AN4Z07BY79KA1307SR9X4MV3","errors":{}}'
    return FormResponse()
   if req.get_method()=="DELETE":return Response()
   return Response()
  result=mod.run("FAKE_ONLY",opener)
  self.assertEqual(result,{"supervisor_info":200,"core_root":200,"core_config":200,
      "rejected_flow_post":400,"esphome_blank_flow_start":200,
      "esphome_blank_flow_cancel":200,"esphome_blank_form":True})
  self.assertEqual({(x[0],x[1]) for x in calls if x[1]=="GET"},{(url,"GET") for name,url in mod.ENDPOINTS})
  self.assertEqual(sum(x[1]=="POST" for x in calls),2)
  self.assertEqual(sum(x[1]=="DELETE" for x in calls),1)
  self.assertTrue(all(x[2]=="Bearer FAKE_ONLY" and x[3]<=8 for x in calls))
  self.assertNotIn(b'"handler"',next(x[4] for x in calls if x[1]=="POST"))
  self.assertTrue(all(b"host" not in (x[4] or b"") and b"noise_psk" not in (x[4] or b"") for x in calls))
 def test_missing_token_never_connects(self):
  def forbidden(*a,**k):raise AssertionError("network attempted")
  self.assertEqual(set(mod.run("",forbidden).values()),{"token_absent"})
 def test_http401_reported_no_fabricated_success(self):
  def rejected(req,timeout):
   raise urllib.error.HTTPError(req.full_url,401,"private information",{},None)
  out=mod.run("FAKE",rejected)
  self.assertEqual(out["core_root"],401)
  self.assertEqual(out["rejected_flow_post"],401)
  self.assertEqual(out["esphome_blank_flow_start"],401)
  self.assertEqual(out["esphome_blank_flow_cancel"],"not_attempted")
  self.assertIs(out["esphome_blank_form"],False)
 def test_unsafe_url_never_connects(self):
  with self.assertRaises(ValueError):
   mod.classify("http://supervisor/addons/self/start","FAKE")
 def test_minimal_addon_manifest_and_no_write_methods(self):
  cfg=(ROOT/"config.yaml").read_text()
  for word in ("homeassistant_api: true","hassio_api: false","boot: manual_only",
               "startup: once","full_access: false","host_network: false",
               "docker_api: false","ports: {}"):
   self.assertIn(word,cfg)
  for bad in ("ingress: true","hassio_api: true","privileged:"):
   self.assertNotIn(bad,cfg)
  src=(ROOT/"probe.py").read_text()
  self.assertEqual(src.count('method="POST"'),2)
  self.assertIn('url="http://supervisor/core/api/config/config_entries/flow"',src)
  self.assertIn("jns_diagnostic_missing_required_handler",src)
  for bad in ("method=\"PUT\"","method=\"DELETE\"","/services/","socket.","subprocess"):
   self.assertNotIn(bad,src)
  self.assertTrue((ROOT/"run.sh").read_bytes().startswith(b"#!/command/with-contenv bashio\n"))
 def test_only_expected_fixed_endpoints(self):
  self.assertEqual(tuple(name for name,_ in mod.ENDPOINTS),("supervisor_info","core_root","core_config"))
if __name__=="__main__":unittest.main(verbosity=2)
