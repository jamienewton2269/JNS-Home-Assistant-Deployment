#!/usr/bin/env python3
"""Offline proof that only native ESPHome config-flow endpoints are touched."""
import importlib.util
import pathlib
import unittest

ROOT=pathlib.Path(__file__).parent
spec=importlib.util.spec_from_file_location("jns_esphome_flow",ROOT/"flow.py")
mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
FID="01AN4Z07BY79KA1307SR9X4MV3"
LEGACY_FID="a"*32
CREDS={"host":"test-device.example.invalid","port":6053,
       "noise_psk":"X"*44,"password":""}

class FlowTests(unittest.TestCase):
    def test_encrypted_device_uses_native_forms_and_one_create(self):
        calls=[]
        response=[
          {"type":"form","flow_id":FID,"step_id":"user","errors":{}},
          {"type":"form","flow_id":FID,"step_id":"encryption_key","errors":{}},
          {"type":"create_entry","title":"test","result":{"entry_id":"example"}},
        ]
        def api(method,path,token,data=None):
            calls.append((method,path,token,data))
            return response.pop(0)
        self.assertTrue(mod.run_flow(CREDS,"TEST",api))
        self.assertEqual([c[0] for c in calls],["POST","POST","POST"])
        self.assertEqual(calls[0][3],{"handler":"esphome"})
        self.assertEqual(calls[1][3],{"host":CREDS["host"],"port":6053})
        self.assertEqual(calls[2][3],{"noise_psk":CREDS["noise_psk"]})
        self.assertFalse(response)
    def test_legacy_uuid_flow_id_remains_supported(self):
        responses=[
          {"type":"form","flow_id":LEGACY_FID,"step_id":"user","errors":{}},
          {"type":"form","flow_id":LEGACY_FID,"step_id":"encryption_key","errors":{}},
          {"type":"create_entry","title":"test","result":{"entry_id":"example"}},
        ]
        calls=[]
        def api(method,path,token,data=None):
            calls.append((method,path))
            return responses.pop(0)
        self.assertTrue(mod.run_flow(CREDS,"TEST",api))
        self.assertEqual(calls[1][1],mod.FLOW_PATH+"/"+LEGACY_FID)

    def test_current_ulid_flow_id_supported_and_case_sensitive(self):
        self.assertEqual(len(FID),26)
        self.assertTrue(mod.FLOW_ID_RE.fullmatch(FID))
        self.assertTrue(mod.FLOW_ID_RE.fullmatch(LEGACY_FID))
        for invalid in (
            FID.lower(), FID+"0", FID[:-1], "0"*26,
            "O"*26, "I"*26, "L"*26, "U"*26,
            "a"*26, "../../services", "../"+FID, FID+"/extra",
            "", "0"*33
        ):
            # "0"*26 is syntactically a valid ULID and is not a secret.
            if invalid == "0"*26:
                continue
            self.assertFalse(bool(mod.FLOW_ID_RE.fullmatch(invalid)),invalid)

    def test_request_never_calls_network_for_malformed_identifiers(self):
        def fail_network(*args,**kwargs):
            raise AssertionError("attempted unintended network request")
        for endpoint in (mod.FLOW_PATH+"/../services",
                         mod.FLOW_PATH+"/"+FID+"/extra",
                         mod.FLOW_PATH+"/"+"O"*26,
                         "services/alarm_control_panel/trigger"):
            with self.assertRaises(ValueError):
                mod.request("POST",endpoint,"TEST",{},opener=fail_network)

    def test_bad_encryption_never_creates_entry(self):
        calls=[]
        responses=[
          {"type":"form","flow_id":FID,"step_id":"user","errors":{}},
          {"type":"form","flow_id":FID,"step_id":"encryption_key","errors":{}},
          {"type":"form","flow_id":FID,"step_id":"encryption_key",
           "errors":{"base":"invalid_psk"}},
        ]
        def api(method,path,token,data=None):
            calls.append((method,path))
            return responses.pop(0) if method!="DELETE" else {}
        self.assertFalse(mod.run_flow(CREDS,"TEST",api))
        self.assertEqual(calls[-1],("DELETE",mod.FLOW_PATH+"/"+FID))
    def test_unexpected_step_not_silently_approved(self):
        calls=[]
        def api(method,path,token,data=None):
            calls.append(method)
            return {"type":"form","flow_id":FID,"step_id":"unknown","errors":{}}
        with self.assertRaises(SystemExit):
            mod.run_flow(CREDS,"TEST",api)
        self.assertEqual(calls,["POST","DELETE"])
    def test_unapproved_endpoint_fails(self):
        with self.assertRaises(ValueError):
            mod.request("POST","services/lock/lock", "TEST",{})
        with self.assertRaises(ValueError):
            mod.request("POST","config/config_entries/entry/delete","TEST",{})
        with self.assertRaises(ValueError):
            mod.request("PUT",mod.FLOW_PATH,"TEST",{})
    def test_app_is_nonpersistent_admin_permission_with_readonly_share(self):
        cfg=(ROOT/"config.yaml").read_text()
        for item in ("boot: manual_only","startup: once","homeassistant_api: true",
                     "hassio_api: false","host_network: false","full_access: false",
                     "docker_api: false","read_only: true","type: share","ports: {}"):
            self.assertIn(item,cfg)
        image=(ROOT/"Dockerfile").read_text()
        self.assertIn("ghcr.io/home-assistant/base-python:3.14-alpine3.24",image)
        self.assertNotIn("apk",image)
        self.assertNotIn("EXPOSE",image)
        run=(ROOT/"run.sh").read_bytes()
        self.assertTrue(run.startswith(b"#!/command/with-contenv bashio\n"))
        self.assertNotIn(b"\r",run)
    def test_no_output_or_registry_operations(self):
        src=(ROOT/"flow.py").read_text()
        self.assertNotIn("services/",src)
        self.assertNotIn("core.config_entries",src)
        self.assertNotIn("call_service",src)
        self.assertNotIn("alarm_control_panel/arm",src)

if __name__=="__main__":unittest.main()
