# JNS IoT Gateway v0.1.0

Efficiency-first, profile-driven radio/IoT gateway node for the JNS Home Assistant infrastructure.

## Implemented now

- Small standard-library Python core; no third-party Python packages.
- Core runs as oneshot commands/timer jobs rather than a permanent daemon.
- `zigbee_serial` profile using a dedicated `ser2net` process.
- Stable `/dev/serial/by-id/...` radio identity requirement.
- One TCP client only, with no client pre-emption.
- `maintenance` and `disabled` core-only profiles.
- RFC 5424 network syslog over UDP/TCP/TLS with a bounded local retry spool.
- State-change-based health events to avoid high-frequency logging.
- systemd hardening/resource limits for the ser2net module.

## Reserved future profiles

`zigbee2mqtt`, `thread_otbr`, and `matter_thread_edge` are present as manifests only. v0.1 rejects them rather than installing placeholder services. This enforces the rule that unused protocol code is not installed or loaded.

## Install

On a Debian gateway/LXC, first copy and edit `config/gateway.example.json`, setting the real coordinator `/dev/serial/by-id/...` path and optional network syslog server. Then run:

```bash
sudo ./install/install.sh --profile zigbee_serial --config ./gateway.json
```

Check:

```bash
jns-gateway validate
jns-gateway status
systemctl status jns-iot-zigbee-serial.service
```

Home Assistant ZHA can then use the configured gateway address, for example `socket://<gateway-ip>:20108`. Cluster fencing must ensure only the active HA node opens the coordinator socket.

## Current JNS Deployment Platform relationship

This code belongs to the same maintained JNS repository, but it is an infrastructure-node payload, not a Home Assistant `config_package` or `integration_package`. The existing v5 Home Assistant executor intentionally confines packages to HA-managed paths and does not execute arbitrary host installers. The gateway installer therefore remains separate until a security-scoped infrastructure deployment path is added to the Management Console/Proxmox side.
