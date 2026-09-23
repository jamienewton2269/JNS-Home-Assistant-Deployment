# JNS IoT Gateway — Public Development Roadmap

**Status:** Active development  
**Current milestone:** v0.1 — external Zigbee serial gateway  
**Project home:** JNS Home Assistant Deployment repository

## Purpose

JNS IoT Gateway is a lightweight, profile-driven gateway platform intended to decouple Home Assistant from radio hardware that would otherwise be attached directly to a Home Assistant host or virtualization node.

The project is designed around standard Home Assistant and open-source interfaces. It is not intended to replace ZHA, zigpy, Zigbee2MQTT, OpenThread Border Router, Matter Server, MQTT, or other established projects. Its purpose is to provide a small, maintainable host for those technologies and make the radio/device edge independent of the Home Assistant compute node.

## Design principles

1. **One maintained codebase, many gateway roles.**
2. **Only selected modules are installed and loaded.**
3. **Low CPU, RAM and storage overhead.**
4. **No permanent JNS daemon where a oneshot command or low-frequency timer is sufficient.**
5. **Dedicated radio ownership by default.**
6. **Stable hardware identity using persistent device paths.**
7. **Wired networking preferred for serial-over-IP and infrastructure gateways.**
8. **Use established upstream projects and protocols wherever practical.**
9. **Operational logging is separate from device telemetry.**
10. **Gateway failure must not force Home Assistant reconfiguration where a stable logical endpoint can be retained.**

## Current implementation — v0.1

The initial profile is:

### `zigbee_serial`

A locally attached Zigbee coordinator is exposed to Home Assistant ZHA over a stable TCP endpoint using `ser2net`.

Current characteristics:

- persistent `/dev/serial/by-id/...` coordinator binding;
- one coordinator client at a time;
- no client pre-emption;
- lightweight systemd service;
- profile validation before activation;
- maintenance and disabled/fenced states;
- structured RFC 5424 network syslog;
- bounded local syslog retry spool;
- low-frequency health checking;
- protocol operation remains independent of remote logging availability.

Initial deployment targets are Debian-compatible systems such as a Proxmox LXC or a small Linux SBC/Raspberry Pi.

## Planned profile model

The gateway platform is intended to support multiple independently selectable profiles.

| Profile | Purpose | Runtime policy |
| --- | --- | --- |
| `zigbee_serial` | ZHA coordinator presented over ser2net | Implemented |
| `zigbee2mqtt` | Dedicated Zigbee2MQTT gateway with direct serial ownership | Planned |
| `thread_otbr` | Dedicated OpenThread Border Router | Planned |
| `matter_thread_edge` | Thread/Matter integration and health helpers | Planned |
| `maintenance` | Core-only maintenance/recovery mode | Implemented |
| `disabled` | Safe state with no protocol owner | Implemented |

A profile that is not selected should not leave its protocol stack installed, imported, listening, or resident merely because the common platform can support it.

## Zigbee deployment stages

### Stage 1 — external coordinator service

Validate the existing Zigbee coordinator through `ser2net` while retaining ZHA as the Home Assistant Zigbee implementation.

Goals:

- prove stable ZHA operation over the wired LAN;
- prove that changing the active Home Assistant instance does not require changing the coordinator configuration;
- measure reconnection behaviour and failure recovery;
- validate operational logging and health reporting.

### Stage 2 — dedicated SBC gateway

Move the Zigbee coordinator away from the virtualization hosts onto a dedicated wired SBC/Raspberry Pi-class gateway.

This removes the virtualization host containing the USB device from the Zigbee failure domain.

Home Assistant continues to use one logical coordinator endpoint.

### Stage 3 — recoverable redundant Zigbee gateways

Future hardware testing will investigate two matched SBC/Raspberry Pi gateways with compatible coordinators in an **active/passive** arrangement.

Only one coordinator may control the Zigbee network at any time.

The intended research areas are:

- validated coordinator/network backups;
- controlled recovery to a replacement coordinator;
- stable virtual service addressing;
- hardware identity validation;
- prevention of simultaneous coordinator ownership;
- recovery testing after gateway or coordinator hardware failure.

This is a future development stage and will not be enabled until suitable hardware and repeatable recovery tests are available.

## Zigbee2MQTT

A future `zigbee2mqtt` profile will allow the same gateway platform to become a dedicated Zigbee2MQTT node.

