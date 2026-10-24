# VEYRA OBS v1.1 — first actual ITVX live A/V stream and visual buffer test

**24 October 2026.** First real OBS capture candidate is committed and GitHub Actions bash/static guard checks have passed. This is **not yet installed or run** on the Lenovo. It is a bounded quality-evaluation build, not production cutover.

## Test topology

- Authenticated Chrome/ITVX continues in existing Xvfb **:92**, video captured via OBS native **Display Capture (XSHM)** source `xshm_input_v2` with `advanced=true`, `server=:92`, `screen=0` and disabled captured cursor.
- Audio source is OBS's **PulseAudio output capture** targeting the existing `veyra_virtual_capture.monitor`; no physical-mic capture or additional virtual devices.
- OBS itself runs on disposable Xvfb **:93** with a private OBS profile and scene; config directory `/opt/veyra/obs-backend-v1/av-qa-v11/config`.
- OBS records **MKV** locally at target **1366×768, 25 fps, 6.5 Mbps H.264 plus 160 kbps stereo audio**. Source-native frame cadence has not been measured; 25 fps is an *initial test output target*, not a claim about source broadcast frames.
- Simultaneously, OBS custom stream service exposes **SRT listener only on `127.0.0.1:23619`**, with mpv as the hardware-decoding physical Cage/Wayland receiver. No FFmpeg/FFplay process is launched by this candidate. OBS itself may rely internally on bundled libav components as intended.
- A protected original legacy recorder is temporarily SIGSTOPped to free its CPU core and SIGCONT is guaranteed by process-verified EXIT cleanup and a separately scheduled 95-second recovery timer.
- The test is **~35 seconds**, stores at most one MKV output, is **not enabled at boot**, does not alter the Chrome profile or kiosk services, and leaves previous recording files intact. A repeat run is refused if a previous MKV exists.
- Prior isolated graphics probe reported **Mesa llvmpipe** under Xvfb. It remains possible that OBS software rendering/encoding will overload the N4200; quality must be assessed visually and through OBS logs. Do not imply this is Intel-accelerated OBS rendering.

## Install/stage/run

On Lenovo, with ITVX programme playing:
```bash
curl -fL https://raw.githubusercontent.com/jamienewton2269/JNS-Home-Assistant-Deployment/main/gateway/trusted/veyra-obs-live-av-quality-v1.1.sh -o ~/veyra-obs-live-av-quality-v1.1.sh
bash -n ~/veyra-obs-live-av-quality-v1.1.sh
sudo bash ~/veyra-obs-live-av-quality-v1.1.sh run
```

The run stages the private OBS scene and recording settings and launches the bounded A/V trial. The laptop's physical display should briefly show an mpv player fed by OBS loopback SRT. Check picture detail (motion/edges/text), stutter, sound and lip-sync. If no picture, inspect OBS and mpv logs; the MKV test recording is an independent diagnostic. OBS may not be able to capture some protected content; do not disable or circumvent DRM.

After trial, inspect:
```bash
sudo bash ~/veyra-obs-live-av-quality-v1.1.sh status
sudo journalctl -b --no-pager -n 20
find /opt/veyra/obs-backend-v1/av-qa-v11/buffer -maxdepth 1 -type f -name '*.mkv' -ls
```

**OBS logs:** `/opt/veyra/obs-backend-v1/av-qa-v11/logs/obs-console.log`, OBS profile's `config/obs-studio/logs` folder, and `logs/mpv.log`.

**Observation checkpoints:** OBS created XSHM image / real source, Pulse source connected to sink monitor, both audio and video encoded to MKV, picture appears on physical display via SRT, OBS rendering/encoding dropped frames and CPU load, recording playback quality. These all need verification before production, before long circular ring implementation, and before retiring original recorder.

## 24 October 2026 — first actual trial result and independent review

