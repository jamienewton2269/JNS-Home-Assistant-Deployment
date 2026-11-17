# Sailing-UK RaceDay Manager — Master Recovery and Development Authority
Checkpoint: 2026-11-17. Owner: JNSystems (https://jnsystems.xyz); project: https://sailing-uk.org.

## Authority and orchestration
RaceDay Manager is the **primary development stream** and authoritative owner of race configuration, yacht/crew assignments, handicaps, starts, results, telemetry pairing and broadcast data. Related Android RaceCam, future Apple client, telemetry receiver, video receiver and OBS integrations must follow manager-defined configuration contracts. Do not independently advance telemetry or mobile integration before the manager can securely issue client configuration. Existing preliminary video receiver works to a limited degree; inspect and preserve, do not rebuild unnecessarily.

## Immediate sequencing (agreed 2026-11-17)
1. Audit actual code, branches, test results and artifacts before making implementation claims.
2. Complete manager core, first-run wizard, justified presets, always-available advanced settings, local user profiles, adaptive guidance.
3. Implement encrypted profile export/import (USB, download, email attachment), with Argon2id + authenticated encryption, merge/replace preview; never export credentials or permissions.
4. Implement familiar local login and optional Google/Microsoft/Apple OpenID Connect; optional Google Drive/OneDrive user-owned profile sync, separately authorised. All race operations remain offline-capable.
5. Implement manager-issued client configuration schema, short-lived single-use QR pairing, device identity, HTTPS trust, signed/expiring credentials, yacht assignment, safe revoke/rotate/re-pair; test with simulated clients.
6. **Only after step 5 is working** resume Android RaceCam client and telemetry receiving server, including integrated local MQTT for small clubs and optional external MQTT for regattas. Apple client follows Android.
7. Integrate the existing preliminary video receiver (MediaMTX/SRT) and OBS. Video separate from GPS telemetry.
8. Validate six-yacht GPS simulation, resource use, offline/failover recovery, two OBS maps and synchronized countdown. Advance to production tests and installers.

## Product and platform
Standalone, low-cost open-source race manager. Debian 13/Linux-first native systemd/LXC and independent Windows 10/11 installation; browser UI for phone/tablet/desktop; Python + SQLite prototype. No Docker, no mandatory HA, Proxmox, cloud, central account service or external broker. Do not change unrelated production services without approval. Use JNS MCP and Node C GitHub runner; Windows test host SAGE. Do not use Desktop Commander.

## Race functions
Yacht names, sail numbers, classes, skipper/crew, fleet and device assignments, optional Club Manager/Joomla import, events/races/entries, configurable Portsmouth Yardstick and other time-on-time handicap rules, race starts and manual/electronic finish timing, DNS/DNF/RET/DSQ, provisional corrected results, approvals/locking, series scoring, audited corrections. RaceDay Manager is the source of truth. External imports must not silently overwrite active races.

## Telemetry and broadcast
RaceCam Android sends GPS separately from video. MQTT 5 preferred, TLS, QoS 1, authenticated device identity, timestamps, accuracy/fix quality, heading/speed, heartbeat, buffering, duplicate and out-of-order protection, primary/fallback tracker policy. Integrated MQTT default, optional external broker. Six simulated yachts for test. Two separate OBS browser-source maps: actual on-water positions and handicap-adjusted provisional race standings, with clear distinction. Start countdown and local phone gun sound require measured synchronisation before official use. MediaMTX video receiver already exists at preliminary stage; inspect before modifying.

## Guidance: important correction
Guidance size changes with **repeat successful use of a particular task by a particular user**, NOT because a step was completed in the current workflow. First use is full hand-holding; repeated use gradually reduces screen footprint; experienced use is brief. A persistent one-click corner Help control can restore full help at any time. User-chosen full help overrides adaptation. Experience per task: yacht registration, race creation, handicaps, entries, timing, telemetry, OBS, accounts. Every recommended preset displays a concise nearby justification. Advanced authorised users may change all supported settings at any time, with impact warning and guided restoration.

## Profiles and identity
Familiar sign-in: local account or Google/Microsoft/Apple; optional Club Manager/Joomla identity linking. Separate identity, authentication, personal preferences and club permissions. Portable profile carries accessibility, layout, per-task guidance history, personal presets; **never** credentials, MFA secrets, OAuth tokens, admin rights, private club records or race DB. Offline local cache. Optional user-owned Google Drive app storage or OneDrive app folder sync; Apple login separate from iCloud sync. Encrypted .raceday-profile export to USB/computer or email-to-self attachment, import with password, validation, merge/replace and rollback. Cross-club permissions never transfer.

## Branding
Original stationary Sailing-UK navy outline yacht logo; original animated JNSystems rotating-ring GIF; About links sailing-uk.org and jnsystems.xyz; memorial for Becki (original cartoon portrait) and Dad Ken Newton. Angel image pending. Preserve original supplied assets; do not invent replacement artwork.

## Verification / historical status
Previous chat reported local ZIP prototypes v0.1–v0.6 with Python/SQLite, six-yacht simulation and adaptive-guidance work. These are **historical claims**, not verified GitHub commits or production readiness. Latest reported ZIP: Sailing-UK-RaceDay-Manager-v0.6-experience-guidance.zip. Verify artifacts and tests. Intended dedicated repo jamienewton2269/Sailing-UK-RaceDay-Manager was NOT found by GitHub search on 2026-11-17. This checkpoint is provisionally stored in JNS-Home-Assistant-Deployment under projects/sailing-uk-raceday-manager; migrate to dedicated repo when available. Do not confuse this documentation location with the source code's actual location.

## Immediate resume instruction
Inspect the actual repositories and local packages; report what exists and is tested; preserve code; continue RaceDay Manager user profiles and client provisioning contract first. Keep mobile/telemetry development paused until manager-driven pairing/configuration works. Do not claim completion without tests.

## Official product line (approved 2026-11-17)
> **RaceDay Manager modernises club racing without forcing clubs to abandon their traditions.**

Use this exact wording as the primary product tagline in RaceDay Manager branding, welcome/about screens, project README and future marketing. Do not change wording without approval. Support traditional ancillary, hybrid and fully digital race-control modes.
