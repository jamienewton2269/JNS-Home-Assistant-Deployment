# VEYRA Watchlist Beta v0.6.6 — Live testing

Status: source published to GitHub. Install/test on Veyra Lenovo still required.
Design: offline-first watchlist (Python standard library, SQLite, static JS/CSS); no streaming content captured by this component.

## Install from trusted JNS repository

Run as jnsadmin on Veyra:

    curl -fL https://raw.githubusercontent.com/jamienewton2269/JNS-Home-Assistant-Deployment/main/gateway/trusted/veyra-watchlist-v0.6.6.sh -o ~/veyra-watchlist-v0.6.6.sh
    bash -n ~/veyra-watchlist-v0.6.6.sh
    sudo bash ~/veyra-watchlist-v0.6.6.sh preflight
    sudo bash ~/veyra-watchlist-v0.6.6.sh install
    sudo bash ~/veyra-watchlist-v0.6.6.sh status

Installer fetches five source assets, parses server.py, checks client syntax where Node exists, performs a local HTTP/SQLite smoke test with its own temporary DB before configuring systemd. It then starts only veyra-watchlist.service.

## Access from Windows, no ITVX disruption

Windows PowerShell:

    ssh -N -L 8772:127.0.0.1:8772 jnsadmin@veyra

Keep tunnel open. Open http://127.0.0.1:8772/ in the Windows browser. If using the existing VNC tunnel in the same PowerShell window, start a second terminal for this tunnel. Don't shut down VNC or the ITVX Chrome session.

## First test scenario

1. Add a genuine show or film you intend to watch. TVmaze suggestions are optional title metadata, not proof of UK provider availability.
2. Choose provider, season/episode, and paste a genuine HTTPS provider programme URL if known. Leave empty rather than invent a link.
3. Save and confirm it survives refresh. SQLite persists after restarting this watchlist service.
4. Update viewing progress (0–99%) manually, verify “In progress”.
5. To play, select Copy link and paste into existing virtual provider Chrome/VNC session. Watchlist intentionally does not directly play providers on the physical kiosk.
6. After actually watching to end, select Watched and explicitly confirm. Automatic provider-verified tracking isn't installed.
7. Use History to view manual progress and completion events.
8. Use Archive to hide an entry; stored history remains.

## Local data and trust

- Service veyra-watchlist.service; 127.0.0.1:8772 only.
- SQLite DB /var/lib/veyra/watchlist/watchlist.sqlite3 (owned by veyra, mode-restricted directory).
- Source /opt/veyra/watchlist/current, symlink to versioned source directory.
- No external database or user account service.
- TVmaze queries are made on request using title text. No user streaming credentials involved.
- Programme availability, episode deep links and automatic watch history not verified.
- Existing /opt/veyra/veyra/view.py and its add-programme database not modified or imported at this stage. Migration and integrated Home tile are separate tasks.
- Watchlist never owns provider video/audio buffers. It never purges unrelated player buffers.
- Completion uses an explicit manual confirmation. Provider-verified completion and session media cleanup require subsequent work.

## Rollback

    sudo bash ~/veyra-watchlist-v0.6.6.sh rollback

Stops/disables only the watchlist beta service. Does not delete SQLite data, provider logins, browser profiles, Cage or VNC services. Re-running install restores access to persisted database.

## Next integrations

- Inspect current Veyra Home view.py storage; import or synchronise original watchlist records without duplicates.
- Add native Home tiles/launch commands after verifying browser supervisor integration, without restarting Cage.
- Separate provider browsing from physical Chrome; place player commands in Veyra-owned local API.
- Implement provider-aware watched progress through browser event telemetry, including seeks, pauses and actually played intervals; don't infer watched just because a segment was captured.
- When full viewing is verified and no active session needs it, delete programme-owned video/audio, rolling buffers and processed media while retaining compact watch-history metadata.
- Introduce UK provider availability metadata with provenance; TVmaze supplies only title suggestions.
