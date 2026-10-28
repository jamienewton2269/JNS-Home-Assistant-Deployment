#!/usr/bin/env python3
"""Offline-only regressions for safe ESPHome flow diagnostic extraction.

No VM, SSH, API, credentials or on-device calls. The implementation under
test is imported as a module; its guarded main() is NEVER executed.
"""
import contextlib
import importlib.util
import io
import pathlib
import unittest

ROOT=pathlib.Path(__file__).parent
spec=importlib.util.spec_from_file_location(
    "jns_ha906_enrol_guard",ROOT/"ha906_to_905_esphome_enrol_guarded_20261028.py")
guard=importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)


class SafeLogClassifyTests(unittest.TestCase):
    def test_timestamp_prefixed_supervisor_log(self):
        raw="2026-10-28 18:41:50 INFO Supervisor JNS_ESP_HANDOVER_BLOCKED=unexpected_step\n"
        self.assertEqual(guard.classify_safe_flow_logs(raw),"blocked:unexpected_step")

    def test_plain_exception_diagnosed(self):
        self.assertEqual(
            guard.classify_safe_flow_logs("JNS_ESP_HANDOVER_FLOW_EXCEPTION_CLASS=HTTPError\n"),
            "flow_exception_class:HTTPError")

    def test_known_flow_auth_error(self):
        raw="[addon] JNS_ESP_HANDOVER_FLOW_ERROR_CODE=invalid_psk\r\n"
        self.assertEqual(guard.classify_safe_flow_logs(raw),"flow_error_code:invalid_psk")

    def test_known_abort_code(self):
        raw="2026-10-28T18:41:50Z JNS_ESP_HANDOVER_ABORT_REASON=already_configured\n"
        self.assertEqual(guard.classify_safe_flow_logs(raw),"abort_reason:already_configured")

    def test_multiple_lines_last_diagnostic_wins(self):
        raw=("INFO JNS_ESP_HANDOVER_FLOW_ERROR_CODE=invalid_auth\n"
             "INFO JNS_ESP_HANDOVER_BLOCKED=one_shot_already_attempted\n")
        self.assertEqual(guard.classify_safe_flow_logs(raw),"blocked:one_shot_already_attempted")

    def test_freeform_or_unknown_code_redacted(self):
        raw="INFO JNS_ESP_HANDOVER_ABORT_REASON=highlySensitiveUserName123\n"
        got=guard.classify_safe_flow_logs(raw)
        self.assertEqual(got,"abort_reason:unknown_code_redacted")
        self.assertNotIn("highlySensitive",got)

    def test_long_secret_and_urls_are_not_extracted(self):
        raw=("JNS_ESP_HANDOVER_FLOW_ERROR_CODE="+"A"*128+"\n"+
             "INFO NoiseKey=PRIVATE_SUPERVISOR_TOKEN host=hidden.home.arpa\n")
        self.assertIsNone(guard.classify_safe_flow_logs(raw))

    def test_substring_fake_marker_does_not_match(self):
        raw="FAKEJNS_ESP_HANDOVER_BLOCKED=unexpected_step\n"
        self.assertIsNone(guard.classify_safe_flow_logs(raw))

    def test_escape_suffix_and_non_string(self):
        self.assertEqual(
            guard.classify_safe_flow_logs(
                "INFO JNS_ESP_HANDOVER_BLOCKED=supervisor_token_absent\x1b[0m\n"),
            "blocked:supervisor_token_absent")
        self.assertIsNone(guard.classify_safe_flow_logs(None))

    def test_no_mutating_helper_called_by_classification(self):
        saved=(guard.ssh,guard.qga,guard.app_cleanup)
        def disallowed(*args,**kwargs):
            raise AssertionError("side effect in pure log parser")
        try:
            guard.ssh=guard.qga=guard.app_cleanup=disallowed
            self.assertEqual(
                guard.classify_safe_flow_logs(
                    "INFO JNS_ESP_HANDOVER_BLOCKED=private_enrolment_stage_missing\n"),
                "blocked:private_enrolment_stage_missing")
        finally:
            guard.ssh,guard.qga,guard.app_cleanup=saved

if __name__=="__main__":
    unittest.main(verbosity=2)
