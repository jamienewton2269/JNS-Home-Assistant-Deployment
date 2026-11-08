# Identity — full LDAP with a simple control panel

This service is being commissioned. Do not migrate existing service logins until
acceptance and failure tests pass. The deployment creates only the two named
identity guests and does not change mail, Proxmox realms, DNS/DHCP configuration,
Home Assistant users, router forwarding or existing SSH access.

## Components

| Role | Location |
|---|---|
| Directory and panel A | Node A, unprivileged CT251, auth-a.home.arpa |
| Directory and panel B | Node B, unprivileged CT252, auth-b.home.arpa |
| Guest allocation | Debian 13, 1 shared CPU, 512 MiB memory, 256 MiB swap, 4 GiB local vmdata |
| Network | DHCP IPv4 and automatic IPv6; DNS names, no new reservations |
| Directory | Debian-packaged OpenLDAP, MDB, two-way syncrepl, syncprov, ppolicy |
| Administration | Debian-packaged LDAP Account Manager |
| Password self service | LDAP Tool Box signed stable package repository |
| Web serving | nginx and on-demand PHP-FPM, maximum three workers |
| Directory suffix | dc=jnsystems,dc=xyz |

Panel URLs are https://auth-a.home.arpa/ and https://auth-b.home.arpa/.
LDAP clients use LDAPS port 636 with both servers and certificate verification.
There is no plaintext LDAP listener and neither service should be port-forwarded
to the Internet. Use the existing VPN when away from home.

The front page is a small static responsive document; it provides clear links
to password changes, account recovery and people/group administration. LDAP
operations and reset cryptography remain in maintained upstream applications.
The interface is optional: authentication does not depend on nginx or PHP.

## TLS trust

Certificates are signed by a dedicated internal CA. Install the CA certificate
on client devices before entering credentials; never bypass certificate checks.
The public certificate is served as /identity-ca.crt. Compare its SHA-256
fingerprint with this command run inside either identity guest:

    openssl x509 -in /etc/ldap/identity/ca.crt -noout -fingerprint -sha256

CA private material is root-only. The CA is available on both identity guests
for independent renewal; therefore both guests are high-trust infrastructure.
A daily timer renews leaf certificates when fewer than 30 days remain.
The CA itself lasts ten years and requires planned rotation before expiration.

## First access

From the Node A Proxmox root shell:

    pct enter 251
    /usr/local/sbin/identity-password jamie-admin

Choose a new password at the hidden prompts, then sign into /admin/ as the
named Jamie administrator. Ordinary self-service username is jamie. Its initial
password can also be set with identity-password jamie, or recovered through the
registered recovery address.

The directory manager DN and machine secrets stay in root-only bootstrap state.
Do not print bootstrap.json or copy it into GitHub, workflow logs or support chat.
The local password command takes no password arguments and is available on both
guests as an emergency recovery route.

## Accounts and access

- uid=jamie,ou=People,dc=jnsystems,dc=xyz is the ordinary identity.
- uid=jamie-admin,ou=People,dc=jnsystems,dc=xyz is the separate administrator.
- People use inetOrgPerson plus POSIX attributes and a consistent UID/GID range.
- Groups use posixGroup/memberUid: identity-admins, mail-users, proxmox-admins,
  linux-admins. Application permissions require explicit integration; creating
  or joining a group does not automatically configure the application.
- The named administrator has directory write access; ordinary users do not.
- Service accounts are outside People and are not offered for email recovery.
- The password-reset account can change ordinary user passwords, but cannot
  modify administrator/service passwords or grant group memberships.
- The replication account can read hashes for replication. Application reader
  accounts cannot retrieve hashes.
- Proxmox root/PAM accounts and deployment SSH keys remain independent.

The initial ordinary recovery address is Jamie's existing club mailbox,
jamie@blundellsandssailingclub.co.uk, rather than a mailbox that will depend on
the directory. This is a recovery destination, not permission to send club mail.
Changing recovery addresses is an administrator operation.

## Password recovery and policy

LTB Self Service Password provides password changes and email recovery.
Reset destinations come from the directory, not from arbitrary form input.
Encrypted reset tokens and their server-side cache expire after 15 minutes.
Unknown-account reset responses are obscured; reset URL logging is disabled.
Security questions and SMS are disabled. SMTP2GO is accessed with verified
STARTTLS using the existing privately stored relay account.

