# JNS Deployment Platform v5.1.0

- Adds signed `integration_package` support for JNS-owned Home Assistant custom integrations.
- Integration packages may write only to `custom_components/<declared jns_ domain>/` plus normal JNS config roots.
- Requires valid embedded manifest/domain and compiles Python payload before commit.
- Adds transactional package uninstall with drift protection.
- Updates remove stale managed files no longer present in the new package.
- Installed-software inventory reports missing/drifted managed files for repair.
- Third-party/HACS integrations remain outside this path; managed integration domains must begin `jns_`.
