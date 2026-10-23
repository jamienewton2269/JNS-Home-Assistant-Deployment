# VEYRA v0.7.1 — Actual advert-transition IMAGE recognition

Status: source published for Lenovo pilot, NOT YET VALIDATED ON REAL ITVX AD BREAKS.

## Purpose

No fixed advert duration, no assumed countdown. Recognise provider-specific advert entrance and exit graphics from the existing virtual ITVX Chrome display :92.

## Components

- Passive 5 fps 160x90 greyscale pixel sampler on the EXISTING :92 Xvfb display; never restarts provider Chrome or VNC.
- Rolling frames for the **last 20 seconds in RAM only**; snapshots sent on demand to localhost training UI.
- User-labelled provider-entrance and provider-exit *numeric* fingerprints persist; no programme video, audio, or full-size screenshots are saved by the detector.
- Match two consecutive frames against a learned template, with independently learned "in"/"out" patterns; refuse arming if both look too similar to distinguish.
- Observe-only is default on every service start; observer logs candidate matches but cannot automatically cover until deliberately armed.
- A new visual-mode cover uses an INDETERMINATE travelling progress bar. It covers the physical output until recognised return-to-programme graphic, or manual End Cover. Zero ad-duration estimates.
- The existing virtual Chrome, login, VNC, physical Cage, watchlist, and media recorder are not reconfigured.
- Local UI: 127.0.0.1:8774 for visual training, 127.0.0.1:8773 for manual End Cover + display preview.

## Install order for users who haven't installed TV-night v0.7.0 yet

The TV-night shared-capture service has to exist for recognised ads to be covered during live TV.

Install TV-night v0.7.0 first (provides the GPU playback service). After it installs, the v0.7.1 installer updates ONLY its ad-cover controller, replacing the timer-based interface with the visual-recognition interface.

Do not rerun v0.7.0 INSTALL after installing v0.7.1; it would reintroduce its older timer controller.

## Install on the Lenovo

    curl -fL https://raw.githubusercontent.com/jamienewton2269/JNS-Home-Assistant-Deployment/main/gateway/trusted/veyra-advision-v0.7.1.sh -o ~/veyra-advision-v0.7.1.sh
    bash -n ~/veyra-advision-v0.7.1.sh
    sudo bash ~/veyra-advision-v0.7.1.sh preflight
    sudo bash ~/veyra-advision-v0.7.1.sh install
    sudo bash ~/veyra-advision-v0.7.1.sh status

The installer checks visual recognition with synthetic pixel patterns and validates one graphical cover frame without outputting it. Service is then launched in OBSERVATION mode. It does not automatically arm itself.

## Windows control

Start this tunnel, keeping PowerShell open:

    ssh -N -L 8774:127.0.0.1:8774 -L 8773:127.0.0.1:8773 jnsadmin@veyra

Open http://127.0.0.1:8774/ to label real provider transition images. Open http://127.0.0.1:8773/ to preview visual cover for 8 seconds and use End Cover in an emergency.

## Collect real ITVX evidence

1. In existing ITVX VNC browser, start a real programme (e.g. Emmerdale or Coronation Street) from your existing watchlist.
2. Before the first advert, check that /api/state shows CAPTURE ACTIVE. Keep mode OBSERVATION ONLY.
3. When the ITVX *entrance graphic* appears, immediately click Refresh Gallery; select the real transition frame and label AD STARTS. The gallery contains 20 seconds in RAM, and shows about one image per second.
4. When actual programme-resume / *exit graphic* appears, refresh and label PROGRAMME RETURNS.
5. Repeat with another advert break, collecting >=2 DISTINCT representative images for each direction. This also verifies whether ITVX uses a consistent bumper. If the graphics are visually identical in and out, image-only recognition CANNOT be trusted and auto arming will be refused.
6. Continue OBSERVE ONLY while another real break happens. Check logged entrance/exit detections and failures; manually End Cover if needed.
7. Arm from UI only after correct detections and no false positives have been observed. Arming too early may obscure programme content.
8. Recogniser matches are pixel signatures, NOT provider-confirmed ad SDK events. If confidence is poor, leave OBSERVE ONLY until provider-event telemetry is available.
9. If no real ITVX bumper is displayed at break transitions, this approach will not identify the break. Do not train an arbitrary advert picture as an ITVX bumper; that could cause false positives.

## No-assumption progress bar behaviour

The detector calls the cover controller only on actual recognised transition events:
  /api/vision/start --> display COVER ON, indeterminate moving bar, mute player if correctly identified.
  /api/vision/end --> display COVER OFF, restore original player mute state.
No fixed duration is used to decide when to start/stop covering ads.

Manually remove cover: click End Cover, or:

    sudo bash ~/veyra-advision-v0.7.1.sh uncover

If the detector sampling process fails, it requests an immediate uncover (fail-open). Stopping detector also triggers uncover. If controls fail, stop the local cover controller:

    sudo systemctl stop veyra-tv-adcover-v070.service

This exposes the programme (or adverts) but avoids keeping the picture hidden indefinitely. Restart only the cover controller after diagnosing it; Chrome and VNC must not be restarted.

## Limits before unattended operation

- User-confirmed training samples HAVE NOT BEEN PROVIDED for ITVX advertising graphics.
- Low-resolution visual signatures must be validated with several real breaks; this initial matcher may miss animated transitions or misclassify scenes.
- Intro and outro bumpers may look identical, requiring corroboration from browser DOM/player ad-period indicators, not invented timing.
- Video output/HMDI/monitor stacking still needs physical verification on the TV.
- Session audio muting is best-effort and must be checked on the TV.
- 4-hour TV-night playback has not been sustained-tested.
- No programme video/audio is retained by the recogniser; the separate existing player still owns its buffer and cleanup.
- Watching and watched-history entry are managed by the existing watchlist, not inferred from video capture.
