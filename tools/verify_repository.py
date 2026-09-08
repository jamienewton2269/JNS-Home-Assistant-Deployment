from pathlib import Path
import json
import py_compile
import tempfile

ROOT = Path(__file__).resolve().parent.parent
CC = ROOT / "custom_components" / "jns_deployment"

required = [
    ROOT / "hacs.json",
    ROOT / "LICENSE",
    ROOT / "SECURITY.md",
    ROOT / "PRODUCTION_ACCEPTANCE.md",
    CC / "brand" / "icon.png",
    CC / "brand" / "logo.png",
    CC / "manifest.json",
    CC / "__init__.py",
    CC / "ha_config_check.py",
    CC / "config_flow.py",
    CC / "deployment.py",
    CC / "security.py",
    CC / "audit.py",
    CC / "recovery_tool.py",
    CC / "diagnostics.py",
    CC / "services.yaml",
    CC / "strings.json",
    CC / "translations" / "en.json",
    ROOT / "tools" / "jns_keygen.py",
    ROOT / "tools" / "jns_make_trust_store.py",
    ROOT / "tools" / "jns_sign_package.py",
    ROOT / "tools" / "jns_build_platform_update.py",
    ROOT / "tools" / "production_selftest.py",
    ROOT / "tools" / "config_check_semantics_selftest.py",
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

manifest = json.loads((CC / "manifest.json").read_text(encoding="utf-8"))
keys = list(manifest)
expected_keys = ["domain", "name"] + sorted(
    key for key in keys if key not in {"domain", "name"}
)
if keys != expected_keys:
    raise SystemExit(
        f"Manifest key order invalid. Expected {expected_keys}; got {keys}"
    )
if manifest.get("version") != "5.0.1":
    raise SystemExit("Unexpected integration version")
if manifest.get("iot_class") != "local_push":
    raise SystemExit("Manifest IoT class must be local_push")
if manifest.get("codeowners") != ["@jamienewton2269"]:
    raise SystemExit("Unexpected codeowners")
if manifest.get("requirements") != []:
    raise SystemExit("Core cryptography dependency should not be duplicated.")

const_text = (CC / "const.py").read_text(encoding="utf-8")
for required_text in (
    "SIGNED_PACKAGE_FORMAT = 3",
    "ALLOW_UNSIGNED_PACKAGES = False",
    'SIGNATURE_ALGORITHM = "ed25519"',
):
    if required_text not in const_text:
        raise SystemExit(f"Missing production constant: {required_text}")

workflow = (ROOT / ".github" / "workflows" / "validate.yml").read_text(
    encoding="utf-8"
)
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
    for py_file in list(CC.glob("*.py")) + list((ROOT / "tools").glob("*.py")):
        py_compile.compile(
            str(py_file),
            cfile=str(tempdir / f"{py_file.stem}.pyc"),
            doraise=True,
        )

if list(ROOT.rglob("__pycache__")):
    raise SystemExit("Python cache directories must not be committed")
if list(ROOT.rglob("*.pyc")):
    raise SystemExit("Python bytecode must not be committed")

print("JNS v5.0.1 repository static validation: PASS")
print("Manifest ordering/version/IoT class: PASS")
print("Mandatory signed-package policy: PASS")
print("Signing/key/recovery tooling present: PASS")
print("Brand/HACS workflow assets: PASS")
print("Python compilation: PASS")
