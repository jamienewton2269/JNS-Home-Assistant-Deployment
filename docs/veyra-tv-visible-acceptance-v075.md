# VEYRA visible playback acceptance — v0.7.5, 2026-10-23

## Evidence and status
- v0.7.2: **capture only confirmed**, ~23 minutes reported at 50fps; physical picture **absent**. 450x4-second ring not filled before stop. FFplay UDP consumer logged repeated H.264 PPS and slice-header errors. The original capture service resumed after stopping v0.7.2.
- v0.7.3: **physical video visible**. User confirmed moving local synthetic pattern on laptop; twice completed successfully, 12 seconds each, using Cage/Wayland and FFmpeg MPEG-TS **local pipe** to FFplay.
- v0.7.4: **physical real ITVX picture confirmed by user** on 2026-10-23 after clarifying that earlier v0.7.3 output was only the coloured test pattern. The visual confirmation was direct user observation; the pasted journal output was for v0.7.3 and is not a v0.7.4 log.
- v0.7.5 FIRST LENOVO TRIAL, 2026-10-23 19:42: **no picture because restricted veyra user could not read root-owned staged player.sh**. The installer used mktemp -d (0700) then moved that directory to the published release. Journal: /opt/veyra/tv-night-v075/current/player.sh: Permission denied. Original recorder was restored; failed trial did not reach encoder. GitHub source patched to chmod staged directory 0755 and verify restricted-user read access before publish, start and recorder pause; CI passed. Corrected source is NOT YET installed or physically tested on the Lenovo.
- v0.7.5: **staged only** 70-second proof of 50fps H.264 hardware-encoded FFmpeg tee **local pipe** to FFplay plus simultaneous 450x4-second rolling segment configuration. This is a bounded integrated visibility test, not a completed 30-minute timeshift. Prior original recorder FFmpeg is temporarily paused (not killed); independent resume timer and cleanup in place. It is not auto-enabled.

## 2026-10-23 v0.7.5 visible-but-jerky follow-up
- User confirmed physical programme video from integrated 70-second v0.7.5 but reports motion is still jerky.
- Read-only Node C SSH audit after run: encoder produced frame=3500 at nominal 50fps for 70 seconds, with **dup=1530**, **drop=5**, speed=0.992x. Approximately 44% of output frames were duplicated by FFmpeg's sync/output handling. Thus a reported output of 50fps does **not** establish 50 newly captured frames per second. The original recorder and VEYRA services were active after trial; v0.7.5 stopped normally.
- Do not assert the video source itself is 28fps; input unique moving picture cadence was NOT directly measured. Duplication counts distinguish FFmpeg output-generated duplicates from requested capture cadence, not true content uniqueness.
- v0.7.6, CI-validated but **not yet run on Lenovo**, is a bounded 20-second Xvfb raw x11grab at 1366x768 / 50fps to FFmpeg null muxer with -fps_mode passthrough. No physical playback or media file retention. It pauses only the original recorder for the test and automatically resumes via cleanup plus independent timer. If this probe delivers near 1000 frames in 20s, the added encode/decode/buffer work is the bottleneck; if substantially lower, capture/Xvfb itself is limiting throughput. Either way, retain genuine 50fps target rather than silently lowering the output goal or hiding duplication with -vsync passthrough in the final player.

## 2026-10-23 v0.7.6 benchmark verified through Node C
- The bounded raw X11-grab test completed at 1366x768 and requested 50fps: FFmpeg logged **1000 frames in 20.00 seconds, speed 1.00x** with `-fps_mode passthrough` to null muxer (no programme media retained).
- After the test Node C confirmed `veyra-tv-v076.service=inactive`; original FFmpeg recorder PID 626060 was running, together with active VEYRA kiosk, virtual loopback and VNC services.
- Therefore requested **raw capture throughput is achievable without downstream encoder/audio/buffer/player pressure**, although 1000 captures do not establish 1000 distinct motion frames from the ITVX source.
- The next isolated test v0.7.7 is staged in GitHub and safety-CI passed. It runs 20 seconds of VAAPI H264 video plus Pulse audio to FFmpeg null muxer, with no physical playback, tee or segment media retention. This distinguishes encoding/audio overhead from playback and ring overhead. No Lenovo v0.7.7 deployment or run has occurred.

