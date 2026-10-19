# Veyra source-derived RC2 — 2026-10-19

Source supplied: veyra-source-for-next-release-20261019-153101.tar.gz (SHA-256 9ce46b4faea03c8b6eca6ff8ee24bde88842ad62c9ce5a7ccaa722eb57e98dd8). This checksum was verified after correcting the machine-specific pathname in the .sha256 file.

The uploaded source confirms:
- veyra/app.py exposes SQLite-backed programme and progress endpoints, and launches provider browser profiles.
- veyra/models.py requires programme provider and URL.
- veyra/programmes.py rejects items without provider and URL.
- browser-extension/content.js controls provider DOM but has no guarantee of compositor-level Escape interception.
- kiosk.py includes Home controller on loopback port 8767.

A source-derived **RC2 patch bundle** was built in the ChatGPT workspace with corrected URL-optional watchlist saving, select-result quick-add, provider HTML5 video playback observation into local SQLite history, and recently watched UI. Modified Python was AST-parse checked and JavaScript node --check passed; **NOT live installed nor provider validated**. Artifact SHA256: 232203fc374e3b7c6ad73f570a5cccd8587cbe141de23422c1da6da1552ccc88.

Gates before deployment-ready status:
1. Actual Lenovo runtime preflight source hashes, service restarts and Home transition.
2. Compositor-owned Back/Home/Escape, tested on each real provider. Browser-extension JS is NOT sufficient.
3. Encrypted consent-based vault, origin-bound autofill and Chrome password prompt suppression, with tests.
4. Accurate UK service availability and programme deeplinks requires licensed/compatible metadata source; TVmaze alone only programme title autocomplete.
5. Fresh PXE boot with all graphics fixes and service/session leak tests.

Do not mistake this manifest for an installed release or full PXE package. Do not ship passwords or browser profiles in GitHub.
