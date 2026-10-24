# VEYRA OBS Backend Migration — v1 (24 October 2026)

**Decision:** Stop development of the external FFmpeg/FFplay capture-and-restream pipeline. OBS Studio is the selected capture, A/V mixing, encoding and restreaming application. Do not automatically disable or remove existing production services until OBS is accepted on the physical screen.

## Verified Lenovo baseline (read-only Node C audits)
- Debian 13 Lenovo Pentium N4200, ~4 GB RAM, native 1366×768 panel.
- OBS Studio **30.2.3.1-3 already installed** at /usr/bin/obs.
- Native OBS modules present: linux-capture.so, linux-pulseaudio.so, obs-ffmpeg.so (OBS's internal codec integration), obs-websocket.so.
- Authenticated ITVX Chrome continues in Xvfb **:92**; original FFmpeg recorder PID 626060 was running at audit time and consumes about one CPU core. Existing kiosk, virtual Chrome service and VNC all active.
- Virtual :92 display supports GLX and MIT-SHM, 1366×768×24. **Actual OBS OpenGL capability/performance has not yet been established.**
- Intel render device /dev/dri/renderD128, VAAPI H.264 encoding and H.264 High-profile decode previously established. OBS VAAPI encoder selection must still be verified inside OBS.
- gstreamer1.0-tools and required receiver plugins were not observed as installed in the audit; installing OBS+plugins+GStreamer blindly would add about 75 packages. Do NOT do so.

## Architecture to validate

~~~text
Existing authenticated ITVX Chrome (Xvfb :92; NEVER restart or recreate)
                         |
             OBS native XSHM capture
            OBS running on isolated :93
                         |
  Existing Pulse monitor: veyra_virtual_capture.monitor
                         |
            OBS A/V mix + native cadence
                         |
       OBS Intel VAAPI H.264, tuned for quality
                         |
             SRT listener on 127.0.0.1:23600
                         |
   VEYRA local receiver (to be selected/tested, no FFplay)
                         |
              Physical Cage laptop display
~~~

- OBS **XSHM Screen Capture** advanced **X Server** may target `:92` even while OBS itself runs on a separate `:93`. Verify plugin behaviour and ensure the OBS window itself never appears in the captured programme. The source is `xshm_input_v2` in OBS; capture GUI advanced property is named **X Server**, setting `server`.
- OBS audio: PulseAudio Output Capture, device `veyra_virtual_capture.monitor`, not laptop speaker monitor or microphone.
- OBS output candidate: **Custom** streaming service, SRT `srt://127.0.0.1:23600?mode=listener&latency=150000`; no stream key. OBS official guide supports SRT custom-service output. Binding to 127.0.0.1 prevents external access initially.
- VEYRA receiver should use a modern playback stack (candidate GStreamer or browser-appropriate playback bridge) with Intel hardware decode, audio synchronisation and efficient Wayland integration. **No FFplay or externally orchestrated FFmpeg pipelines.**
- OBS may internally depend on libavcodec/FFmpeg (Debian package design); that is not reintroducing a standalone FFmpeg development path.

## Quality goals / acceptance gates

1. Capture the **actual provider playback** inside an authorised browser without bypassing DRM, HDCP or service access restrictions; black or protected pictures are a hard stop, not a reason to disable protection.
2. Source pixel dimensions and video cadence identified; use 1366×768 only if the renderer really supplies it; distinguish 25/30 fps source content from a 50 fps display.
3. GPU or CPU burden measured on the N4200 and OBS render/encode overload counters captured. Do not assume OBS improves quality automatically.
4. Test physical laptop playback with audio at least 15 minutes. Visually compare pans, scrolling text, high-motion scenes and audio lip sync; reject obvious stutter or excessive dropped frames.
5. Only when live OBS restream is accepted, add VEYRA pause/seek with a 30-minute circular buffer as a **separate** workstream; no perpetual recording before testing storage and rights requirements.
6. Only after verified roll-back and physical acceptance, switch launcher default to OBS and then retire the old capture recorder. **Do not disable the authenticated Chrome, VNC, Cage, or dual-boot Windows.**
7. Do not publish captured media outside the user's authorised environment. OBS WebSocket must be authenticated, not exposed on LAN or WAN.

## First deployment command (separate, safe compatibility probe)

```bash
curl -fL https://raw.githubusercontent.com/jamienewton2269/JNS-Home-Assistant-Deployment/main/gateway/trusted/veyra-obs-backend-v1.sh -o ~/veyra-obs-backend-v1.sh
bash -n ~/veyra-obs-backend-v1.sh
bash ~/veyra-obs-backend-v1.sh audit
sudo bash ~/veyra-obs-backend-v1.sh stage
sudo bash ~/veyra-obs-backend-v1.sh probe
```

This launches OBS for 14 seconds on **independent temporary Xvfb :93 only**, using a private `XDG_CONFIG_HOME`. It is a GPU/OpenGL viability check, not a live broadcaster; no OBS stream or browser should appear on the physical laptop during the probe. Logs will be in `/opt/veyra/obs-backend-v1/logs/obs-probe.log`. The probe terminates its own :93 process, and all protected ITVX services remain untouched.

### Deprecated experiment — DO NOT RUN
`gateway/trusted/veyra-obs-virtual-display-test-v1.sh` is unsafe on today's topology: it attempts to launch a second Xvfb on the **already active :92** and creates another Chrome profile. Replaced by `veyra-obs-backend-v1.sh`.

## OBS isolated GPU probe result and cleanup repair (24 October 2026)
- User ran the v1 staged :93 test. OBS 30.2.3 started, read its modules and initialised OpenGL 4.5, but reported **Mesa llvmpipe (LLVM 19.1.7)** as its renderer: this is **CPU software rendering, not an Intel GPU-backed OBS scene**. The 14-second `timeout` correctly returned 124. This is a **hardware-rendering acceptance blocker** for the 4 GB Pentium N4200 until an Intel-backed compositor path is verified.
- The first probe exited with `xvfb_pid: unbound variable` because an EXIT handler outlived the function-local variable. Node C subsequently verified that the throwaway `:93` Xvfb remained alive as user veyra, while the authenticated `:92` Xvfb, VEYRA kiosk, virtual capture/VNC and original recorder were unaffected.
- Corrected `gateway/trusted/veyra-obs-backend-v1.sh`: global trap state, new `recover` action that strictly validates the :93 X lock PID, process owner and full original Xvfb command before signalling it, plus an explicit **BLOCKED** exit when OBS reports llvmpipe/software rasterisation. GitHub safety CI passed.
- The recovery command after downloading the updated script is `sudo bash ~/veyra-obs-backend-v1.sh recover`. It does **not** affect :92. Do not rerun the isolated :93 graphics probe; it has already given its answer.
- A second read-only Node C audit confirmed `cage` is currently the physical compositor and Intel Mesa DRI drivers are installed. The NEXT OBS rendering experiment should determine whether a separate GPU-backed Wayland session can run OBS while `:92` remains the screen-capture input. Do not launch OBS directly on the existing physical Cage compositor without an isolation plan—it could obscure the kiosk. If no low-resource accelerated session is possible, flag a hardware limitation rather than falling back to llvmpipe or resurrecting standalone FFmpeg.
- OBS's Linux XSHM input implementation explicitly allows a separate `server` value when `advanced` is true, so `:92` can remain the captured server even if OBS's own rendering context changes: https://github.com/obsproject/obs-studio/blob/master/plugins/linux-capture/xshm-input.c . This is an implementation capability, **not** proof of achieved capture quality.

## Next gates after isolated OpenGL proof
- Stage OBS GUI on permanent separate :93 with a restricted VNC/SSH management endpoint, import or create XSHM (:92) plus Pulse audio scene.
- Verify native source, headless compositor/OBS render frame timings, SRT output start/stop and Intel encoding selection.
- Test a modern local receiver on the laptop physical screen. Evaluate GStreamer dependency footprint separately before installing any optional packages.
- Confirm quality by **actual eyesight and metrics** before touching recorder and kiosk.

## External technical references
- OBS launch parameters: https://obsproject.com/kb/launch-parameters
- OBS sources: https://obsproject.com/kb/sources-guide
- OBS SRT guide: https://obsproject.com/kb/srt-protocol-streaming-guide
- OBS hardware encoding: https://obsproject.com/kb/hardware-encoding
- Debian OBS package: https://packages.debian.org/trixie/obs-studio
