from __future__ import annotations
from pathlib import Path
import importlib.util
ROOT = Path(__file__).resolve().parent.parent
MODULE = ROOT / "custom_components" / "jns_deployment" / "ha_config_check.py"
spec = importlib.util.spec_from_file_location("_jns_ha_config_check_test", MODULE)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)
summarize = module.summarize_config_check_result
class Item:
    def __init__(self, message): self.message = message
class FakeHomeAssistantConfig(dict):
    def __init__(self, *args, errors=None, warnings=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.errors = list(errors or [])
        self.warnings = list(warnings or [])
valid = FakeHomeAssistantConfig({"homeassistant": {}, "automation": [{"id":"example"}]}, errors=[], warnings=[])
assert bool(valid) is True
assert summarize(valid)["status"] == "passed"
warning = FakeHomeAssistantConfig({"homeassistant": {}}, errors=[], warnings=[Item("warning")])
assert summarize(warning)["status"] == "passed"
assert summarize(warning)["warnings"] == ["warning"]
invalid = FakeHomeAssistantConfig({"homeassistant": {}}, errors=[Item("error")], warnings=[])
assert summarize(invalid)["status"] == "failed"
try:
    summarize({"homeassistant": {}})
except TypeError:
    pass
else:
    raise AssertionError("Unexpected result type was not rejected")
print("JNS v5.0.1 Home Assistant config-check semantics: PASS")
print("Truthy valid HomeAssistantConfig is accepted: PASS")
print("Warnings remain non-fatal: PASS")
print("Actual result.errors trigger failure: PASS")