## 2026-10-23 v0.7.7 Lenovo test and next isolation
- Node C read-only verified v0.7.7 **1000 H264 VAAPI encoded frames** and Pulse/MP2 audio over 19.99 seconds at reported `speed=0.995x`. This test deliberately used `-fps_mode:v passthrough` and a null muxer, with no FFplay or ring.
- v0.7.7 null muxer repeatedly logged `Application provided invalid, non monotonically increasing dts to muxer in stream 0`: timestamps require analysis; not a clean A/V timestamp acceptance. Neither raw frame count nor encoder frame count proves every ITVX scene frame differs.
- At end `veyra-tv-v077.service=inactive`, no recorder marker, and original recorder PID 626060 was running, along with active kiosk, virtual capture and VNC.
- FFmpeg documentation confirms `-fps_mode passthrough` passes each decoded frame's timestamp, `cfr` can duplicate/drop frames, and `auto` defaults to muxer-dependent behaviour. Do not silently use pass-through as a claimed frame-quality fix without validating timestamp monotonicity and A/V playback.
- v0.7.8 staged in GitHub (CI passed, **not yet installed or run on Lenovo**). Test: bounded 20s VAAPI+Pulse encoder with the **same default output sync and tee/segment ring** as jerky v0.7.5, replacing only physical FFplay pipe with MPEG-TS output to `/dev/null`. Logs compare duplicate count versus v0.7.5 and v0.7.7; the isolated segment files are deleted during cleanup, original recorder restored. This determines whether tee/segment muxing alone is implicated before touching the real player.

## 2026-10-23 v0.7.8 confirms the blocking-player bottleneck
- Node C retrieved full 20-second v0.7.8 tee/ring trial log: **1000 encoded frames, 50fps, speed 0.995x, dup=22, drop=20**. The muxer simultaneously wrote 4-second H264/MP2 segment files and MPEG-TS to /dev/null; **FFplay was absent**.
- Compared with v0.7.5's 70-second integrated direct-PIPE FFplay test (**3500 frames, dup=1530, drop=5**), duplicate generation fell from 43.7% of output frames to 2.2%. Trials differed in length, so this is compelling isolation evidence but not an identical A/B benchmark.
- Original FFmpeg recorder PID 626060 was confirmed running, VEYRA kiosk/capture/VNC active, v0.7.8 inactive, marker absent, isolated segment files automatically cleared.
- Interpretation: high duplicate count arises only with connected FFplay/pipe delivery in the observed trials. A slow FFplay decoder or blocking pipe/back-pressure is the strongest remaining candidate. This is NOT proof the source has 50 distinct moving frames per second or that buffer pause/rewind is implemented.
- v0.7.9 staged in GitHub (CI PASS, **not yet run on Lenovo**). Bounded 40-second candidate uses a separate localhost UDP receiver, started BEFORE encoding so it sees MPEG-TS headers, with the proven VEYRA Wayland/Pulse environment. Encoder continues 450x4s segment ring, without a blocking FFplay stdout pipe. A visually smooth test and a low duplicate count would support this architecture; any decoding errors, packet loss or choppy picture mean physical acceptance still fails. Original recorder restored on stop/exit, Chrome/ITVX/VNC/Cage unchanged.
## 2026-10-23 v0.7.9 actual laptop picture and v0.8.0 staged
- User physically confirmed v0.7.9 **ITVX visible on Lenovo screen and playback smoother than v0.7.5, but NOT fully smooth**. On-Lenovo journal: start 22:01:08 BST, encoder 40s finished at 22:01:56, 10 temporary buffer slots written, clean exit and original recorder SIGCONT restored at 22:01:57; Chrome, VNC and Cage left untouched.
- Node C read-only logs: v0.7.9 **2000 encoded output frames in 39.99s, nominal 50fps, speed=0.988x, dup=770, drop=4** (38.5% duplicate output). FFplay log physically decoded H264 High/MP2 from local UDP and its frame-drop counter reached **fd=354** over ~40 seconds. Sync values converged near zero, but playback dropped frames. Hardware display remains below acceptance. Do not interpret 2000 frames as 2000 distinct ITVX motion frames.
- Separate Node C capability audit: mpv not installed; Debian 13 apt candidate mpv 0.40.0-3+deb13u1. A dry-run `apt-get -s install --no-install-recommends mpv` reported **six NEW native packages, zero upgrades**. Intel i965 VAAPI driver already exists and `vainfo --display drm --device /dev/dri/renderD128` reports **VAProfileH264High : VAEntrypointVLD**. No package installation was performed remotely.
- v0.8.0 scripted and staged on GitHub with safety CI; **not yet installed or tested on Lenovo**. It changes only FFplay to mpv on Wayland with `--hwdec=vaapi --vo=gpu --gpu-context=wayland` (i965 decoder), while retaining private iHD encoder, 50fps target, local UDP transport, 450x4s temporary ring, 40-second bound, verified original-recorder restore, disabled systemd service and no background/autostart. Requires an explicit user-side `sudo apt-get install --no-install-recommends mpv` beforehand. Stage/launch only if user agrees to this six-package addition. Verify mpv log actually states VAAPI hardware decoding is active, quantify frame drops and encoder duplicates, and obtain visual smoothness confirmation. Do not yet extend to 30-min ring/time-shift.

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