Directory policy: minimum 14 characters when checkable, five remembered
passwords, ten failures within five minutes trigger a five-minute lockout.
The web form requires 14–128 characters. LDAP clients should use the Password
Modify extended operation with cleartext carried inside TLS so server-side
quality checks can run. Imported/pre-hashed values cannot be length-checked by
the server with pwdCheckQuality=1; trusted administrators must enforce policy.

nginx rate-limits PHP requests; PHP session cookies are Secure, HttpOnly and
SameSite=Lax. Public access to application config directories and LAM's profile
configuration pages is blocked. Application source is installed from signed
package repositories and is not forked by this project.

## Redundancy and its boundaries

Both directory nodes have independent local disks and accept updates. Either
node can authenticate users while its peer is unavailable. The two panel URLs
are independent, so a failed panel can be replaced by opening the other URL.
There is no shared NAS dependency for live LDAP data and no floating-IP service.

OpenLDAP replication is asynchronous, not a quorum/consensus system. During a
network partition clients may see older passwords, and conflicting edits must
be avoided. Normally use panel A for administration, use B during a confirmed
A outage, and check replication before switching back. Lockout counters can
also differ briefly across nodes. This is not a CERBERUS/CHARMED deployment.

Users should request a fresh recovery link on the surviving panel if the panel
that issued an earlier link fails. Reset cache/session state is local to that
panel; directory password changes themselves replicate.

## Health and maintenance

The front page reads aggregate /health.json, refreshed every 30 seconds by a
short-lived local process. It checks verified TLS binds to both directories and
compares contextCSN vectors. No account details or credentials are published.

Daily maintenance creates GnuPG AES-256 encrypted LDAP/config exports under
/root/identity/backups, retaining seven. The encryption key stays in protected
bootstrap state and must be preserved separately for disaster recovery.
A host cron job copies encrypted exports to the existing mounted WD-BACKUP NFS storage. It refuses to write if that mount is unavailable. An off-host copy and a restore drill must be verified before production cutover.
Replication is not a substitute for backups.

## Commissioning evidence (8 November 2026)

- Directory and policy acceptance: GitHub Actions run 42368949263 (passed).
- Failover, backup and actual email-token recovery: run 42369193073 (passed).
- Linux pilot: unprivileged Debian 13 CT253; LDAP user/group NSS resolution,
  PAM positive/negative login, home-directory creation and isolated one-server
  client failover passed. Local root access is retained.
- Fresh Debian 13 recovery drills in disposable CT254: encrypted WD NAS archive
  decrypted, LDAP MDB restored, local LDAPS started with replication disabled,
  internal-CA TLS hostname verification and directory-manager bind passed.
  A further drill rendered the upstream LDAP Account Manager login and Self
  Service Password pages over verified HTTPS on loopback-only ports; it did not
  send mail or reset real user passwords.
- Archive completeness deficiency found and corrected: recovery requires nginx
  identity-rate.conf, web assets, PHP-FPM pool, LDAP defaults, upstream repository
  source/key and related systemd service files. Deployment and expanded backup
  restore validation passed: GitHub Actions run 42476513294.
- CT254 and its staged recovery material were destroyed after testing.

**Remaining before production migration:** arrange and verify independent,
offline or separately controlled encrypted custody of the backup decryption
key and recovery instructions. Do not put bootstrap.json, the key, CA private
material or recovery tokens into GitHub, chat, ordinary shared folders or
workflow logs. Recovery using the original protected key was proven; recovery
of that key after *simultaneous* loss of all existing hosts is not yet proven.

No existing mail, Proxmox, Home Assistant, router, DNS/DHCP or SSH
authentication has been migrated by this project.

## Migration sequence

1. Commission both guests and prove web, policy, ACL and replication checks.
2. Stop each new directory in turn; authenticate and change a disposable user's
   password on the survivor; restart and prove convergence.
3. Exercise email recovery, expiry and token replay using a disposable user.
4. Preserve recovery material and prove encrypted-backup restoration.
5. Pilot one noncritical Linux guest; then migrate Dovecot, Proxmox and HA
   separately, retaining local emergency access and rollback paths.

No service is migrated merely by deploying these containers.
