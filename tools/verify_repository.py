from pathlib import Path
import json
import py_compile
import tempfile

ROOT = Path(__file__).resolve().parent.parent
CC = ROOT / "custom_components" / "jns_deployment"

required = [
    ROOT / "hacs.json",
    ROOT / "LICENSE",
    ROOT / "brand" / "icon.png",
    CC / "brand" / "icon.png",
    CC / "brand" / "logo.png",
    CC / "manifest.json",
    CC / "__init__.py",
    CC / "config_flow.py",
    CC / "deployment.py",
    CC / "services.yaml",
    CC / "strings.json",
    CC / "translations" / "en.json",
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
        "Manifest keys are not in Hassfest order. "
        f"Expected {expected_keys}; got {keys}"
    )

if manifest.get("version") != "4.2.3":
    raise SystemExit(
        f"Unexpected integration version: {manifest.get('version')!r}"
    )

if manifest.get("codeowners") != ["@jamienewton2269"]:
    raise SystemExit("Unexpected codeowners")

if manifest.get("iot_class") != "local_push":
    raise SystemExit(
        f"Unexpected IoT class: {manifest.get('iot_class')!r}"
    )

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
        raise SystemExit(
            f"Workflow missing required action: {required_action}"
        )

with tempfile.TemporaryDirectory() as tempdir:
    tempdir = Path(tempdir)
    for py_file in CC.glob("*.py"):
        py_compile.compile(
            str(py_file),
            cfile=str(tempdir / f"{py_file.stem}.pyc"),
            doraise=True,
        )

cache_dirs = list(ROOT.rglob("__pycache__"))
if cache_dirs:
    raise SystemExit(
        f"Python cache directory must not be committed: {cache_dirs[0]}"
    )

bytecode_files = list(ROOT.rglob("*.pyc"))
if bytecode_files:
    raise SystemExit(
        f"Python bytecode must not be committed: {bytecode_files[0]}"
    )

print("JNS v4.2.3 repository static validation: PASS")
print("Manifest ordering: PASS")
print("Integration version: PASS")
print("IoT class: PASS")
print("MIT licence completeness: PASS")
print("Local integration brand assets: PASS")
print("GitHub Action versions: PASS")
print("Python compilation: PASS")
