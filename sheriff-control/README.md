# Sheriff Control (read-only) — staging

Sheriff Control v0.1 is deliberately a *read-only* Home Assistant observability layer. It does not modify DNS, DHCP, IPv6 advertisements, Proxmox settings or reservations.

## Deployment invariant
- HA905 / HA-General only displays data.
- NodeC collects CT247 / CT248 / CT249 service health, revision, DNS records, fixed reservations, leases and bounded logs.
- NodeC publishes one MQTT snapshot to the existing broker CT212.
- Use existing MQTT integration in Home Assistant; 60-second interval.
- No new database, custom cards, DNS engine, or privileged HA SSH permissions.
- Changes to records (future v0.2) must use the existing revisioned Sheriff publisher, with validation, preview, administrator confirmation, verification and rollback.

## Current status
Package built and syntax checked in the working session, but it has **not been installed** on nodeC or HA905. Before enabling, verify SSH access, broker credentials/ACL and HA MQTT YAML configuration. Evaluate MQTT attribute-size limits with real production payload.

## Rollback
Disable the nodeC systemd timer, then remove HA MQTT sensor; no Sheriff service modifications.

## Installer artifact
The matching downloadable staging bundle is `sheriff-control-v0.1.zip` in the ChatGPT conversation. Its deployment steps are in its README.

## Acceptance
1. CT247, CT248, CT249 visible with actual status and revision; unreachable nodes show unavailable/error.
2. Read-only DNS A/AAAA entries and DHCP reservations available, with lease and warning excerpts.
3. No writes, restarts, lease renewals or port exposure from the collector.
4. On failure, stop timer and remove MQTT sensor without affecting DNS/DHCP.
