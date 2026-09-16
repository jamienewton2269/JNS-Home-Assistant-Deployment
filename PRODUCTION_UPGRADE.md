# Production upgrade to JNS v5.4.1

1. Update **JNS Home Assistant Deployment Platform** through HACS.
2. Restart Home Assistant.
3. Open **Settings → Devices & services → JNS Home Assistant Deployment Platform → Configure**.
4. Enter a unique deployment-only SFTP password of at least 24 characters and save.
5. Confirm the JNS Secure SFTP App is installed/running and TCP 2222 is reachable only from the intended management LAN/VPN.
6. Put the same host/user/password into Windows Management Console v5.4 and run its connection test.
7. Continue package management with Deploy / Update / Repair / Uninstall.

Do not enable unsigned package deployment and do not expose the SFTP port directly to the public Internet.
