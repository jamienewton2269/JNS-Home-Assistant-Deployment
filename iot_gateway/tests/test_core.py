import importlib.util
from pathlib import Path
import tempfile
import unittest

MODULE = Path(__file__).resolve().parents[1] / "core" / "jns_gateway.py"
spec = importlib.util.spec_from_file_location("jns_gateway", MODULE)
jg = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(jg)


class GatewayCoreTests(unittest.TestCase):
    def base_config(self):
        return {
            "node": {"id": "gw-test"},
            "profile": {"active": "zigbee_serial"},
            "hardware": {"radio_1": {"device": "/dev/serial/by-id/test-radio"}},
            "zigbee_serial": {"baudrate": 115200, "listen_port": 20108, "bind": "0.0.0.0"},
            "logging": {"syslog": {"enabled": False, "facility": "local5"}},
        }

    def zigbee_profile(self):
        return {"id": "zigbee_serial", "status": "implemented"}

    def test_validate_zigbee(self):
        jg.validate_config(self.base_config(), self.zigbee_profile())

    def test_requires_stable_by_id_path(self):
        cfg = self.base_config()
        cfg["hardware"]["radio_1"]["device"] = "/dev/ttyUSB0"
        with self.assertRaises(jg.GatewayError):
            jg.validate_config(cfg, self.zigbee_profile())

    def test_future_profile_is_not_silently_loaded(self):
        cfg = self.base_config()
        cfg["profile"]["active"] = "zigbee2mqtt"
        with self.assertRaises(jg.GatewayError):
            jg.validate_config(cfg, {"id": "zigbee2mqtt"})

    def test_ser2net_is_single_client_and_non_preemptive(self):
        rendered = jg.render_ser2net(self.base_config())
        self.assertIn("max-connections: 1", rendered)
        self.assertIn("kickolduser: false", rendered)
        self.assertIn("/dev/serial/by-id/test-radio", rendered)
        self.assertIn("tcp,20108", rendered)

    def test_rfc5424_contains_node_profile_and_event(self):
        cfg = self.base_config()
        cfg["logging"]["syslog"].update({"enabled": True, "server": "127.0.0.1"})
        msg = jg.build_rfc5424(cfg, "RADIO_CLAIMED", "info", {"radio": "abc"}, "claimed")
        self.assertIn("RADIO_CLAIMED", msg)
        self.assertIn('node="gw-test"', msg)
        self.assertIn('profile="zigbee_serial"', msg)
        self.assertIn('radio="abc"', msg)

    def test_spool_is_bounded(self):
        cfg = self.base_config()
        cfg["logging"]["syslog"].update({"enabled": True, "spool_max_events": 3})
        with tempfile.TemporaryDirectory() as td:
            spool = Path(td) / "spool.jsonl"
            for n in range(7):
                jg._spool_append(cfg, f"message-{n}", spool)
            lines = spool.read_text().splitlines()
            self.assertEqual(len(lines), 3)
            self.assertIn("message-6", lines[-1])
            self.assertNotIn("message-0", "\n".join(lines))

    def test_disabled_profile_has_no_protocol_requirements(self):
        cfg = self.base_config()
        cfg["profile"]["active"] = "disabled"
        jg.validate_config(cfg, {"id": "disabled"})


if __name__ == "__main__":
    unittest.main()
