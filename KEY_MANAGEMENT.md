# JNS Production Key Management

Recommended separation:

- `jns-config-production`: `config` scope only.
- `jns-platform-production`: `platform` scope only.

Keeping platform authority separate limits the impact of a config signing-key compromise.

Home Assistant stores only public keys in `/config/jns/trust/publishers.json`. Verify each public-key fingerprint independently before trusting it.
