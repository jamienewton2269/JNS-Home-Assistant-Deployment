# JNS Secure SFTP

This companion app is provisioned by the HACS-installed **JNS Home Assistant Deployment Platform**. It provides standards-based SFTP transport only.

- Default external port: `2222`
- Default user: `jnstransfer`
- Client starts in `/incoming`
- No interactive shell, port forwarding, agent forwarding, X11 forwarding, root login or tunnels
- Package trust is enforced separately by the JNS signed-package deployment engine

The app maps Home Assistant configuration read/write because `/config/jns/sftp/incoming` is the deployment inbox. The SFTP account itself is chrooted to that inbox and cannot browse the rest of Home Assistant configuration. Keep port 2222 LAN/VPN-only.
