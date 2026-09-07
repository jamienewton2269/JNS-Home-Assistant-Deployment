DOMAIN = "jns_deployment"
VERSION = "4.2.1"

CONF_INBOX = "inbox_path"
CONF_STAGING = "staging_path"
CONF_BACKUPS = "backup_path"

DEFAULT_INBOX = "jns/inbox"
DEFAULT_STAGING = "jns/staging"
DEFAULT_BACKUPS = "jns/backups"

PACKAGE_MANIFEST = "jns_package.json"
TRANSACTION_RECORD = "transaction.json"

MAX_PACKAGE_BYTES = 50 * 1024 * 1024
MAX_MEMBER_BYTES = 25 * 1024 * 1024
MAX_MEMBER_COUNT = 1000

ALLOWED_ROOTS = (
    "packages/",
    "custom_components/",
    "themes/",
    "www/jns/",
)
