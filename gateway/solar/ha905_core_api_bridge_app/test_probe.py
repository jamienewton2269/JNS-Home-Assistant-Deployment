#!/usr/bin/env python3
"""Offline fail-closed regression tests for the dormant one-shot HA905 app."""
import importlib.util
import pathlib
import unittest
import urllib.error

ROOT = pathlib.Path(__file__).parent
spec = importlib.util.spec_from_file_location("jns_core_app_probe", ROOT / "probe.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class Response:
    status = 200
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return None
    def read(self, *args):
        raise AssertionError("reading API body is forbidden")


class ProbeTest(unittest.TestCase):
    def test_readonly_authenticated_core_probe(self):
        seen = []
        def fake(req, timeout):
            seen.append((req.full_url, req.get_method(),
                         req.get_header("Authorization"), timeout))
            return Response()
        result = module.run("TEST_ONLY", fake)
        self.assertEqual(result, {"core_root": 200, "core_config": 200})
        self.assertEqual([x[1] for x in seen], ["GET", "GET"])
        self.assertTrue(all(x[2] == "Bearer TEST_ONLY" for x in seen))
        self.assertTrue(all(x[3] <= 8 for x in seen))
        self.assertEqual({x[0] for x in seen}, set(module.ENDPOINTS.values()))
    def test_no_token_no_http(self):
        def forbidden(*args, **kwargs):
            raise AssertionError("network on missing token")
        self.assertEqual(module.run("", forbidden),
                         {"core_root": "no_app_token", "core_config": "no_app_token"})
    def test_untrusted_endpoint_rejected(self):
        with self.assertRaises(ValueError):
            module.get_status("http://supervisor/addons/self/start", "test")
    def test_auth_failure_does_not_forge_success(self):
        def unauth(req, timeout):
            raise urllib.error.HTTPError(req.full_url, 401, "denied", {}, None)
        self.assertEqual(module.run("test", unauth),
                         {"core_root": 401, "core_config": 401})
    def test_fixed_one_shot_minimal_privilege_manifest(self):
        contents=(ROOT/"config.yaml").read_text()
        for line in (
            "startup: once", "boot: manual_only", "homeassistant_api: true",
            "hassio_api: false", "hassio_role: default",
            "host_network: false", "full_access: false", "docker_api: false",
            "stdin: false", "ports: {}", "arch:", "  - amd64"):
            self.assertIn("\n"+line+"\n", "\n"+contents)
        self.assertNotIn("map:", contents)
        self.assertNotIn("privileged:", contents)
        self.assertNotIn("ingress: true", contents)
    def test_probe_has_no_mutation_api(self):
        src=(ROOT/"probe.py").read_text()
        self.assertNotIn("method=\"POST\"", src)
        self.assertNotIn("method=\"PUT\"", src)
        self.assertNotIn("method=\"DELETE\"", src)
        self.assertNotIn("config_entries/flow", src)
        self.assertNotIn("subprocess", src)
        self.assertNotIn("socket.", src)
    def test_image_contains_only_local_probe(self):
        dockerfile=(ROOT/"Dockerfile").read_text()
        self.assertIn("COPY probe.py /opt/jns/probe.py", dockerfile)
        self.assertIn('CMD ["/run.sh"]', dockerfile)
        self.assertIn('COPY run.sh /run.sh', dockerfile)
        self.assertIn('ghcr.io/home-assistant/base-python:3.14-alpine3.24', dockerfile)
        self.assertNotIn('apk', dockerfile)
        start=(ROOT/"run.sh").read_bytes()
        self.assertTrue(start.startswith(b"#!/command/with-contenv bashio\n"))
        self.assertNotIn(b"\r", start)
        self.assertNotIn("EXPOSE", dockerfile)


if __name__ == "__main__":
    unittest.main()
