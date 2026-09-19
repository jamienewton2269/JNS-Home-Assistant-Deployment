# JNS Deployment Platform v5.5.4

## Legacy Secure Transfer coexistence hotfix

The live VM900 migration exposed a second JNS transport app already bound to
TCP 2222: the existing **JNS Secure Transfer Gateway** from
`jamienewton2269/HA`.  That gateway is the legacy transport used by the old
management PC and must remain available until the new PC has completed
commissioning.

v5.5.4 therefore does not stop, reconfigure or displace the legacy gateway.

### Changes

- Keeps TCP 2222 as the preferred JNS Secure SFTP port on clean installations.
- Detects host-port assignments of other installed Home Assistant apps through
  Supervisor.
- If 2222 is already reserved by another app, selects the first free port in
  the migration range 2223-2232.
- Applies the selected port to the new JNS Secure SFTP app before start.
- Returns the selected port in the management-PC enrollment response.
- The Windows Management Console already consumes the returned `sftp_port`,
  so no Windows-side protocol change is required.
- Stores the selected port in the management-PC registry so retries and status
  reporting stay consistent.
- Preserves the old gateway and old management-PC credentials throughout
  commissioning.

For the current VM900 topology, the expected result is that the legacy
`c4757267_jns_secure_transfer` gateway remains on **2222** and the new
`155ff8a7_jns_secure_sftp` app starts on **2223**.
