# JNS MQTT service high availability — design, not yet deployed

**Status:** Design for later CT212 redundancy. Existing live service remains
`mqtt-infra-a.home.arpa:1883` on CT212 (Node B). No MQTT service cutover today.

## Client configuration
All MQTT clients should **eventually** reference `mqtt.home.arpa:1883` rather
than a particular broker hostname or IP. Use a service-specific DNS record,
controlled by the existing Sheriff DNS pair. No per-client reconfiguration at
failover. The service name can have both AAAA (preferred) and A records.

## Active–passive brokers
- Broker A: existing CT212 / Node B; new Broker B: separate Node A LXC.
- Exactly one broker must have the active service address and accept clients.
- If L2/network topology permits, use a dual-stack **floating service address**
  tied to active broker ownership; DNS `mqtt.home.arpa` resolves to the
  floating address. Failover does not require rewriting DNS.
- If VIP is unavailable, Sheriff DNS switches the service record on promotion
  with short TTL; DNS caching/client reconnection may delay recovery. This is
  a fallback, not seamless failover.
- Configure distinct broker node names for management and health, separate from
  the MQTT service name; never use DNS round-robin for active–passive Mosquitto.
- Independent two-node monitor/watchdog plus a peer link, but **never** infer
  lease ownership only from 'peer ping lost'. A partition can split brain.
  Strict active-owner/lease logic with hardware/network fencing or fail closed
  when ownership is ambiguous. No forced promotion in a two-sided partition.

## MQTT state consistency
- Mosquitto is not an active-active clustered broker.
- Keep the subscriber/publisher user and ACL accounts consistent with secure
  secret distribution.
- Snapshot and transfer broker persistence **safely**, not by concurrently
  mounting/writing the same persistence database. Test persistence restoration,
  retained Zigbee2MQTT/HA discovery messages, durable session subscriptions,
  and QoS 1/2 behaviour.
- Stateless MQTT fan-out bridging **alone** does not guarantee full retained
  message, session, in-flight and queued-message failover semantics.
- Upon takeover check and refresh critical retained status/discovery state.
  Zigbee2MQTT and Home Assistant publishers should reconnect/reannounce.
  Commands during outage may be lost; never promise uninterrupted control.

## Client transition
1. Build standby without touching CT212 production subscriptions.
2. Replicate/restore broker config, ACLs and retained state to an isolated
   test environment. Verify no command duplication.
3. Establish tested single-owner failover / fencing and floating endpoint.
4. Create `mqtt.home.arpa` through Sheriff DNS and test resolution on Node A,
   Node B, HA-General, HA-Primary, CT214 and IoT endpoints.
5. Change each client **once** from hard-coded broker name to stable service
   alias; test reconnect and retained-message handling.
6. Test Node A/B link loss, CT212 failure, standby startup, return-to-primary
   and fail-closed simultaneous ownership edge cases.
7. Only then enable fully automatic promotion. Keep controlled rollback.

## Scope
This design includes future HA-Security VM906 consumer, HA-General MQTT area
catalogue, Welcome Home presence Statestream and Zigbee2MQTT. It must preserve
the JNS DNS-name-first, IPv6-first policy and not duplicate Sheriff DNS or NTP.

**The current area/presence installation uses the existing broker** until the
above migration gates are completed. Changes to `mqtt.home.arpa` are not live.
