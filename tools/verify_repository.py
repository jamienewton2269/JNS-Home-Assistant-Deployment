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
    CC / "addon.py",
    CC / "services.yaml",
    CC / "management_pc.py",
    CC / "strings.json",
    CC / "translations" / "en.json",
    ROOT / "tools" / "jns_keygen.py",
    ROOT / "tools" / "jns_make_trust_store.py",
    ROOT / "tools" / "jns_sign_package.py",
    ROOT / "tools" / "jns_build_platform_update.py",
    ROOT / "tools" / "production_selftest.py",
    ROOT / "tools" / "config_check_semantics_selftest.py",
    ROOT / "repository.yaml",
    ROOT / "jns_secure_sftp" / "config.yaml",
    ROOT / "jns_secure_sftp" / "Dockerfile",
    ROOT / ".github" / "workflows" / "build_sftp_app.yml",
    ROOT / "jns_secure_sftp" / "rootfs" / "etc" / "services.d" / "sshd" / "run",
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
if manifest.get("version") != "5.5.3":
    raise SystemExit("Unexpected integration version")
if manifest.get("iot_class") != "local_push":
    raise SystemExit("Manifest IoT class must be local_push")
if manifest.get("codeowners") != ["@jamienewton2269"]:
    raise SystemExit("Unexpected codeowners")
if manifest.get("requirements") != []:
    raise SystemExit("Core cryptography dependency should not be duplicated.")

const_text = (CC / "const.py").read_text(encoding="utf-8")
for required_text in (
    'VERSION = "5.5.3"',
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


app_config = (ROOT / "jns_secure_sftp" / "config.yaml").read_text(encoding="utf-8")
for required_text in (
    'version: "0.4.0"',
    "slug: jns_secure_sftp",
    "image: ghcr.io/jamienewton2269/{arch}-jns-secure-sftp",
    "22/tcp: 2222",
    "type: homeassistant_config",
    "password_authentication: true",
):
    if required_text not in app_config:
        raise SystemExit(f"JNS SFTP app config missing: {required_text}")

image_workflow = (ROOT / ".github" / "workflows" / "build_sftp_app.yml").read_text(encoding="utf-8")
for required_text in (
    'VERSION: "0.4.0"',
    'matrix:',
    'arch: [amd64, aarch64]',
    'ghcr.io/${{ github.repository_owner }}/${{ matrix.arch }}-${{ env.IMAGE_NAME }}',
    'home-assistant/builder/actions/build-image@',
):
    if required_text not in image_workflow:
        raise SystemExit(f"JNS SFTP image workflow missing: {required_text}")

addon_text = (CC / "addon.py").read_text(encoding="utf-8")
for required_text in (
    "_REPOSITORY_READY_TIMEOUT = 60.0",
    "_APP_READY_TIMEOUT = 120.0",
    "_APP_START_TIMEOUT = 60.0",
    'await client.store.reload()',
    'await _async_wait_for_repository(hass)',
    'await _async_wait_for_app(hass, addon_slug)',
    'await _async_addon_snapshot(hass, addon_slug)',
    'await _async_addon_options(hass, addon_slug)',
    'f"addons/{addon_slug}/info"',
    'raise _provisioning_error("app_install", err)',
    'raise _provisioning_error("app_configure", err)',
    'raise _provisioning_error("app_start", err)',
):
    if required_text not in addon_text:
        raise SystemExit(f"Supervisor/SFTP production fix missing: {required_text}")
for forbidden_text in (
    "async_get_addon_info",
    ".addons.addon_info(",
    ".addons.addon_config(",
    "InstalledAddonComplete",
):
    if forbidden_text in addon_text:
        raise SystemExit(f"Strict Supervisor installed-add-on parsing returned: {forbidden_text}")

management_text = (CC / "management_pc.py").read_text(encoding="utf-8")
if "async_add_executor_job" not in management_text:
    raise SystemExit("Management-PC registry file I/O must use Home Assistant executor jobs")

config_flow_text = (CC / "config_flow.py").read_text(encoding="utf-8")
for label in (
    "Enrol a new management PC",
    "Manage JNS management PCs",
    "Legacy transport recovery",
):
    if label not in config_flow_text:
        raise SystemExit(f"Management security menu label missing: {label}")

run_script = (
    ROOT / "jns_secure_sftp" / "rootfs" / "etc" / "services.d" / "sshd" / "run"
).read_text(encoding="utf-8")
for required_text in (
    "ForceCommand internal-sftp",
    "DisableForwarding yes",
    "PermitRootLogin no",
    "ChrootDirectory",
    "server_host_ed25519.pub",
):
    if required_text not in run_script:
        raise SystemExit(f"JNS SFTP hardening missing: {required_text}")

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

print("JNS v5.5.3 repository static validation: PASS")
print("Manifest ordering/version/IoT class: PASS")
print("Mandatory signed-package policy: PASS")
print("Signing/key/recovery tooling present: PASS")
print("Brand/HACS workflow assets: PASS")
print("Python compilation: PASS")

print("Supervisor companion-app repository assets: PASS")
print("v5.4.3 Supervisor readiness/diagnostic fixes preserved: PASS")
print("v5.4.3 prebuilt architecture-specific SFTP image path preserved: PASS")
print("SFTP transport hardening static checks: PASS")
