# JNS Front Door Video Intercom — v0.1 Implementation Handover

Status: **Phase A deployed to disk and validated on HA-Primary VM902; automation reload and press test still required.** Phases B–D not activated. Date: 2026-10-24.

## Established, working source

- HA-Security VM906 runs the recovered X15 `binary_sensor.alarmpanel_kc868_a16_x15` → `siren.alarmpanel_kc868_a16_y01` chime (07:00–23:00) and `JNS Security - Publish Doorbell Press`.
- Event bus: MQTT topic `jns/security/doorbell/press`, payload `pressed`, non-retained, QoS 1, publishing at any hour.
- HA-Primary VM902 has enabled MQTT configuration `mqtt-infra-a.home.arpa` and mobile app client SM-S721B with `notify.sm_s721b`.
- HA-General VM905 has ONVIF Tapo C210 `camera.c210_mainstream`; this has been used as the Kitchen Dog Camera. **Do not presume it is the front-door camera.**
- HA-Primary Cameras dashboard already shows generic `camera.c210_home_arpa`. This is not an approved front-door media path and must not be repurposed blindly.
- HA-General existing MQTT security lights consumer is `automation.jns_doorbell_mqtt_night_security_lighting`.

## A — Mobile press notification (configuration staged)

File: `/config/automations.yaml` on HA-Primary, automation ID `jns_primary_doorbell_phone_notification_v1`.
MQTT `pressed` → `notify.send_message` to `notify.sm_s721b`, title `Front doorbell`. Five-second execution lockout.
- GitHub guarded apply `gateway/doorbell/ha-primary-mobile-doorbell-apply.py`, triggered by `gateway/doorbell/ha-primary-mobile-doorbell-apply.request`.
- Verified `ha core check` exit 0, SHA check, backup `/config/.jns_doorbell_backups/ha-primary-automations.before-mobile-doorbell-20261024T191754Z.bak`.
- Activation: HA-Primary → Developer Tools → YAML → **Reload automations**. This may interrupt active automations; choose an idle interval.
- Test one real button press and confirm mobile alert once. Do not test with retained MQTT publishes.
- Second mobile recipient requires registration on HA-Primary; the audit currently found only one.

## B — Front door video viewer

Required to start implementation:
1. Confirm physical front-door camera make/model and DNS name, whether it supports RTSP/ONVIF and **bidirectional audio backchannel**.
2. Check authenticated HTTPS/WebRTC access for the phones, including off-LAN via authorised VPN/private remote access; never publish camera admin passwords or bare go2rtc listener on the public Internet.
3. HA-General VM905 provides camera ingestion, recording if eventually needed, go2rtc/WebRTC delivery, microphone backchannel, and media output. HA-Primary must **not** perform transcoding, FFmpeg/HLS/go2rtc, recording or audio processing.
4. HA-Primary controls a lightweight authenticated doorbell view/button. A notification tap navigates to this view via `url` / `clickAction` with companion-app notifier. The new notify entity's basic `notify.send_message` supports the reliable text alert, but deep-link extras require an explicitly verified compatible notification action.
5. Mobile OS constraint: iOS does not allow arbitrary background launching; Android `command_webview` requires optional Display-over-other-apps permission. Normal notification tap is the cross-platform default.
6. Native HA camera two-way audio is a Labs preview from Core 2026.11, currently later than HA-Primary/HA-General Core 2026.9. Use a supported, correctly authenticated WebRTC component in HA-General for now if a backchannel is confirmed.

## C — Camera speaker acknowledgement chime

- HA-General-only subscriber to `jns/security/doorbell/press`.
- Default OFF until the physical front-door camera speaker output and codec are verified.
- Play a short low-volume ding-dong (maximum 2–3 seconds) through the camera speaker **only when a tested media-output/backchannel is available**.
- For cameras compatible with go2rtc stream-to-camera, a local FFmpeg file source can be pushed to a backchannel; actual codec often needs `PCMA/8000`, but this must be checked per device. Do not assume an ordinary RTSP feed supports speaker playback.
- Set explicit scheduling/mute control, minimum interval between chimes, timed cutoff; avoid playing over an active conversation; do not enable camera's loud siren/alarm as a surrogate for the requested polite chime.
- Keep physical HA-Security siren Y01 independent: loss of camera, HA-General or HA-Primary must not stop the existing physical chime.

## D — Two-way voice

- Visitor mic audio and talkback only on user-initiated action with microphone permissions.
- Never automatically open the mobile mic on incoming ring.
- One active talk session at a time; explicit disconnect; 2-minute inactivity timeout; echo/feedback suppression and speaker volume control.
- No unattended audio capture/recording; HTTPS identity checks; avoid exposed unauthenticated RTSP/WebRTC and default credentials.

## Acceptance tests

- Doorbell press rings original HA-Security sounder and MQTT security lights exactly as before.
- Phone receives exactly one alert within expected LAN/mobile push delays.
- Tapping alert opens the **correct front-door camera**, not the Kitchen Dog Camera.
- Visitor video is smooth and usable with the mobile device away from LAN over a secure remote route.
- Push-to-talk works bidirectionally, with immediate microphone release after end.
- Camera speaker plays a distinct short, safe doorbell confirmation, then stops.
- Failure of camera or mobile app does not stop physical chime and does not leave speaker output latched.

## Sources

- HA Companion notification navigation: https://companion.home-assistant.io/docs/notifications/notifications-basic/
- HA Companion Android `command_webview`: https://companion.home-assistant.io/docs/notifications/notification-commands/
- go2rtc stream-to-camera: https://github.com/AlexxIT/go2rtc/blob/master/internal/streams/README.md
- HA 2026.11 camera two-way audio preview: https://contributors.home-assistant.io/blog/2026/10/24/camera-two-way-audio/
