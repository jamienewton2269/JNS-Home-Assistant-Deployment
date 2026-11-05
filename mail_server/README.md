# JNS lightweight in-house mail

Dedicated unprivileged Debian 13 container CT250 (jns-mail) on Node A.
1 shared CPU, 512 MiB memory limit, 256 MiB swap, 8 GiB local vmdata disk.
Dynamic IPv4 and IPv6; use DNS names in client settings after registration is verified.

## Accounts and aliases

| Inbox | Aliases |
|---|---|
| jamie@jnsystems.xyz | webadmin@jnsystems.xyz, mailadmin@jnsystems.xyz |
| jamie@sailing-uk.org | webadmin@sailing-uk.org, mailadmin@sailing-uk.org |

Operational postmaster and abuse aliases also reach Jamie in their own domain.
Full email addresses are the login names. Passwords are separate per domain.
Passwords are generated on the guest and saved only in root-readable
/root/jns-mail/credentials.json; password hashes are in /etc/dovecot/jns-users.
Do not commit either file or private TLS/DKIM keys.

## Services

Postfix receives SMTP on 25 and accepts authenticated STARTTLS submissions on 587.
Dovecot provides TLS IMAP on 993 and local LMTP delivery.
OpenDKIM signs outgoing authenticated submissions. It is not a content scanner.
No webmail, SQL database, Docker, antivirus or server-side spam scoring.

## Commissioning status

Public MX and SPF records remain on the existing registrar forwarding service.
The initial TLS certificate is self-signed and valid for 30 days, solely for
commissioning. Replace it with an automatically renewed public certificate
before normal client use; do not disable certificate verification in clients.

Public cutover requires:
- Confirmed stable public connectivity and inbound port 25.
- Static public address and provider-managed matching PTR for direct sending,
  or a selected authenticated outbound relay.
- DNS-only A/AAAA for mail.jnsystems.xyz pointing to externally reachable
  addresses. Publish AAAA only after externally testing the IPv6 path.
- MX for both domains pointing to mail.jnsystems.xyz.
- Correct SPF for the actual outbound path, DKIM records from the generated
  public mail202611.txt files, and DMARC monitoring before enforcement.
- Public TLS certificate and automated renewal/reload.
- Verified external inbound/outbound delivery and off-host backup.

Keep existing website records and DrayTek VPN on port 443 intact.
Ordinary SMTP is not carried by the existing Home Assistant Cloudflare tunnel.
No public DNS, router or existing DNS/DHCP configuration is changed by these scripts.

## Operations

Use Node C and its established SSH route to Node A.
Read credentials locally with:
    pct exec 250 -- cat /root/jns-mail/credentials.json
Run acceptance tests through mail_server/verify.sh.
Internal test messages are clearly marked JNS local commissioning.

## Verified 5 November 2026

Local acceptance passed:
https://github.com/jamienewton2269/JNS-Home-Assistant-Deployment/actions/runs/42039540208

- Both requested aliases on both domains delivered to their respective Jamie inbox.
- TLS SMTP and IMAP authentication passed for both accounts.
- DKIM headers were present on all four test messages.
- Unauthenticated external relaying, unknown local recipients and cross-domain
  SMTP envelope sender impersonation were rejected.
- Outbound TCP/25 reached Google and Microsoft SMTP greetings; no external
  message was sent. This does not establish inbound reachability or inbox delivery.
- Container free -m reported 48 MiB used excluding cache after acceptance,
  463 MiB available and no swap used.
- Public DNS is unchanged and the commissioning certificate remains temporary.
