DOMAIN = "jns_deployment"
VERSION = "4.3.0-beta.1"

DEFAULT_INBOX = "jns/inbox"
DEFAULT_STAGING = "jns/staging"
DEFAULT_BACKUPS = "jns/backups"
DEFAULT_STATE = "jns/state"
DEFAULT_PLATFORM_UPDATES = "jns/platform_updates"

PACKAGE_MANIFEST = "jns_package.json"
TRANSACTION_RECORD = "transaction.json"
PENDING_PLATFORM_UPDATE = "pending_platform_update.json"

FORMAT_CONFIG_PACKAGE = 1
FORMAT_PLATFORM_UPDATE = 2

MAX_PACKAGE_BYTES = 50 * 1024 * 1024
MAX_MEMBER_BYTES = 25 * 1024 * 1024
MAX_TOTAL_UNCOMPRESSED_BYTES = 100 * 1024 * 1024
MAX_MEMBER_COUNT = 1000
MAX_COMPRESSION_RATIO = 200.0

# Unsigned format-1 packages cannot install executable Python.
ALLOWED_ROOTS = (
    "packages/",
    "themes/",
    "www/jns/",
)

ALLOWED_EXTENSIONS = {
    "packages/": {".yaml", ".yml"},
    "themes/": {".yaml", ".yml"},
    "www/jns/": {
        ".css", ".gif", ".html", ".ico", ".jpeg", ".jpg",
        ".js", ".json", ".png", ".svg", ".webp",
    },
}

PLATFORM_DOMAIN = "jns_deployment"
PLATFORM_TARGET_ROOT = "custom_components/jns_deployment/"
PLATFORM_REQUIRED_TARGETS = {
    "custom_components/jns_deployment/__init__.py",
    "custom_components/jns_deployment/const.py",
    "custom_components/jns_deployment/config_flow.py",
    "custom_components/jns_deployment/deployment.py",
    "custom_components/jns_deployment/manifest.json",
}
