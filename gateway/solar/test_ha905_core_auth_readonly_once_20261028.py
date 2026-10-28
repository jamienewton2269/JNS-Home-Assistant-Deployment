#!/usr/bin/env python3
"""Offline-only tests of safe Core auth probe executor. No VM or network access."""
import contextlib,importlib.util,io,pathlib,unittest
ROOT=pathlib.Path(__file__).parent
spec=importlib.util.spec_from_file_location(
 "auth_once",ROOT/"ha905_core_auth_readonly_once_20261028.py")
app=importlib.util.module_from_spec(spec);spec.loader.exec_module(app)
class Tests(unittest.TestCase):
 def test_only_known_get_statuses_are_accepted(self):
  self.assertIn(401,app.ALLOWED_STATUSES)
  self.assertNotIn(302,app.ALLOWED_STATUSES)
  self.assertNotIn("Bearer private",app.ALLOWED_STATUSES)
 def test_status_result_redacts_other_log_text(self):
  private="PRIVATE_NOT_TO_LOG"
  msg='{"token_present":true,"statuses":{"supervisor_info":200,"core_root":401,"core_config":403,"rejected_flow_post":400},"invalid_flow_post_sent":true,"handler_supplied":false,"used_security_output":false,"logged_token":false}'
  logs="INFO other field "+private+"\n2026-10-28 JNS_HA905_CORE_AUTH_READONLY="+msg+"\n"
  before=app.guest
  try:
   app.guest=lambda *a,**k:{"exitcode":0,"out-data":logs}
   buf=io.StringIO()
   with contextlib.redirect_stdout(buf):
    result=app.read_probe()
   self.assertEqual(result,{"supervisor_info":200,"core_root":401,"core_config":403,"rejected_flow_post":400})
   self.assertNotIn(private,buf.getvalue())
   self.assertNotIn("Bearer",buf.getvalue())
  finally:app.guest=before
 def test_missing_log_never_returns_success(self):
  before,wait=app.guest,app.time.sleep
  try:
   app.guest=lambda *a,**k:{"exitcode":0,"out-data":"no marker"}
   app.time.sleep=lambda x:None
   self.assertIsNone(app.read_probe())
  finally:app.guest,app.time.sleep=before,wait
 def test_untrusted_status_rejected(self):
  msg='{"token_present":true,"statuses":{"supervisor_info":200,"core_root":302,"core_config":200,"rejected_flow_post":400},"invalid_flow_post_sent":true,"handler_supplied":false,"used_security_output":false,"logged_token":false}'
  before,wait=app.guest,app.time.sleep
  try:
   app.guest=lambda *a,**k:{"exitcode":0,"out-data":"JNS_HA905_CORE_AUTH_READONLY="+msg}
   app.time.sleep=lambda x:None
   self.assertIsNone(app.read_probe())
  finally:app.guest,app.time.sleep=before,wait
 def test_installed_inventory_unknown_fails_closed(self):
  old=app.inventory
  try:
   app.inventory=lambda:None
   self.assertFalse(app.cleanup())
  finally:app.inventory=old
 def test_only_temporary_folder_removed(self):
  self.assertTrue(app.FOLDER.endswith("/jns_ha905_core_auth_readonly"))
  self.assertNotIn("jns_ha905_security_handover",app.FOLDER)
  self.assertTrue(app.SLUG.startswith("local_jns_ha905_core_auth_readonly"))
if __name__=="__main__":unittest.main(verbosity=2)
