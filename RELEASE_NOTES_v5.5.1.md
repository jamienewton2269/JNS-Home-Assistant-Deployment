# JNS Deployment Platform v5.5.1

## Management PC enrollment hotfix

- Fixes management-PC enrollment failing when Home Assistant Supervisor returns
  add-on data without the installed-only `hostname` field.
- Reads JNS Secure SFTP configuration through the dedicated
  `/addons/<slug>/options/config` API instead of relying on the full
  `InstalledAddonComplete` model when only app options are required.
- Preserves pre-v5.5 authorized keys during enrollment and continues to enforce
  public-key-only SFTP transport for enrolled management PCs.
- Reasserts the complete SFTP boot, network and authentication policy during
  configuration.
- Keeps an existing enrolled PC identity valid until a retry succeeds.
- Removes a newly created Home Assistant system identity when enrollment fails,
  preventing future failed attempts from leaving usable orphan credentials.

The one-time enrollment code remains single-use. If an enrollment attempt fails,
the administrator must generate a fresh code before retrying.