- User ran `veyra-obs-live-av-quality-v1.1.sh run` successfully; OBS captured into `/opt/veyra/obs-backend-v1/av-qa-v11/buffer/2026-10-24 17-05-30.mkv`, observed size **24,317,952 bytes** at the initial status check. **Actual frame contents, video codec/audio stream metadata and audio audibility have not yet been visually/technically verified.**
- mpv on physical compositor logged up to **AV: 00:00:18** with A-V offset approximately 0 s and 2.9 s player cache at final sample, so a live stream was received and demuxed. Do not infer smoothness or visible ITVX picture from stream timestamps alone.
- OBS logged **193 lagged frames due to rendering stalls (27.3%)**, plus repeated `Connection rejected, Unknown or erroneous` at the SRT muxer. SRT instability and high software rendering lag are **independent quality blockers**; no production cutover.
- Test completed its bounded run and printed **RESTORED ORIGINAL RECORDER 626060**. Follow-up Node C read-only audit confirms virtual display :92 still running, no :93 Xvfb, original FFmpeg recorder PID 626060 running, Cage/kiosk/virtual capture/VNC active, and no recorder recovery marker. OBS buffer/log directory is mode-restricted to the `veyra` user, so ordinary `jnsadmin` Node C SSH cannot read inside, by design. Do not weaken permissions to retrieve log or buffer contents.
- A separate **read-only MKV review helper**, `gateway/trusted/veyra-obs-mkv-review-v1.1.sh`, is published (CI PASS). It safely uses `sudo` to inspect MKV A/V streams with `ffprobe`, count decoded video frames, and play the SAVED OBS MKV with mpv in the physical Wayland session using Intel VAAPI where supported, without starting OBS, SRT or any FFmpeg capture pipeline.
- Next gate: obtain `inspect` metadata and user observation during `play`: is actual ITVX picture present (or black), detailed, smooth? Is audio present/audible/lip-synced? Independent replay isolates OBS encoding/capture quality from live SRT network/player timing. If local file is smooth but SRT isn't, address transport. If file is jerky, first fix OBS llvmpipe/scene render overload, not transport.

### Review commands on Lenovo (no new capture)

```bash
curl -fL https://raw.githubusercontent.com/jamienewton2269/JNS-Home-Assistant-Deployment/main/gateway/trusted/veyra-obs-mkv-review-v1.1.sh -o ~/veyra-obs-mkv-review-v1.1.sh
bash -n ~/veyra-obs-mkv-review-v1.1.sh
sudo bash ~/veyra-obs-mkv-review-v1.1.sh inspect
sudo bash ~/veyra-obs-mkv-review-v1.1.sh play
```

### Saved MKV inspection and physical replay (24 October 2026)
- User ran the existing read-only `veyra-obs-mkv-review-v1.1.sh inspect` and `play` commands, both completed.
- **MKV:** 24,317,952 bytes, Matroska container, video H.264 **1364×768 at 25/1 fps**, audio AAC **2 channels at 48,000 Hz**. `ffprobe -count_frames` read **749 video frames**, but warned **`File ended prematurely`**. File format duration missing, so about 29.96s is estimated from counted frames; the original OBS script uses TERM followed by KILL after ~2 seconds, so a missing/truncated muxer trailer is a likely issue to investigate, not yet conclusively proven.
- Physical laptop `mpv` replay reported `Using hardware decoding (vaapi)`, `VO: [gpu] 1364x768 vaapi[nv12]`, `AO: [pulse] 48000Hz stereo 2ch float`, `AV: 00:00:29 / 00:00:29 (100%) A-V: 0.000`, then normal end of file. This verifies successful **decoder and audio output initialization and transport streams**, but **does not yet verify that actual ITVX programme pixels were visible, sound was audible, or motion was smooth**; request user's direct observation.
- Earlier OBS live SRT output reported **193 render-lagged frames (27.3%)** and repeated SRT connection rejections. Neither a usable MKV nor 749 encoded frames demonstrate unique frames or broadcast-quality motion.
- Pending investigation/gates before *any* production cutover: physical playback visual/audio report; OBS renderer hardware path (Xvfb :93 currently Mesa llvmpipe software renderer); replace forced OBS process-group teardown with an OBS-supported **graceful recording stop and verified MKV finalisation**; make restream errors independent of local recording test; confirm video dimensions/codec/clean EOF; measure actual capture drops and not just encoded frame totals. Preserve ITVX Xvfb :92, Chrome profile, VNC, Cage and original recorder; **no standalone FFmpeg/FFplay development**.

