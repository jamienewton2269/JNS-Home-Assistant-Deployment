# RaceDay Manager → Mobile Client Provisioning Contract (draft v0.1)
Status: **design contract, not implemented**. Android first, iOS later. Manager is authoritative. Telemetry and camera clients remain paused until tested provisioning.

## Provisioning lifecycle
1. Race officer signs into RaceDay Manager with explicit pairing permission.
2. Officer selects yacht, race/event, client role (telemetry-only, camera+telemetry), and creates a **single-use short-lived** pairing invitation.
3. Manager displays a QR with an HTTPS origin and opaque random invitation ID; no permanent credential or DDNS token in QR.
4. Android client scans QR, verifies TLS identity, fetches a limited public invitation description, presents yacht/club/race for user confirmation.
5. Client creates its own keypair and submits public key plus device capabilities over HTTPS.
6. Officer approves the device binding; manager issues short-lived device credentials scoped to the yacht, event and allowed services. Persist credential metadata server-side, not secrets in logs.
7. Client receives configuration and acknowledges version/hash; manager shows last-applied configuration, health and connectivity.
8. On reassignment/revocation, rotate credentials and prevent old device access. Expiry and race changes require explicit rules.

## Configuration document (illustrative, versioned)
```json
{
  "schema_version": 1,
  "config_revision": 1,
  "club_id": "club-identifier",
  "event_id": "event-identifier",
  "race_id": "race-identifier",
  "yacht_id": "yacht-identifier",
  "device_id": "device-identifier",
  "roles": ["telemetry"],
  "telemetry": {
    "enabled": true,
    "transport": "mqtts",
    "endpoint": "mqtts://receiver.example:8883",
    "topic_prefix": "raceday/v1/club/event/yacht",
    "interval_ms": 1000,
    "qos": 1,
    "offline_buffer_seconds": 300
  },
  "video": {"enabled": false},
  "start": {"utc": null, "countdown_enabled": false},
  "expires_utc": "ISO-8601 UTC timestamp"
}
```
All values are placeholders. Do not embed credentials in this JSON. Signed or authenticated configuration transport, device key binding, hostname/certificate validation and a clear rollback procedure are required.

## Manager-side acceptance tests
- QR expires and cannot be reused.
- Pairing requires officer permission and explicit approval.
- Client rejects wrong hostname, invalid TLS, expired invitations and mismatched yacht assignments.
- Reissued config increments revision and client acknowledges it.
- Revocation prevents further ingest; no permanent secrets in logs/QR.
- Six simulated clients can pair and receive distinct yacht configurations.
- Offline race operation remains available for already provisioned clients.
- Mobile camera stream configuration stays independent of GPS telemetry.
- Changes to an active race cannot silently retarget devices.

## Development gate
**Do not resume Android telemetry ingestion, MQTT receiver integration or new video receiver work** until a manager-side provisioning API and simulated-client tests pass. Existing preliminary MediaMTX receiver is preserved. Apple support follows tested Android provisioning.


## Two equally supported deployment paths — 2026-11-17 decision

**A. In-person pairing (QR):** Race officer creates a single-use, expiring QR invitation for a yacht. Competitor scans it on Android, confirms race/yacht, completes secure device registration and receives configuration. Keep this for on-site registration, late entries and replacement devices.

**B. Remote pre-race provisioning (night before):** Race officer prepares tomorrow's race and assignments, then generates per-yacht, per-competitor expiring invitation links. Deliver via email or copy/share via a messaging application. A link opens the installed Android app (verified HTTPS app link); if not installed, show an installation guide and then resume onboarding. App confirms the club, event, race and yacht, generates device keypair, registers with the manager and downloads scoped configuration. An invitation is not a long-lived credential and must not by itself permit unreviewed yacht reassignment. For clubs requiring officer approval, the invitation is a pending request until approved; for pre-approved entries, officer authorisation occurs at invitation issuance with strict one-device/one-use limits.

**Manager readiness dashboard:** Show invited / opened / registered / configured / ready / expired / revoked / needs attention, per yacht and device; last configuration revision acknowledgement; last contact and device capability checks. Provide resend, revoke, reissue and replacement-phone controls.

**Race-day validation:** Device checks for config changes, assigned yacht, GPS permissions, power and connection; can continue with a previously authenticated, cached configuration when offline. Do not promise that an unpaired phone can first register offline. Any race start changes must use versioned config, acknowledgement and explicit timing safeguards.

**Security:** HTTPS deep links, high-entropy opaque invitation, short expiry, single use, bind device key at registration, prevent link previews or email scanners from consuming tokens merely by GET, rate-limit redemption, officer audit trail, avoid PII in URLs, avoid exposing credentials in QR or email. For remote pairing, use a reachable trusted HTTPS manager endpoint or a securely operated relay; offline-only managers cannot directly provision phones over the internet. No mandatory central Sailing-UK service for local operation.

**Acceptance tests:** Generate six invitations in one batch; remotely redeem on six simulated devices; verify unique yacht binding, app-link fallback, duplicate/replayed/expired invitations rejected, wrong yacht rejected, reissue/revocation, lost network and cached configuration, readiness dashboard status, QR and remote invitations both using the same provisioning API.

**Sequencing:** Complete both manager-side invitation delivery modes and simulated-client tests before resuming Android and telemetry receiver development. Apple client support follows Android, reusing the same contract.
