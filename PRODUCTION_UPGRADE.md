# Upgrade to JNS v5.0.0

For v4.x -> v5.0.0, use HACS. Do not weaken v4.2.4's protection that blocks unsigned executable `custom_components/` deployment.

1. Push v5.0.0 to GitHub.
2. Confirm Hassfest, HACS and production CI are green.
3. Update/redownload JNS through HACS.
4. Restart Home Assistant.
5. Confirm `jns_deployment.status` reports `5.0.0`.
6. Generate publisher keys offline.
7. Copy only `publishers.json` to `/config/jns/trust/`.
8. Verify `list_trusted_publishers` and run production acceptance tests.

Future v5.x updates should use signed platform updates with a publisher granted only `platform` scope.
