# VEYRA TV-Night v0.7.0 — manual advert cover pilot

Status: published, awaiting validation on the real Lenovo and TV. No automatic advert detection.

## Currently implemented

- Runs shared-capture VA-API H.264 Veyra player for a bounded, maximum four-hour session; previous full pipeline tested only for 75 seconds.
- ITVX continues playing in the existing virtual Chrome. The cover is a separate fullscreen Wayland client.
- Browser controls on 127.0.0.1:8773, including 8-second Preview, Cover 30/60/90/120/180 seconds, immediate End Cover.
- Veyra-branded countdown and progress bar represent a chosen time estimate, NOT an ITVX advert API or accurate break end.
- During manual cover, attempts to mute only the matching Veyra ffplay audio sink input; reports unsuccessful mute in UI; restores saved mute state afterwards and at controller service shutdown.
- Stopping TV service returns original recorder via SIGCONT and removes short isolated buffer segments.
- The separate controller does NOT open provider credentials or play media itself.

## Not yet implemented or validated

- Automatic ITVX advert start/end recognition, seek/skip, provider-verified break countdown.
- HDMI physical TV versus internal laptop focus and window stacking. Check using Preview before viewing tonight.
- Stable four-hour operation. No unattended claim.
- Accurate watched-to-completion telemetry or user media retention cleanup across all buffers. Watchlist marking is currently manual.
- The ring test wraps approximately every 40 seconds (10 × 4 second chunks), not 1–2 hours.
- Native zero-copy/GPU compositor replacement. ITVX is still played via existing proven FFplay output path.
- Local physical remote keys and overlays attached to the main Veyra Home UI.

## Install on Veyra over SSH

    curl -fL https://raw.githubusercontent.com/jamienewton2269/JNS-Home-Assistant-Deployment/main/gateway/trusted/veyra-tv-night-v0.7.0.sh -o ~/veyra-tv-night-v0.7.0.sh
    bash -n ~/veyra-tv-night-v0.7.0.sh
    sudo bash ~/veyra-tv-night-v0.7.0.sh preflight
    sudo bash ~/veyra-tv-night-v0.7.0.sh install
    sudo bash ~/veyra-tv-night-v0.7.0.sh status

This starts the manual cover controller only. It does not start the actual TV stream, and it never restarts existing Chrome/VNC/Cage.

## Remote from Windows

Open a separate PowerShell tunnel:

    ssh -N -L 8773:127.0.0.1:8773 jnsadmin@veyra

Keep it open. Navigate to http://127.0.0.1:8773/ .
Existing VNC tunnel on 5902 and watchlist tunnel on 8772 are independent.

## Tonight test sequence

1. Connect Lenovo to TV through HDMI. Check TV input and that system HDMI connector reports connected in the status output.
2. First press Preview cover for 8 seconds; verify it appears on the intended TV. If only on laptop screen, stop and diagnose output routing before depending on it.
3. In existing virtual Chrome (VNC), log in and start a genuine ITVX programme from the watchlist.
4. Run: sudo bash ~/veyra-tv-night-v0.7.0.sh start
5. Verify playback on intended TV with audio. Read status if no video or sound.
6. At first advert, choose a cover duration. Listen to verify the sound is also muted (status shows whether the ffplay stream was identified).
7. End cover as soon as the programme resumes. Timeout removes cover regardless of whether ads are finished.
8. At end of viewing, run: sudo bash ~/veyra-tv-night-v0.7.0.sh stop
9. Only mark programme Watched in watchlist after genuinely viewing it to end.

## Emergency controls

    sudo bash ~/veyra-tv-night-v0.7.0.sh uncover
    sudo bash ~/veyra-tv-night-v0.7.0.sh stop
    sudo bash ~/veyra-tv-night-v0.7.0.sh status

The cover controller and GPU player are beta-only separate systemd services. The stop operation preserves virtual Chrome, VNC, Cage, user login, watchlist and their existing settings.

## Next detection engineering phase

Instrument provider-level DOM/video-state changes while ITVX shows an advert and a programme transition, with explicit opt-in, no video retention and no provider account credentials. Correlate independent signals and estimate confidence. Avoid claiming that generic black frames, a silent audio section, or a fixed timer is a dependable ITVX advert detector.
