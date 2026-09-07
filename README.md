# JNS Home Assistant Deployment Platform v4.2.1

JNS is a deployment/configuration/rollback layer for Home Assistant. This repository
contains the HACS-installable Home Assistant integration and the local transactional
deployment executor.

## Security model

Deployment ZIP files are untrusted by default.

JNS v4.2:
- accepts ZIP files only from `/config/jns/inbox`;
- accepts a filename, never an arbitrary filesystem path;
- rejects path traversal and absolute archive paths;
- rejects symbolic links;
- rejects undeclared archive files;
- verifies SHA-256 for every deployed file;
- restricts targets to approved Home Assistant roots;
- stages and re-verifies files before commit;
- saves rollback copies before overwriting live files;
- never executes package-provided shell commands or Python scripts as part of deployment.

Remote management consoles should use standard SSH/SFTP to transfer deployment ZIPs
into `/config/jns/inbox`. Do not place SSH passwords, Home Assistant tokens, GitHub
passwords, or other secrets in this repository.


## Test status

This archive has passed local static checks (Python compilation, JSON parsing and
example-package SHA-256 verification). The included GitHub Actions run the official
HACS validation action and Home Assistant Hassfest after the repository is pushed
to GitHub. Those remote checks are the next gate before installing on a live system.

The v4.2 test baseline does **not** treat an internal SHA-256 manifest as proof of
publisher identity. SHA-256 proves that the extracted file matches the manifest,
while SSH/SFTP protects the transfer channel. A trusted package-signing layer is a
separate security gate planned before production use.

## HACS test installation

1. Publish this repository to GitHub.
2. In HACS, open **Integrations > Custom repositories**.
3. Add your repository URL and select **Integration**.
4. Install **JNS Home Assistant Deployment Platform**.
5. Restart Home Assistant.
6. Open **Settings > Devices & services > Add integration**.
7. Search for **JNS Home Assistant Deployment Platform** and add it.
8. Create `/config/jns/inbox` if it does not already exist.
9. Upload a JNS deployment ZIP into that directory using SFTP/SSH.
10. Call `jns_deployment.validate_package` before `jns_deployment.install_package`.

## Package layout

A deployment package is a ZIP containing:

```text
jns_package.json
payload/
  example.yaml
```

`jns_package.json`:

```json
{
  "format": 1,
  "name": "Example package",
  "version": "1.0.0",
  "files": [
    {
      "source": "payload/example.yaml",
      "target": "packages/example.yaml",
      "sha256": "<64-character sha256>"
    }
  ]
}
```

Allowed target roots in v4.2:
- `packages/`
- `custom_components/`
- `themes/`
- `www/jns/`

## Services

### `jns_deployment.validate_package`

Validates the ZIP, manifest, archive paths, target paths and all hashes.

### `jns_deployment.install_package`

Validates again, stages every file, re-verifies staged hashes, backs up any file that
will be replaced, and commits using same-filesystem atomic replacement.

Set `dry_run: true` to perform validation without changing live files.

### `jns_deployment.rollback_transaction`

Restores the backups belonging to a transaction id returned by a successful install.

## Test event names

JNS fires:
- `jns_deployment_validation_result`
- `jns_deployment_deployment_result`
- `jns_deployment_deployment_failed`
- `jns_deployment_rollback_result`

## Required GitHub repository metadata

Set the repository description to:

`Transactional deployment, validation and rollback platform for Home Assistant, installable via HACS.`

Add these topics:

`home-assistant`, `hacs`, `custom-component`, `deployment`, `rollback`

Keep GitHub Issues enabled.


## GitHub publishing

Replace `jamienewton2269` in
`custom_components/jns_deployment/manifest.json` before publishing.

Suggested repository name:

`JNS-Home-Assistant-Deployment`

Do not commit GitHub credentials. Use normal Git authentication, a GitHub personal
access token, GitHub CLI, or SSH keys from your workstation.
