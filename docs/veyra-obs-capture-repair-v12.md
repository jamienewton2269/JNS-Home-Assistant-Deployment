# VEYRA OBS Capture Repair v1.2

24 October 2026 — experimental code published and statically validated. **No Lenovo runtime deployment or programme-video acceptance has yet been confirmed.**

## Repair

The OBS 30.2 Linux capture plugin on VEYRA exposes the source identifier xshm_input, not xshm_input_v2. The v1.1 startup log therefore reported the latter source ID missing. V1.2 preserves authenticated ITVX X display :92 and creates OBS on disposable :93, recording locally only. The scene uses advanced=true, server=:92 and screen=0.

Preserved: Chrome/provider logins, Cage physical kiosk, VNC, existing FFmpeg legacy recorder, Windows dual boot, earlier OBS recordings and all v1.1 scripts. No standalone FFmpeg pipeline or SRT connection is started.

The private OBS WebSocket 5 controller checks that the video source, existing PulseAudio monitor and active scene match the expected configuration. It calls StopRecord and waits for recording status to change before terminating the temporary OBS process. Files go to unique run directories under /opt/veyra/obs-backend-v1/av-qa-v12/runs.

## On VEYRA, install and audit

Run the commands below as jnsadmin. They fetch one pinned GitHub revision. Installing the Python helper does not start a service or change OBS globally.

~~~bash
REV=7eb5dc912de9c5effd0834cdf7d350a19047fd49
BASE="https://raw.githubusercontent.com/jamienewton2269/JNS-Home-Assistant-Deployment/$REV/gateway/trusted"

curl -fL "$BASE/veyra-obs-ws-control-v1.2.py" -o ~/veyra-obs-ws-control-v1.2.py &&
curl -fL "$BASE/veyra-obs-live-av-quality-v1.2.sh" -o ~/veyra-obs-live-av-quality-v1.2.sh &&
python3 -m py_compile ~/veyra-obs-ws-control-v1.2.py &&
bash -n ~/veyra-obs-live-av-quality-v1.2.sh &&
sudo install -D -o root -g root -m 0755 ~/veyra-obs-ws-control-v1.2.py /usr/local/libexec/veyra-obs-ws-control-v1.2.py &&
sudo bash ~/veyra-obs-live-av-quality-v1.2.sh audit
~~~

Verify that the source currently displays moving imagery in the existing :92 VNC session. A non-DRM moving test page suffices for initial source capture. Do not attempt to defeat video copy protection.

## Single recording

~~~bash
sudo bash ~/veyra-obs-live-av-quality-v1.2.sh run
~~~

V1.2 produces one roughly 18-second MKV in a new private run directory, no older clips overwritten. It checks sources via OBS WebSocket, verifies clean MKV probe metadata and non-identical decoded frames sampled with mpv at 3, 8 and 13 seconds. Ephemeral image samples are deleted on exit.

On PASS, note the printed CANDIDATE_MKV path and use the printed replay command, substituting that exact file. Visual confirmation of moving picture and audible, synchronised programme sound is still mandatory.

## Rollback and future work

The original production recorder remains running and unchanged throughout the v1.2 test. The isolated OBS/Xvfb trial is removed from memory on normal exit; saved MKVs and logs remain for evidence. If recording close was not acknowledged, consider the resulting MKV unverified. Do not promote this code to production until real source picture, audio, decoding, and recovery are demonstrated.

Only after recording acceptance: investigate llvmpipe/Intel GPU rendering, SRT restreaming, source cadence and motion quality, 30-minute guarded rolling buffer, and transactional kiosk integration.
