# VEYRA v0.7.2 — restore high-frame-rate trial and 30-minute ring

**State:** candidate code staged on branch `veyra/quality-evidence-20261023`; **not installed or tested on the Lenovo**. Earlier v0.7.0 services/files remain unchanged.

## Reason for revision

v0.7.0 hardcodes 25 fps and ten four-second wrapped MPEG-TS segments (roughly 40 seconds). That setting was inherited from the older v0.6.1 X11 capture, despite later v0.6.5 persistent Wayland capture probing up to 60 fps (`wf-recorder -B 60`). The GitHub source contains a 25 fps pass threshold for v0.6.5 but not the actual logged frame result from the Lenovo. Do not misreport 25 fps as a hardware limit or 50 fps as a verified real-world rate.

## v0.7.2 candidate

- Separate systemd service: `veyra-tv-v072.service`, **disabled**, started manually for testing only.
- Source: `gateway/trusted/veyra-tv-player-v0.7.2.sh`.
- Isolated installation: `/opt/veyra/tv-night-v072/current/player.sh` (timestamped release behind `current`).
- Buffer: **450 wrapped MPEG-TS segments × 4 seconds = about 30 minutes** at the configured output cadence, subject to actual keyframe/timestamp boundaries.
- Frame capture target: **50 fps** at 1366×768 via the existing `:92` X11 display. This is deliberately above 25 fps but **not** a proof of 50 distinct source frames.
- Scoped Intel iHD driver staging plus a synthetic **50 fps** low-power H.264 preflight before the existing recorder is paused.
- One encoder feeds live UDP and the rolling files; full 4-hour bounded session remains.
- Disk: requires 8 GiB initially free and stops the candidate encoder if free space falls below 2 GiB; unit and external watchdog restore the original recorder.
- Recorder ownership marker is version-specific. v0.7.0 playback must be inactive before running this candidate.
- Does not replace the kiosk, Chrome authentication, VNC, v0.7.0 player unit, or advert/visual-controller units.

**Not yet present:** seekable pause/rewind playback UI, benchmark evidence that source contains 50 unique fps, proven four-hour acceptance, and integration of v0.7.1 ad-cover muting with the separate v0.7.2 unit.

## Controlled Lenovo test (download from isolated branch)

```bash
curl -fL --retry 2 --max-time 45 \
  https://raw.githubusercontent.com/jamienewton2269/JNS-Home-Assistant-Deployment/veyra/quality-evidence-20261023/gateway/trusted/veyra-tv-player-v0.7.2.sh \
  -o ~/veyra-tv-player-v0.7.2.sh
bash -n ~/veyra-tv-player-v0.7.2.sh
sudo bash ~/veyra-tv-player-v0.7.2.sh preflight
sudo bash ~/veyra-tv-player-v0.7.2.sh install
sudo bash ~/veyra-tv-player-v0.7.2.sh start
sudo bash ~/veyra-tv-player-v0.7.2.sh status
```

Use a real moving ITVX programme and inspect actual physical frame smoothness, distinct frame cadence, GPU/CPU utilization, encoder progress `speed=`, A/V sync, and output ring duration. A 50 fps command-line setting by itself is *not* validation. The trial refuses to start if v0.7.0 is already active or disk capacity is inadequate.

To stop safely, without changing the older service:

```bash
sudo bash ~/veyra-tv-player-v0.7.2.sh stop
sudo bash ~/veyra-tv-player-v0.7.2.sh status
```

After stop, the original recorder must be running (not state T). If not, inspect v0.7.2 service journal and use the version-scoped `recover` action only after confirming neither pilot is running. Do not remove historical player or Chrome profiles.

The 30-minute ring is **retention only** at this stage; interactive timeshift pause, playback indexing, catch-up and seek operations must be implemented and accepted separately.
