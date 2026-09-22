# JNS IoT Gateway architecture

## Design rules

1. One maintained codebase; many deployable gateway nodes.
2. Core functions are dependency-light and normally non-resident.
3. A protocol module is installed only when its profile is selected.
4. One physical radio has one owner. No implicit Zigbee/Thread multiprotocol sharing.
5. Matter is modelled as an IP application layer; Thread owns the Thread radio.
6. Profile changes are validated before resources are transferred.
7. Network syslog carries operational/security/audit events, not device telemetry.
8. A syslog outage never blocks protocol operation; failed messages use a bounded spool.
9. Hardware bindings use stable `/dev/serial/by-id/...` identities.
10. Future Guardian integration must fence the old consumer before coordinator ownership moves.

## Runtime model

The core CLI is invoked at boot to apply the selected profile and by a low-frequency systemd timer for health/state-change checks. It is not a permanent daemon. In the initial `zigbee_serial` profile the only protocol process kept resident is `ser2net`.

Profiles defined but not implemented are deliberately rejected. This prevents a configuration typo from causing a partially installed or unexpectedly loaded protocol stack.

## Initial profile

`zigbee_serial` renders a dedicated ser2net configuration and service. The listener accepts at most one client and does not kick the current client. Both HA cluster nodes may be configured with the same socket URI, while Guardian/fencing controls which HA/ZHA instance is permitted to connect.

## Future profiles

- `zigbee2mqtt`: direct local serial ownership by Zigbee2MQTT; ser2net absent.
- `thread_otbr`: dedicated Thread radio owned by OpenThread Border Router.
- `matter_thread_edge`: OTBR plus Matter/Thread integration helpers; Matter itself does not claim the radio.
- `maintenance`: core only, no protocol owner.
- `disabled`: safe fenced state.

## Syslog

The core emits RFC 5424-compatible records over UDP, TCP, or TLS. TCP/TLS uses octet-count framing. Events include node/profile lifecycle, radio ownership, health changes, updates/rollback, fencing, configuration validation failures, and security policy events. The spool is event-count bounded and flushed by the health timer.
