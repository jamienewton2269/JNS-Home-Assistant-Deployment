DOMAIN = "jns_deployment"
VERSION = "5.5.2"

DEFAULT_INBOX = "jns/sftp/incoming"

# HACS bootstrap / Supervisor-managed transport
JNS_REPOSITORY_URL = "https://github.com/jamienewton2269/JNS-Home-Assistant-Deployment"
SFTP_APP_SLUG = "jns_secure_sftp"
SFTP_APP_NAME = "JNS Secure SFTP"
SFTP_APP_PORT = 2222
SFTP_USERNAME = "jnstransfer"
SFTP_MIN_PASSWORD_LENGTH = 24
CONF_SFTP_PASSWORD = "sftp_password"
CONF_SFTP_ADDON_SLUG = "sftp_addon_slug"
CONF_SFTP_CREATED_BY_INTEGRATION = "sftp_created_by_integration"
DEFAULT_STAGING = "jns/staging"
DEFAULT_BACKUPS = "jns/backups"
DEFAULT_STATE = "jns/state"
DEFAULT_PLATFORM_UPDATES = "jns/platform_updates"
DEFAULT_TRUST = "jns/trust"
DEFAULT_AUDIT = "jns/audit"
DEFAULT_QUARANTINE = "jns/quarantine"
DEFAULT_RECOVERY = "jns/recovery"

PACKAGE_MANIFEST = "jns_package.json"
PACKAGE_SIGNATURE = "jns_signature.json"
TRANSACTION_RECORD = "transaction.json"
PENDING_PLATFORM_UPDATE = "pending_platform_update.json"
TRUST_STORE_FILE = "publishers.json"
AUDIT_FILE = "audit.jsonl"
OPERATION_LOCK_FILE = "operation.lock"

SIGNED_PACKAGE_FORMAT = 3
SIGNATURE_ALGORITHM = "ed25519"
SIGNATURE_DOMAIN = b"JNS-PACKAGE-V3\x00"

MAX_PACKAGE_BYTES = 50 * 1024 * 1024
MAX_MEMBER_BYTES = 25 * 1024 * 1024
MAX_TOTAL_UNCOMPRESSED_BYTES = 100 * 1024 * 1024
MAX_MEMBER_COUNT = 1000
MAX_COMPRESSION_RATIO = 200.0
MIN_FREE_SPACE_RESERVE = 64 * 1024 * 1024

ALLOW_UNSIGNED_PACKAGES = False

CONFIG_ALLOWED_ROOTS = (
    "packages/",
    "themes/",
    "www/jns/",
)

CONFIG_ALLOWED_EXTENSIONS = {
    "packages/": {".yaml", ".yml"},
    "themes/": {".yaml", ".yml"},
    "www/jns/": {
        ".css", ".gif", ".html", ".ico", ".jpeg", ".jpg",
        ".js", ".json", ".png", ".svg", ".webp",
    },
}


INTEGRATION_DOMAIN_RE = r"^jns_[a-z0-9_]{1,59}$"
INTEGRATION_ALLOWED_EXTENSIONS = {
    ".py", ".json", ".yaml", ".yml", ".png", ".svg", ".ico", ".jpg", ".jpeg", ".webp",
}

PLATFORM_DOMAIN = "jns_deployment"
PLATFORM_TARGET_ROOT = "custom_components/jns_deployment/"
PLATFORM_REQUIRED_TARGETS = {
    "custom_components/jns_deployment/__init__.py",
    "custom_components/jns_deployment/const.py",
    "custom_components/jns_deployment/config_flow.py",
    "custom_components/jns_deployment/deployment.py",
    "custom_components/jns_deployment/manifest.json",
    "custom_components/jns_deployment/security.py",
    "custom_components/jns_deployment/audit.py",
    "custom_components/jns_deployment/recovery_tool.py",
    "custom_components/jns_deployment/diagnostics.py",
    "custom_components/jns_deployment/addon.py",
    "custom_components/jns_deployment/ha_config_check.py",
    "custom_components/jns_deployment/management_pc.py",
    "custom_components/jns_deployment/services.yaml",
}
