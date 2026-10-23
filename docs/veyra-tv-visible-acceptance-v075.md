# VEYRA visible playback acceptance — v0.7.5, 2026-10-23

## Evidence and status
- v0.7.2: **capture only confirmed**, ~23 minutes reported at 50fps; physical picture **absent**. 450x4-second ring not filled before stop. FFplay UDP consumer logged repeated H.264 PPS and slice-header errors. The original capture service resumed after stopping v0.7.2.
- v0.7.3: **physical video visible**. User confirmed moving local synthetic pattern on laptop; twice completed successfully, 12 seconds each, using Cage/Wayland and FFmpeg MPEG-TS **local pipe** to FFplay.
- v0.7.4: **physical real ITVX picture confirmed by user** on 2026-10-23 after clarifying that earlier v0.7.3 output was only the coloured test pattern. The visual confirmation was direct user observation; the pasted journal output was for v0.7.3 and is not a v0.7.4 log.
- v0.7.5 FIRST LENOVO TRIAL, 2026-10-23 19:42: **no picture because restricted veyra user could not read root-owned staged player.sh**. The installer used mktemp -d (0700) then moved that directory to the published release. Journal: /opt/veyra/tv-night-v075/current/player.sh: Permission denied. Original recorder was restored; failed trial did not reach encoder. GitHub source patched to chmod staged directory 0755 and verify restricted-user read access before publish, start and recorder pause; CI passed. Corrected source is NOT YET installed or physically tested on the Lenovo.
- v0.7.5: **staged only** 70-second proof of 50fps H.264 hardware-encoded FFmpeg tee **local pipe** to FFplay plus simultaneous 450x4-second rolling segment configuration. This is a bounded integrated visibility test, not a completed 30-minute timeshift. Prior original recorder FFmpeg is temporarily paused (not killed); independent resume timer and cleanup in place. It is not auto-enabled.

## Acceptance gates before long-running release
1. Physical laptop visibly plays the **actual ITVX programme** in v0.7.4 or another equivalent accepted real video test.
2. v0.7.5 visible picture with decoded H264, audio synchronised, no black screen, and complete controlled stop/resume. Check session, encoder and player logs.
3. Confirm 50fps capture and sustained display cadence from actual evidence; no report of frame duplication beyond acceptable levels, no render stalls, reasonable CPU load.
4. Extend runtime to at least 30 minutes, check 450x4-second segment wrap behavior and disk guard, verify original recorder resumes on stop/failure.
5. A buffer is **not a functional timeshift** until pause, seek/rewind and seekable manifest/indexing controls are implemented and tested. Do not conflate ring retention with user-controlled playback.
6. Preserve installed Debian dual boot, Chrome ITVX profile, Cage kiosk, original recorder, VNC and audio services. No unattended start, no PXE changes.

## On-Lenovo commands for bounded v0.7.5 (v0.7.4 picture visually accepted)
```bash
curl -fL https://raw.githubusercontent.com/jamienewton2269/JNS-Home-Assistant-Deployment/main/gateway/trusted/veyra-tv-player-v0.7.5.sh -o ~/veyra-tv-player-v0.7.5.sh
bash -n ~/veyra-tv-player-v0.7.5.sh
sudo bash ~/veyra-tv-player-v0.7.5.sh preflight
sudo bash ~/veyra-tv-player-v0.7.5.sh install
sudo bash ~/veyra-tv-player-v0.7.5.sh start
```
Emergency or manual stop: `sudo systemctl stop veyra-tv-v075.service`.

The `sudo` requirement is deliberate; Node C's trusted login does not have passwordless administrator privileges. Do not bypass or expand sudo.
