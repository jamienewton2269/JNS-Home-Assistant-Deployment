# JNS HA905 Core API probe — dormant stage

This is a proposed **temporary local Home Assistant app**, not a replacement
for the existing HA-General, SSH, ESPHome or Steward integrations.

**Currently repository-only. NOT installed into VM905 or started.**

## Why

The existing three installed apps have no `homeassistant_api` grant. Home
Assistant requires an app explicitly granted that setting to use its Core API
proxy. This gives the app administrator-level access; do not repurpose another
app's token, copy `.storage/core.config_entries` or print bearer tokens.

## Safety envelope

- `homeassistant_api: true` is the sole elevated capability, and is
  administrator-equivalent inside Core.
- No host files, Docker socket, host network, ingress, ports, or stdin.
- `boot: manual_only`, `startup: once`: no unattended service or persistence.
- The one-shot `probe.py` executes exactly two GETs with fixed endpoints;
  no mutation, integration flows, alarm operations or API responses logged.
- No passwords, encryption keys, HA storage or identities are bundled.

## Release gates — do NOT install automatically

1. Operator explicitly authorises installing an admin-capable temporary app.
2. Take a fresh VM905 verified backup; confirm VM906 remains the sole active
   ESPHome/security owner, and six target security automations remain disabled.
3. Review source in this folder, locally build in an isolated/safe manner,
   confirm image/version, then copy only these files to a new HA local-app
   folder by a dedicated guarded Node C deployment workflow.
4. Install as a `manual_only` app and start **once**; capture HTTP statuses
   only. If both endpoints return HTTP 200, the auth path is proven.
5. Stop/remove app after confirming auth or if any gate fails. No ESPHome
   configuration flow is implemented in this read-only version.
6. A separate, explicitly permitted, exclusive-controller handover will be
   required to run the native ESPHome config flow and test physical security.
   Never activate a duplicate alarm/siren control client.

Do not treat source-level tests as an installed app or as ESPHome enrolment.
