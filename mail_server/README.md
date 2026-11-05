# JNS lightweight in-house mail

Dedicated unprivileged Debian 13 container CT250 (jns-mail) on Node A.
1 shared CPU, 512 MiB memory limit, 256 MiB swap, 8 GiB local vmdata disk.
DHCP-reserved IPv4 10.10.110.232; IPv6 remains automatic.
Local name: jns-mail.home.arpa. Use DNS names in client settings.

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

jnsystems.xyz MX now points to jnsystems.freeddns.org (priority 10, TTL 300).
Incoming Internet delivery to Jamie is confirmed for both domains. The user
updated sailing-uk.org in Cloudflare; all of its current MX entries point to
jnsystems.freeddns.org (priorities 5, 10, 15 and 20; equivalent redundant routes).
SPF remains on the previous forwarding-service policy pending SMTP2GO activation.
The initial TLS certificate is self-signed and valid for 30 days, solely for
commissioning. Replace it with an automatically renewed public certificate
before normal client use; do not disable certificate verification in clients.

Public cutover requires:
- Confirmed stable public connectivity and inbound port 25.
- Static public address and provider-managed matching PTR for direct sending,
  or a selected authenticated outbound relay.
- DNS-only A/AAAA for mail.jnsystems.xyz pointing to externally reachable
  addresses. Publish AAAA only after externally testing the IPv6 path.
- MX for sailing-uk.org pointing directly to jnsystems.freeddns.org; jnsystems.xyz is complete.
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

## Confirmed dynamic public addressing

User confirmed that the home public IPv4 address is dynamic and is maintained
by the existing DDNS hostname jnsystems.freeddns.org.
On 5 November 2026, public DNS returned a direct A record with a 120-second TTL,
no AAAA or CNAME, and its IPv4 matched Node C's current outbound public IPv4.
The public reverse-DNS query returned no PTR answer.

Incoming MX for both domains can target jnsystems.freeddns.org directly, subject
to confirming externally reachable TCP/25 and DDNS maintenance. Do not create
a CNAME as an MX target. A branded mail hostname used by clients can be separate.
DDNS changes do not establish inbound connectivity or direct-send reputation.
Prefer authenticated outbound relay unless the ISP can provide suitable
reverse DNS and permits direct mail from this dynamic range. Provider details
and external port forwarding remain unconfirmed; public MX remains unchanged.
DDNS check:
https://github.com/jamienewton2269/JNS-Home-Assistant-Deployment/actions/runs/42060310792

## Reserved server address — 5 November 2026

User authorized a static DHCP IPv4 address within 10.10.110.* for CT250.
- MAC: BC:24:11:52:AA:1F.
- Reservation: dhcp-host=BC:24:11:52:AA:1F,10.10.110.232,jns-mail,infinite.
- Published reservation revision 18, followed by associated local DNS revision 19.
- Both CT247 and CT248 hold the reservation and resolve jns-mail.home.arpa to 10.10.110.232.
- CT250 acquired 10.10.110.232/16 through DHCP after restart.
- Postfix, Dovecot and OpenDKIM active; TCP 25, 587 and 993 reachable on the reserved address.
- The old mail lease 10.10.200.49 was released through the standard dnsmasq DHCPRELEASE utility.
- Each DNS node's existing unrelated hosts entries were preserved, including Node B's local House Audio B overrides. No DHCP pools or IPv6 settings changed.
- Router forwarding and public MX cutover remain pending.

Verification:
https://github.com/jamienewton2269/JNS-Home-Assistant-Deployment/actions/runs/42092700507

## Internet SMTP probe passed — 5 November 2026, 19:21 GMT