## 24 October 2026 — saved MKV inspected and replayed

- The OBS MKV was inspected by the user: H.264 video **1364×768 at 25/1 fps** (different from the requested 1366×768), AAC **two channels at 48000 Hz**, 24,317,952-byte file, **749 video frames** counted. Approximate frame-count duration is 30 seconds. This demonstrates codec data exists, **not** that video contains the desired ITVX programme, or that its content is visually smooth, or that audio contains audible programme sound.
- `ffprobe` warned `File ended prematurely`: the MKV is playable but may be incomplete/unfinalised. Review the OBS shutdown path before the next capture. Do not overwrite the sample.
- Physical `mpv` replay reported `Using hardware decoding (vaapi)`, `VO: [gpu] 1364x768 vaapi[nv12]`, `AO: [pulse] 48000Hz stereo`, replayed through **00:00:29**, and finished with `A-V: 0.000`. This proves **player** hardware decoding and nominal A/V clock alignment, *not* OBS hardware rendering/encoding or actual ITVX sound quality.
- The OBS *streaming output* separately logged **193 lagged frames (27.3%)** and persistent SRT `Connection rejected` errors. Do not conflate this streaming-output metric with a verified dropped-frame count for the MKV recording.
- NEXT quality decision requires the user's first-hand observation: **was the ITVX programme visible in the saved MKV; was motion smooth; was its programme audio audible and synchronised?** If the MKV itself was poor, prioritise OBS rendering (earlier llvmpipe) and isolate recording from broken SRT before another combined test. If the saved MKV was good, prioritise SRT connection/protocol and receiver buffering. Do not claim broadcast-equivalent quality yet.

## 24 October 2026 — user visual result and controlled retake
- User personally replayed the OBS MKV on the Lenovo and saw a **blank picture**. ITVX was **not playing a programme at the time of the OBS capture**. Therefore the first trial **cannot assess programme visual quality**. This does not conclusively prove either that XSHM works for programme content or that the capture path is broken.
- Do not redevelop transport or graphics pipeline based on the blank recording alone. Have the user **start actual ITVX programme playback in the existing Chrome :92 via VNC** and visually confirm motion *before* the next bounded OBS trial. Do not restart virtual Chrome or create another browser profile.
- The v1.1 script deliberately refuses to overwrite an MKV. Preserve the initial sample by moving **only the named v1.1 MKV** into a dedicated archive under the same test root before running the identical v1.1 trial again; the existing `veyra-obs-mkv-review-v1.1.sh` helper will then select the new buffer sample. No source code changes required for this retake. OBS/ffprobe metadata and audio streams alone do not establish quality; ask for actual picture and programme sound in the saved replay.
- Initial SRT errors and reported OBS rendering lag remain for later attention *after* validating a real programme capture.

