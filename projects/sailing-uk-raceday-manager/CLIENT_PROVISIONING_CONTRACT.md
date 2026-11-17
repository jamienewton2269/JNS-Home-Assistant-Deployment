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