In that profile, Zigbee2MQTT should own the local coordinator directly. The serial bridge is not intended to remain in the data path merely to connect two services running on the same host.

The objective is to allow the deployment model to evolve without replacing the gateway management architecture.

## Thread and Matter

Thread and Matter are deliberately modelled as separate layers.

### Thread

Thread is the IPv6 mesh/radio network. A `thread_otbr` profile will use an established OpenThread Border Router implementation with a dedicated Thread radio.

Multiple Thread Border Routers may eventually be deployed where useful for coverage and resilience.

### Matter

Matter is an application protocol operating over IP, including Wi-Fi/Ethernet and Thread.

The gateway does not treat Matter as another radio driver. Matter-over-Thread uses the Thread Border Router to provide IP connectivity while the Matter controller remains an application-layer service.

The project will follow Home Assistant and Open Home Foundation architecture as these capabilities evolve rather than duplicating established Matter infrastructure unnecessarily.

## Observability

Every gateway can expose lightweight operational visibility.

### Network syslog

Structured syslog is intended for events such as:

- node and profile lifecycle;
- module activation/failure;
- radio presence and ownership state;
- health degradation/recovery;
- configuration validation failure;
- update/recovery lifecycle events;
- security-policy events.

High-frequency Zigbee, Thread, Matter, sensor or device telemetry is not intended for syslog.

A logging destination failure must never block the operational radio path.

### Home Assistant / MQTT health

Where a selected profile naturally uses MQTT or Home Assistant status interfaces, concise health information can be exposed there independently of syslog.

## Resource-efficiency policy

Resource efficiency is a design requirement, not an optimisation to add later.

The project aims to:

- keep the common core dependency-light;
- avoid resident management processes when event-driven or scheduled execution is sufficient;
- install only dependencies required by the active profile;
- prevent unselected modules from binding ports or hardware;
- apply sensible systemd/cgroup limits to long-running services;
- measure resource use as the project matures.

## Upstream-first development

The project prefers established open-source implementations over unnecessary reimplementation.

Examples include:

- Home Assistant ZHA/zigpy for ZHA deployments;
- Zigbee2MQTT for the Zigbee2MQTT profile;
- OpenThread Border Router for Thread;
- standard Matter/Home Assistant interfaces;
- MQTT where appropriate;
- RFC 5424-compatible syslog.

Where project work uncovers generally useful fixes, documentation improvements, interoperability issues, or reusable libraries, we intend to contribute those upstream where practical.

## Public interoperability goals

Public discussion and collaboration should focus on:

- radio/gateway interoperability;
- ZHA network-coordinator behaviour;
- Zigbee backup/recovery assumptions;
- Zigbee2MQTT compatibility;
- Thread Border Router behaviour;
- Matter-over-Thread interaction;
- network service discovery;
- low-resource operation;
- safe exclusive radio ownership requirements;
- failure/recovery testing methodology;
- standards-compliant logging and health interfaces.

The private resilience and deployment control plane is intentionally outside the scope of this public project discussion. See [PUBLICATION_BOUNDARY.md](PUBLICATION_BOUNDARY.md).

## Development status

- [x] Define common gateway/profile architecture.
- [x] Implement lightweight v0.1 core.
- [x] Implement `zigbee_serial`/ser2net profile.
- [x] Add maintenance and disabled profiles.
- [x] Add structured network syslog with bounded retry.
- [x] Define future Zigbee2MQTT, Thread and Matter profile manifests.
- [ ] Commission against physical Zigbee coordinator.
- [ ] Validate ZHA serial-over-IP operation on wired LAN.
- [ ] Validate Home Assistant instance handover while retaining the same gateway.
- [ ] Move radio to dedicated SBC/Raspberry Pi hardware.
- [ ] Prototype Zigbee2MQTT profile.
- [ ] Prototype Thread/OTBR profile.
- [ ] Validate Matter-over-Thread interoperability.
- [ ] Test active/passive replacement-coordinator recovery using matched hardware.
- [ ] Publish reusable upstream fixes/documentation discovered during testing.

## Feedback requested

We welcome technical feedback on assumptions that may conflict with current or planned Home Assistant, ZHA/zigpy, Zigbee2MQTT, OpenThread, or Matter architecture.

In particular, feedback is useful where an existing upstream capability already solves part of this problem or where a standard interface would make the gateway easier to integrate without introducing Home Assistant-specific coupling.
