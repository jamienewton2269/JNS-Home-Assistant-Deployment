#!/usr/bin/env bash
# Veyra capture experiment v1 - FFmpeg only, isolated from kiosk and recovery VT.
set -Eeuo pipefail
ROOT=/home/jnsadmin/veyra-ffmpeg-test
PIDFILE="$ROOT/ffmpeg.pid"
case "${1:-}" in
 install)
   [ "$(id -u)" -eq 0 ] || { echo "sudo required"; exit 2; }
   apt-get update
   DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends ffmpeg pulseaudio-utils
   install -d -o jnsadmin -g jnsadmin -m 700 "$ROOT" "$ROOT/segments"
   echo "FFMPEG_READY. Does not modify Veyra kiosk or OBS installation."
 ;;
 start)
   [ "$(id -un)" = jnsadmin ] || { echo 'Run start as jnsadmin'; exit 2; }
   mkdir -p "$ROOT/segments"
   if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then echo "Already recording, PID $(cat "$PIDFILE")"; exit 3; fi
   [ -S /tmp/.X11-unix/X92 ] || { echo "Virtual X11 :92 is not running"; exit 4; }
   command -v ffmpeg >/dev/null || { echo "ffmpeg missing"; exit 5; }
   # Capture visible desktop at 1280x720, not physical VT1.
   # Audio capture is opt-in: require an explicit PulseAudio monitor name.
   # A default audio device could otherwise capture microphone or unrelated audio.
   AUDIO_SOURCE="${2:-}"
   if [ -n "$AUDIO_SOURCE" ]; then
     pactl list short sources | grep -Fq "$AUDIO_SOURCE" || { echo "Unknown audio source; use pactl list short sources"; exit 6; }
     ffmpeg -nostdin -hide_banner -loglevel info -f x11grab -framerate 15 -video_size 1280x720 -i :92.0 \
       -f pulse -i "$AUDIO_SOURCE" -map 0:v:0 -map 1:a:0 \
       -c:v libx264 -preset ultrafast -pix_fmt yuv420p -g 30 -sc_threshold 0 \
       -c:a aac -b:a 128k -ar 48000 -f segment -segment_time 10 -segment_wrap 6 -reset_timestamps 1 \
       -segment_format mpegts "$ROOT/segments/capture-%02d.ts" >"$ROOT/capture.log" 2>&1 &
   else
     ffmpeg -nostdin -hide_banner -loglevel info -f x11grab -framerate 15 -video_size 1280x720 -i :92.0 \
       -map 0:v:0 -an -c:v libx264 -preset ultrafast -pix_fmt yuv420p -g 30 -sc_threshold 0 \
       -f segment -segment_time 10 -segment_wrap 6 -reset_timestamps 1 \
       -segment_format mpegts "$ROOT/segments/capture-%02d.ts" >"$ROOT/capture.log" 2>&1 &
   fi
   pid=$!; echo "$pid" >"$PIDFILE"
   sleep 2
   if ! kill -0 "$pid" 2>/dev/null; then
     echo "Capture exited:"; tail -n 40 "$ROOT/capture.log"; rm -f "$PIDFILE"; exit 7
   fi
   echo "FFMPEG_RUNNING PID=$pid on virtual display :92"
   echo "Buffer: six 10-second TS segments (~60 seconds). Audio: ${AUDIO_SOURCE:-NOT ENABLED}"
   echo "Chrome remains interactive only through a separate viewing solution; no protected-playback claim."
 ;;
 status)
   if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then echo "Capture PID: $(cat "$PIDFILE")"; else echo 'Capture not running'; fi
   ls -lh "$ROOT/segments/" 2>/dev/null || :
   tail -n 8 "$ROOT/capture.log" 2>/dev/null || :
 ;;
 stop)
   if [ -f "$PIDFILE" ]; then
     pid=$(cat "$PIDFILE")
     # Only terminate the PID if it remains an FFmpeg capture from this test.
     if [ -r "/proc/$pid/cmdline" ] && tr '\0' ' ' <"/proc/$pid/cmdline" | grep -Fq "$ROOT/segments/capture-%02d.ts"; then
       kill -TERM "$pid"; echo "Requested capture stop PID=$pid"
     else echo "PID no longer identifies the capture; no signal sent"; fi
     rm -f "$PIDFILE"
   fi
 ;;
 obs-close)
   # Terminate only OBS PID recorded by original test launcher; do not touch Chrome/Xvfb.
   PIDS=/home/jnsadmin/veyra-obs-test/pids
   if [ -r "$PIDS" ]; then
     obs_pid=$(sed -n '4p' "$PIDS")
     if [[ "$obs_pid" =~ ^[0-9]+$ ]] && [ -r "/proc/$obs_pid/comm" ] && [ "$(cat "/proc/$obs_pid/comm")" = obs ]; then
       kill -TERM "$obs_pid"; echo "Closed test OBS PID $obs_pid"
     else echo 'OBS not found at recorded PID; nothing stopped'; fi
   else echo 'No original test process manifest'; fi
 ;;
 *) echo 'Usage: sudo bash SCRIPT install | bash SCRIPT start [PulseAudio_MONITOR] | status | stop | obs-close'; exit 2;;
esac
