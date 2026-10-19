# Veyra v0.9.2-next deployment patch manifest — 2026-10-19

Status: Source scripts committed; NOT YET BAKED INTO THE LIVE PXE PAYLOAD; MUST VALIDATE ON LENOVO AND REBUILD IMMUTABLE PACKAGE BEFORE NEXT RELEASE.

## Order of application
1. Preserve current confirmed working Lenovo runtime and Node C PXE backups.
2. Run `gateway/trusted/veyra-navigation-home-hotfix-v1.sh` on a fresh image (the existing Lenovo already received this; do not rerun: script is deliberately non-idempotent).
3. Run `gateway/trusted/veyra-programme-discovery-v1.sh` on working installed Veyra; backup /var/backups/veyra-programme-discovery. It changes `/opt/veyra/veyra/view.py` only; refresh Home page. No Cage/systemd restart.
4. Verify Veyra Home is visible, Add Programme shows real TVmaze suggestions, selected show populates title, and programme saves via existing backend. Show website URL is used only when TVmaze lists an official website; service availability and deep-playability are not verified. Provider homepage may be used only as a starting URL with a visible warning, not a per-show deep link. Catalogue access requires Internet and website CORS permissions.
5. Test ITVX Home recovery by direct API (confirmed), and explicitly test keyboard shortcut separately (not yet confirmed). Do not claim universal Escape.
6. For clean PXE reproducibility, integrate these exact source changes and Python-path/seatd graphics baseline into next version *in a staging directory*, verify file hashes and boot/install on disposable target before moving live PXE pointers. Do not replace existing v0.9.2 payload or reinstall reference Lenovo until proven.

## Known limitations and planned follow-up
TVmaze is a metadata autocomplete provider, **not** an up-to-date aggregate of streaming availability across all named providers. The v1 UI does not provide verified provider-specific playable deeplinks. Add regional TMDB watch-provider metadata or licensed catalogue partner API, cache/rate limit and verify deeplinks before claiming live cross-provider discovery. The existing backend may require a URL to save; v1 maintains existing form semantics. A dedicated, Veyra-owned compositor-level Home/Escape key path is still required.
