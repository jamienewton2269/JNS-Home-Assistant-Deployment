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

## Retention and next gate

This run creates **one approximately 30-second audiovisual test buffer**, not 30 minutes, and is *not yet a circular buffer*. Once capture/perception are verified, switch to OBS-backed bounded segmented storage with play/pause/rewind using a separate recorder output strategy and proper disk/time limits. Prefer source frame-rate rather than repeating fixed 50 fps.

## References
- OBS native Linux XSHM source supports `advanced` and a separate `server` display: https://github.com/obsproject/obs-studio/blob/master/plugins/linux-capture/xshm-input.c
- OBS OBS startup flags: https://obsproject.com/kb/launch-parameters
- OBS custom SRT listener: https://obsproject.com/kb/srt-protocol-streaming-guide
