from pathlib import Path
import json
import py_compile
import tempfile

ROOT = Path(__file__).resolve().parent.parent
CC = ROOT / "custom_components" / "jns_deployment"

required = [
    ROOT / "hacs.json",
    ROOT / "LICENSE",
    CC / "brand" / "icon.png",
    CC / "brand" / "logo.png",
    CC / "manifest.json",
    CC / "__init__.py",
    CC / "config_flow.py",
    CC / "deployment.py",
    CC / "diagnostics.py",
    CC / "services.yaml",
    CC / "strings.json",
    CC / "translations" / "en.json",
    ROOT / "tools" / "security_selftest.py",
    ROOT / "tools" / "beta_selftest.py",
    ROOT / "BETA_TEST_PLAN.md",
]

for path in required:
    if not path.is_file():
        raise SystemExit(f"Missing required file: {path}")

for json_file in (
    ROOT / "hacs.json",
    CC / "manifest.json",
    CC / "strings.json",
    CC / "translations" / "en.json",
):
    json.loads(json_file.read_text(encoding="utf-8"))

manifest = json.loads(
    (CC / "manifest.json").read_text(encoding="utf-8")
)
keys = list(manifest)
expected_keys = ["domain", "name"] + sorted(
    key for key in keys if key not in {"domain", "name"}
)
if keys != expected_keys:
    raise SystemExit(
        f"Manifest key order invalid. Expected {expected_keys}; got {keys}"
    )

if manifest.get("version") != "4.3.0-beta.1":
    raise SystemExit(
        f"Unexpected integration version: {manifest.get('version')!r}"
    )
if manifest.get("iot_class") != "local_push":
    raise SystemExit("Manifest IoT class must be local_push")
if manifest.get("codeowners") != ["@jamienewton2269"]:
    raise SystemExit("Unexpected codeowners")

const_text = (CC / "const.py").read_text(encoding="utf-8")
if '"custom_components/"' in const_text.split("ALLOWED_ROOTS =", 1)[1].split(")", 1)[0]:
    raise SystemExit(
        "Unsigned format-1 package policy must not allow custom_components/"
    )
if "FORMAT_PLATFORM_UPDATE = 2" not in const_text:
    raise SystemExit("Platform-update format is missing")

license_text = (ROOT / "LICENSE").read_text(encoding="utf-8")
if "IN NO EVENT SHALL THE" not in license_text:
    raise SystemExit("MIT licence appears incomplete")

workflow = (
    ROOT / ".github" / "workflows" / "validate.yml"
).read_text(encoding="utf-8")
for required_action in (
    "actions/checkout@v7",
    "actions/setup-python@v7",
    "home-assistant/actions/hassfest@master",
    "hacs/action@main",
):
    if required_action not in workflow:
        raise SystemExit(f"Workflow missing {required_action}")

with tempfile.TemporaryDirectory() as tempdir:
    tempdir = Path(tempdir)
    for py_file in CC.glob("*.py"):
        py_compile.compile(
            str(py_file),
            cfile=str(tempdir / f"{py_file.stem}.pyc"),
            doraise=True,
        )

if list(ROOT.rglob("__pycache__")):
    raise SystemExit("Python cache directories must not be committed")
if list(ROOT.rglob("*.pyc")):
    raise SystemExit("Python bytecode must not be committed")

print("JNS v4.3.0-beta.1 repository static validation: PASS")
print("Manifest ordering/version/IoT class: PASS")
print("Unsigned package target policy: PASS")
print("Platform-update format presence: PASS")
print("MIT licence completeness: PASS")
print("Brand assets: PASS")
print("GitHub Action versions: PASS")
print("Python compilation: PASS")
