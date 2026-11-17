# JNS Hikvision Talk – Kitchen Tablet v1.9 MQTT and alarm-safe display (staged)

**Status: implementation starter validated; NOT installed, no APK built/published.**

## Existing production preserved
- Package `com.frontdoor.hikvisiontalk`, release **1.8 / versionCode 9**, Node C `/opt/jns-apk-updates/releases/com.frontdoor.hikvisiontalk`.
- Node C publisher: `/opt/jns-apk-updates/publish.py`, HTTPS updater on `https://nodec.home.arpa:8766` (existing published manifest still contains historical HTTP URL; verify/update client path before next release).
- Editable Android 4 application source was last kept on SAGE, `H:\CurrentProjects\Cameras\HikvisionTalk\current\`; not found on Nodes A/B/C or in the GitHub deployment repository. Do not rebuild from APK without original signing key/source.
- Broker: `mqtt-infra-a.home.arpa:8883`, TLS, custom JNS root CA, username/password and ACL; **no** 1883/1885 fallback. Current SSL server SAN includes `mqtt-infra-a.home.arpa`.
- Home Assistant now one instance, VM905 on Node B. Alarm entity: `alarm_control_panel.house_alarm`. Doorbell topic already published: `jns/security/doorbell/press`, `pressed`, QoS 1, NOT retained. Do not duplicate its producer.

## State contract

New **staged** HA package `jns_kitchen_tablet_mqtt.yaml` publishes retained QoS 1 JSON to `jns/tablet/kitchen/alarm/state` whenever alarm changes / HA starts / every 5 seconds:

```json
{"v":1,"state":"armed_away","ts_ms":1795000000000}
```

App must check sender timestamp within last 15 s, connected MQTT over certificate-verified TLS, and monitor local monotonic freshness. **Any missing/unrecognized/stale/unknown/pending/arming/triggered state forces PRIVACY_LOCK.** On disconnection immediately stop video and audio and cover the video surface; don't continue showing the last decoded video frame.

## Screens and doorbell

| Verified current alarm state | Default tablet display | Doorbell event |
|---|---|---|
| `disarmed` | Front-door live camera | Start incoming camera **speaker** audio up to 45 s; never open tablet microphone |
| `armed_home` | Front-door live camera | Same as above; manual push-to-talk remains separate |
| `armed_away` | Opaque full-screen **guest QR** only, no video thumbnail or decoded-frame bleed-through | **Ignore autoplay video AND incoming audio**, no override |
| `arming`, `pending`, `triggered`, unavailable/unknown/stale | Opaque privacy lock | Ignore autoplay |

Fresh `armed_away` event takes precedence over any prior listening session; stop audio and native stream before switching screens. Ignore retained doorbell events and debounce QoS1 duplicates. Use a five-second update heartbeat and fifteen-second client expiry to limit stale exposure when HA fails (network failure detection should lock sooner). Suppress notifications revealing video preview on away mode.

**QR privacy:** currently `app_local_jns_guest_alarm` v0.1.3 on VM905 (LAN HTTPS port 8449) is a **staging landing page** only: it returns `405` for all POST requests. It cannot enroll passkeys or operate the alarm yet. The QR must contain only the authenticated service URL (no PIN, token, alarm state, magic disarm link or secret in the QR). Do not advertise functional guest disarm until enrollment and server-side authorization are implemented.

**Hidden keypad:** on away display, three taps in the top-right hidden corner within 1.8 s show a local PIN overlay for up to 30 s; hide on timeout/away exit. This is only a hidden launcher, **not authentication**. Entered PIN must be verified by a rate-limited, authenticated server-side HTTPS endpoint, never hard-coded into APK or sent to MQTT. Permit only `disarmed` or `armed_home` after server authorization. Never add MQTT alarm-control write permissions to tablet credentials. Both QR and keypad must avoid storing or revealing an alarm PIN on the screen.

## Integration work before shipping APK

1. Recover **latest** SAGE source and existing signing/build tooling; determine concrete callbacks for video `hideAndStopCamera()`, display/QR screen, and already-working incoming audio. The `DisplayPolicy.java` in this folder is tested reusable logic, not integrated into that app.
2. Implement Android 4-compatible MQTT subscriber (Paho Java or similar) with trusted internal CA, TLSv1.2 explicitly enabled where supported, strict `mqtt-infra-a.home.arpa` certificate hostname validation, unique per-device ID, dedicated **read-only ACL** for exactly two topics. Never embed credentials in distributable APK; provide supervised local pairing. Fail closed if TLSv1.2/hostname validation is unavailable.
3. Integrate `DisplayPolicy` on Android UI thread, with opaque full-screen privacy cover **above** native SurfaceView and audio decoder, `FLAG_SECURE`, no live video on away mode even after screen wake, pause/resume or doorbell.
4. Finalize guest passkey service and rate-limited local PIN authorisation **separately**; no client-side alarm code checking, no anonymous disarm endpoint.
5. Stage/backup/validate Home Assistant package, add dedicated read-only broker identity, reload automations at a quiet period; verify retained state, fresh heartbeat, privacy race tests and MQTT interruption behaviour before marking enabled.
6. Build signed update with same package/signature, **versionCode > 9**, smoke-test on an Android 4 test unit, then atomically publish through Node C publisher. Check TLS update URL mismatch in current `latest.json` before releasing.

## Local tests

JDK8+ may compile the Java 7-compatible policy and test harness without Android:

```sh
mkdir -p build
javac --release 8 -d build DisplayPolicy.java DisplayPolicyTest.java
java -cp build DisplayPolicyTest
```

The above confirms screen priorities and corner-PIN launcher only. No network, MQTT, camera, PIN authorization, real APK or end-to-end alarm control is covered by these unit tests.