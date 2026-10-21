# Steward Diagnostics — Private GitHub Handoff v0.1

**Not deployed; private repository must exist before installation.** GitHub connector available in this chat does not support creating repositories, and the authenticated GitHub account currently shows only public repos. User-approved target: `jamienewton2269/JNS-Steward-Diagnostics` (PRIVATE).

## Bootstrap
1. In GitHub create `JNS-Steward-Diagnostics` under `jamienewton2269` and choose **Private** (or on an authenticated admin machine use `gh repo create jamienewton2269/JNS-Steward-Diagnostics --private`). Verify visibility.
2. Make a **fine-grained** token restricted to this one private repo: Contents read/write + Metadata read; use short expiry. GitHub supports token access control, but rotation must be maintained.
3. On each uploading Proxmox host, install the uploader/cleanup code from the reviewed source, then:
   ```sh
   install -d -m 0700 /etc/jns-steward /var/lib/jns-steward/upload-acks
   # Securely create /etc/jns-steward/github-diagnostics.token using interactive input / secret manager (NEVER paste token into chat).
   chmod 0600 /etc/jns-steward/github-diagnostics.token
   python3 steward_diagnostics_upload.py --input /root/steward-nodec-inventory.json
   ```
4. To mark a report reviewed, update its *local ack file* to `"status": "reviewed"` only after processing / extracting useful facts. The cleanup tool deletes the current branch-head copy after at least 48h. DO NOT automatically mark uploaded files as reviewed.
5. Add daily systemd timer or cron invoking the cleanup tool. Inventory cadence should be intentionally set based on the load/sensitivity; do not run repeated uploads without bounded retention and monitoring.

## Safety / limitations
- The uploaded JSON is reduced to an allowlisted inventory structure. **This is not a formally complete secret detector**; human review is still recommended for first use. Treat all inventory as sensitive.
- The uploader validates GitHub returns `private: true` before uploading; no public fallback.
- The upload stores a content SHA-based reference in a local acknowledgement; processing and deletion are separate.
- **Deleting files from a Git repository does not remove earlier commits or guarantees deletion from storage or clones.** Consequently this is *temporary visibility/housekeeping*, not secure erasure.
- For strict expiry without persisted Git history, migrate handoff to short-lived GitHub Actions artifacts or a dedicated authenticated ephemeral object store (once a supported upload path is verified).
- Don't commit raw host dumps or access tokens to the public JNS source repo. Don't auto-export HA secrets, authentication stores, Zigbee keys or passwords.
- GitHub connector may not automatically re-ingest uploads into chat: request a review after upload or configure a separate event-based automation.
- Revoke the token to stop future uploads. Audit permissions and token expiry regularly.
