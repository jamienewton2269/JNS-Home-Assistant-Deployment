# Veyra appliance UX corrective design — 2026-10-19

## Priority 0: appliance owns control keys, not provider sites
Veyra is the kiosk shell, not merely a Chrome page. The existing JS extension Escape/history.back approach is inadequate across Chrome profile switches. Implement dedicated input handling at compositor/kiosk session level *before events reach streaming sites*, with stable explicit return and back commands to the Veyra browser supervisor. Cage 0.2.0 requires verifying an available compositor binding/hook or supplying a patched replacement; do not claim it already has one. Never grab all keyboard input or interfere with text fields, accessibility, DRM, provider essential playback keys. Always expose an accessible Home/Back overlay owned by Veyra, outside provider DOM. UX: Escape closes overlay first, then fullscreen, then moves back one page in provider, then exits provider to the last local Veyra screen, then returns Home. Home always returns Home. Preserve logins and the provider-specific Chrome user-data directories. Test on real laptop.

## Priority 0: programme search and add
Replace raw programme title/provider/HTTPS URL entry with a single prominent search bar; autocomplete suggestions from locally indexed watched programmes and legal metadata/catalogue feeds (e.g., TMDB metadata where API license/key permits, provider catalogue APIs where permitted). Search result row: title/year/poster/synopsis, providers with confirmed matching watch URLs, Add to My Programmes. Do NOT fabricate deep-link streaming URLs, claim availability from title-only metadata, or scrape around website restrictions. If reliable provider link unknown, allow user to save the show with link pending and later choose a provider or manually supply URL. Retain explicit easy manual path. Persist watchlist by viewer profile, deduplicate, enable remove/update. Suggestions throttled and cached; preserve provider logins. UI works with remote or keyboard and mouse.

## Proven baseline not to disturb
Oct 19 Lenovo kiosk active/interactive after WorkingDirectory=/opt/veyra, PYTHONPATH=/opt/veyra, seatd backend; Chrome/Cage debug wrapper still active, Restart=no; do not touch graphics launcher, systemd, seatd while working on UI. Veyra navigation hotfix commit 4e87ff6 installed, source backup /var/backups/veyra-navigation/20261019-144025, but user confirmed dashboard appeared on restart only and navigation keyboard still *not proven working*. HTTP 204 from /home is not UI confirmation.

## Acceptance
- Keyboard owned appliance level; no provider can suppress Home/Back; Back reaches Home from ITVX/Netflix and program pages, full screen tested.
- Search autocomplete and add actual show to Watchlist without mandatory pasted HTTPS URL.
- Versioned rollback-tested update deployed to Lenovo without reinstallation; then fold validated files into new PXE asset and test cold boot.