## 24 October 2026, 18:21 BST — ITVX playback unavailable, OBS QA paused
- The user archived the original 17:05:30 MKV, captured a second 18:19:16 MKV, and independently inspected it: **1364×768 H.264 25fps, AAC 48kHz stereo, 749 counted frames, same 24,317,952-byte file size and premature-end warning**. The second OBS run reported **210 rendering-stall frames (30.3%)** and recurring SRT connection rejections; the original recorder PID 626060 was restored.
- The user confirmed **ITVX itself failed to play**, so the second recording is **not usable as a source-content quality assessment**. The MKV is a technically decodable capture container only, not demonstrated ITVX motion/audio quality. Stop further OBS capture attempts until the original ITVX programme plays successfully in Chrome through VNC.
- A subsequent rerun failed harmlessly because the 18:19:16 MKV was already in the buffer; the older 17:05:30 sample had already been archived. Preserve both samples. Once source playback is verified, archive only the **18:19:16** MKV before running the existing trial; do not repeat an already archived path.
- Next priority: inspect Chrome process/window state, VNC, network and actual ITVX error message. Refresh only the ITVX browser tab if needed, not the entire Chrome/VNC service; avoid deleting cookies or CDM/DRM bypass. Require observed source picture and programme audio **before** any OBS quality capture.

## 24 October 2026 — third OBS test / physical display isolation
- After archiving second buffer, user ran v1.1 again. OBS generated `2026-10-24 18-37-25.mkv` (24,911,872 bytes). Original recorder PID 626060 was restored. SRT connection rejection messages persisted; mpv log showed A/V timestamps through ~20 seconds and ~1.7–1.9 second cached buffer.
- **User again reported nothing appearing on physical Lenovo display**, despite mpv decoding and stream timestamps. This is not proof of valid programme picture: physical presentation and captured-pixel content remain unverified.
- Cage is a single-visible-window compositor; independent mpv windows launched into Cage may not be made visible automatically. Reference: https://github.com/cage-kiosk/cage/blob/master/cage.1.scd . Prior v0.7.9/FFplay physical success doesn't establish that mpv's Wayland window becomes foreground now.
- Created `gateway/trusted/veyra-display-isolation-v1.2.sh`: a **12-second static four-colour test pattern** shown via mpv directly in existing Wayland session (no capture, SRT, OBS startup, recorder pause or compositor changes). Its output will determine whether a newly launched mpv Wayland client can become visible. GitHub safety validation PASS.
- If colour bars remain invisible while mpv reports video output, fix physical kiosk window presentation before repeating OBS test. If bars are visible, inspect recorded MKV's actual programme content and OBS XSHM source geometry; focus on captured black frames or protected-player output. Preserve all three MKVs; no production cutover.

## 24 October 2026 — Physical mpv picture confirmed
- User confirmed the **four-colour static mpv test pattern was visible** on the laptop physical screen. Therefore a separate mpv Wayland client **can** present over Cage; do not assume the kiosk is preventing all new mpv windows.
- What remains unverified is **the actual programme pixels in the most recent OBS MKV** (`2026-10-24 18-37-25.mkv`), rather than just an encoded H.264/AAC container. To isolate the remaining failure from SRT, replay the existing third sample with the trusted read-only `veyra-obs-mkv-review-v1.1.sh play` utility *without running OBS again*.
- If that recording has visible programme picture and sound, the live SRT stream/player path (repeated connection rejections) is the next fault. If it is blank/black, inspect OBS XSHM capture source and the :92 browser picture before any further recording. OBS `xshm_input_v2` does support `advanced=true, server=:92, screen=0` per upstream plugin source, but runtime source settings/visibility must be verified. No DRM workarounds.

## Retention and next gate

This run creates **one approximately 30-second audiovisual test buffer**, not 30 minutes, and is *not yet a circular buffer*. Once capture/perception are verified, switch to OBS-backed bounded segmented storage with play/pause/rewind using a separate recorder output strategy and proper disk/time limits. Prefer source frame-rate rather than repeating fixed 50 fps.

## References
- OBS native Linux XSHM source supports `advanced` and a separate `server` display: https://github.com/obsproject/obs-studio/blob/master/plugins/linux-capture/xshm-input.c
- OBS OBS startup flags: https://obsproject.com/kb/launch-parameters
- OBS custom SRT listener: https://obsproject.com/kb/srt-protocol-streaming-guide