After the user saved TCP/25 forwarding to 10.10.110.232, a GitHub-hosted
ubuntu-latest runner outside the home network connected to
jnsystems.freeddns.org:25 and received the mail.jnsystems.xyz EHLO response.
All six Jamie/webadmin/mailadmin recipients across both domains returned 250.
An unknown local recipient returned 550 and external relaying returned 554.
STARTTLS was advertised. This probe did not perform a TLS handshake or send
message DATA, so it establishes Internet reachability and recipient/relay
checks, not complete external message delivery or public certificate validity.
Public MX remains unchanged and outbound relay/PTR decision remains pending.

Evidence:
https://github.com/jamienewton2269/JNS-Home-Assistant-Deployment/actions/runs/42093091868

## SMTP2GO selected and prepared — 5 November 2026

User selected SMTP2GO free plan for outbound relay.
Installed libsasl2-modules and the private helper /usr/local/sbin/jns-smtp2go-setup
inside CT250. Verified connection from CT250 to mail.smtp2go.com:587 with
STARTTLS, trusted server certificate verification and TLS 1.3.
No SMTP2GO credentials were present in the known credential locations.
Postfix relayhost remains unchanged pending account signup/domain verification.

User must complete SMTP2GO account signup and email verification.
Add jnsystems.xyz and sailing-uk.org as Verified Sender domains, publish the
exact DNS verification records supplied by SMTP2GO, then create an SMTP User.
Keep dashboard login credentials separate from the SMTP User credentials.

Once domains are verified, run inside CT250:
    jns-smtp2go-setup
It prompts privately for SMTP credentials, verifies authentication and TLS
before changing Postfix, installs root-only credential maps and reloads Postfix.
Alternatively use --credentials with a root-owned mode-600 JSON file containing
username and password; never commit that file or include credentials in logs.
Authenticated outbound delivery and provider domain verification are not yet tested.

Preparation evidence:
https://github.com/jamienewton2269/JNS-Home-Assistant-Deployment/actions/runs/42100791746

## Incoming jnsystems.xyz activated — 5 November 2026, 20:49 GMT

Found the existing Cloudflare DNS-01 token in HA-General's Let's Encrypt app
configuration; used it in place without logging or copying the token to GitHub.
It has access to jnsystems.xyz, but not sailing-uk.org.
Backed up the previous JNS MX set privately under the Supervisor data directory,
then atomically replaced the five root MX records via Cloudflare's batch API.
New root MX: priority 10, target jnsystems.freeddns.org, TTL 300.
Cloudflare API and an independent public DNS lookup confirmed the new record.
An independent GitHub-hosted Internet runner sent a commissioning message to
jamie@jnsystems.xyz, and doveadm confirmed that message in Jamie's inbox.
This is end-to-end incoming delivery, not just a connection test.

Evidence:
https://github.com/jamienewton2269/JNS-Home-Assistant-Deployment/actions/runs/42106860704

Remaining action for sailing-uk.org: an authorized Cloudflare user must replace
its five eforward*.registrar-servers.com MX records with root MX priority 10,
target jnsystems.freeddns.org, TTL 300. Available token cannot edit this zone.
Incoming JNS mail is independent of the still-pending SMTP2GO outgoing account.

## Sailing incoming delivery verified — 5 November 2026, 20:55 GMT

User updated sailing-uk.org MX records manually.
Public DNS returned four MX entries at priorities 5, 10, 15 and 20, all targeting
jnsystems.freeddns.org. Multiple equivalent destinations are redundant but valid.
An independent GitHub-hosted Internet runner sent a test message to Jamie,
webadmin and mailadmin on sailing-uk.org. SMTP accepted all three recipients,
and doveadm confirmed the test message in jamie@sailing-uk.org's mailbox.
Both domains now have confirmed end-to-end Internet incoming delivery.
SMTP2GO outgoing authentication and a trusted server certificate remain pending.

Local client hostname: jns-mail.home.arpa (10.10.110.232).
IMAP: 993 SSL/TLS; SMTP submission: 587 STARTTLS, authentication required.
Login with the full Jamie mailbox address; aliases are not separate logins.

Evidence:
https://github.com/jamienewton2269/JNS-Home-Assistant-Deployment/actions/runs/42107851501
