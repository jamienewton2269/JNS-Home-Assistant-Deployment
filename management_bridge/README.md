# JNS Management Bridge

A small, dependency-light administrative bridge for infrastructure you own.

It was created as an open alternative to proprietary remote-command relays. The bridge keeps SSH as the underlying transport and adds only a minimal browser/API layer.

## Security model

- Binds to `127.0.0.1` by default.
- Requires a randomly generated bearer token.
- Only targets explicitly present in `config.json` are reachable.
- SSH runs in `BatchMode` and therefore does not fall back to password prompts.
- Command execution has a fixed timeout and output limit.
- The audit log records target, result, duration and a SHA-256 fingerprint of the command, but not command text.
- No file-upload endpoint is provided.
- Do **not** bind the service directly to the public Internet. Put an authenticated TLS reverse proxy/tunnel in front of it.

This project intentionally does not contain deployment-specific IP addresses, hostnames, credentials, SSH private keys or access tokens.

## Install

On a Debian/Ubuntu/Proxmox management host:

```bash
curl -fsSL https://raw.githubusercontent.com/jamienewton2269/JNS-Home-Assistant-Deployment/main/management_bridge/install.sh | sudo bash
```

Then edit:

```text
/etc/jns-management-bridge/config.json
```

The SSH `destination` can be an ordinary hostname or an alias already defined in that machine's `~/.ssh/config`.

Restart after changing configuration:

```bash
sudo systemctl restart jns-management-bridge
```

Check it locally:

```bash
curl http://127.0.0.1:8765/health
sudo systemctl status jns-management-bridge
```

The generated access token is stored root-only at:

```text
/etc/jns-management-bridge/token
```

## Example target configuration

```json
{
  "listen_host": "127.0.0.1",
  "listen_port": 8765,
  "command_timeout": 30,
  "max_output_bytes": 200000,
  "max_command_chars": 8192,
  "targets": {
    "local": {"mode": "local"},
    "hypervisor": {"mode": "ssh", "destination": "my-hypervisor"}
  }
}
```

## Remote access

Keep the bridge listening on loopback and expose it through infrastructure you control, for example an authenticated HTTPS reverse proxy or a reverse SSH tunnel terminating on your own server.

A temporary tunnel can also be used for short diagnostic sessions, but treat the generated bearer token as a secret and stop the tunnel when finished.

## API

### Health

`GET /health`

### Targets

`GET /api/targets`

Header:

```text
Authorization: Bearer <token>
```

### Run a command

`POST /api/run`

```json
{"target":"hypervisor","command":"hostname && uptime"}
```

Header:

```text
Authorization: Bearer <token>
Content-Type: application/json
```

## Licence

This component is distributed under the repository's root licence.
