# JNS IoT Gateway — Public / Private Publication Boundary

This document defines what may be published from the JNS IoT Gateway project and what must remain outside public repositories, issues, forum posts, presentations, logs and examples.

The purpose is to support useful open collaboration without exposing security-sensitive resilience, authorization, distribution, rollback or infrastructure-control internals.

## Guiding rule

Publish **interfaces, requirements, interoperability behaviour and non-sensitive gateway implementation**.

Do not publish **security-sensitive control-plane implementation, credentials, cryptographic material, private deployment mechanisms or details that materially reduce the security of a deployed JNS environment**.

When uncertain, describe the requirement or externally observable behaviour rather than the private mechanism used to achieve it.

## PUBLIC / OPEN

The following are suitable for public development and discussion.

### Gateway architecture

- profile-driven modular gateway design;
- lightweight core architecture;
- Raspberry Pi/SBC and Debian/LXC deployment;
- module dependency and conflict declarations;
- resource-efficiency goals and measurements;
- systemd hardening that is generic to the gateway;
- persistent radio device identification;
- stable service endpoint concepts.

### Protocol integrations

- ser2net/ZHA interoperability;
- Zigbee2MQTT profile integration;
- OpenThread Border Router integration;
- Matter/Thread interoperability;
- MQTT interfaces;
- IPv6/mDNS requirements;
- standards-compatible protocol behaviour.

### Safety properties expressed as requirements

It is acceptable to state requirements such as:

- only one Zigbee coordinator owner may be active;
- a stale/old gateway must be prevented from simultaneously controlling a restored network;
- profile changes must validate resource conflicts before activation;
- failover must not silently create two active radio owners.

Public material should discuss these as **required properties**, not disclose the private implementation of the orchestration that enforces them.

### Observability

- RFC 5424 event format;
- non-sensitive syslog event names;
- health/state reporting;
- resource telemetry;
- test results with secrets and identifiable infrastructure removed.

### Recovery interoperability

- use of supported coordinator backups;
- generic backup validation concepts;
- recovery compatibility testing;
- externally observable migration results;
- documentation of limitations found in upstream projects.

### Upstream contributions

Generally useful bug fixes, interoperability improvements, documentation, test cases and isolated reusable libraries may be contributed upstream after review confirms that they contain no private control-plane code or security-sensitive deployment material.

## PRIVATE / DO NOT PUBLISH

The following remain private unless deliberately reclassified after security review.

### Resilience control plane

Do not publish implementation details of the private cluster/orchestration layer, including:

- quorum implementation;
- leader/promotion algorithms;
- node-election internals;
- detailed fencing implementation;
- private failure scoring or promotion decision logic;
- control-plane authentication internals;
- private state-transition protocols.

Public wording should normally be limited to statements such as:

> An external orchestration layer guarantees exclusive ownership before a standby gateway is promoted.

### Cryptographic and authorization implementation

Do not publish:

- private keys;
- signing keys;
- recovery keys;
- enrollment secrets;
- tokens;
- trust-store contents;
- private certificate material;
- key derivation or storage implementation specific to deployed JNS systems;
- authorization-capability internals that would materially weaken the security model.

Public documentation may say that packages/configuration are authenticated or integrity checked without disclosing deployable secrets or sensitive internal policy implementation.

### Secure distribution and enrollment

Do not publish private implementation details of:

- management-node enrollment;
- privileged deployment transport;
- secure bootstrap;
- private management APIs;
- authorization handshakes;
- remote execution controls;
- internal package-distribution channels.

### Transaction / rollback control internals

Do not publish security-sensitive details of:

- private rollback checkpoints;
- privileged recovery mechanisms;
- protected state restoration;
- transactional promotion internals;
- methods that could be abused to bypass validation or restore unauthorised state.

It is safe to describe the public property as:

> Configuration/profile changes are validated and recoverable.

### Infrastructure secrets and topology

Never publish real:

- passwords or tokens;
- private IP addressing where disclosure is unnecessary;
- VPN/WireGuard keys;
- API credentials;
- SSH host/private keys;
- serial numbers when they identify deployed equipment unnecessarily;
- management hostnames;
- firewall exception details that expose privileged paths;
- internal account names where security-sensitive.

Use obvious documentation examples such as `zigbee-gateway.example.lan` and RFC 5737 documentation networks where addresses are needed.

### Security-sensitive logs

Before sharing logs, remove:

- credentials;
- session IDs;
- cryptographic keys;
- Zigbee network keys;
- Matter fabric credentials;
- bearer tokens;
- device onboarding secrets;
- private infrastructure identifiers.

## PUBLIC LANGUAGE GUIDE

Prefer:

- “external orchestration layer”
- “exclusive ownership is enforced before promotion”
- “authenticated/integrity-checked deployment”
- “recoverable profile transition”
- “validated backup generation”
- “private control plane”

Avoid public descriptions that explain exactly how the private control plane reaches those guarantees.

## CONTRIBUTION / PUBLICATION CHECKLIST

Before publishing a commit, issue, forum post, log or diagram:

1. Does it contain a credential, key, token, secret, QR/onboarding code or certificate material?
2. Does it disclose a private management endpoint or privileged network path?
3. Does it reveal the implementation of private quorum, fencing, promotion, authorization, secure distribution or rollback logic?
4. Could the information materially help bypass a JNS deployment or recovery safeguard?
5. Does it contain identifiable production infrastructure data that is unnecessary for the discussion?
6. Could the same technical point be expressed as an interface requirement or externally observable behaviour instead?

If any of questions 1–5 are yes, do not publish until reviewed and sanitised.

## Repository rule

Public gateway modules should depend only on documented public interfaces to the private control plane.

They must not import, vendor, copy or require private resilience/deployment implementation code.

This separation is intentional: the gateway should remain useful with Home Assistant and open standards even when the private JNS orchestration layer is absent.

## External discussions

When asking Home Assistant, zigpy, Zigbee2MQTT, OpenThread or Matter communities for advice, include only the minimum information needed to discuss interoperability.

The preferred pattern is:

1. state the externally observable problem;
2. describe the standard interface being used;
3. state the safety/reliability property required;
4. provide a minimal reproducible example where possible;
5. omit unrelated private orchestration and deployment internals.
