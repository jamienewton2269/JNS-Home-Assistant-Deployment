#!/bin/bash
set -Eeuo pipefail
test "$(hostname -s)" = nodec
ssh -o BatchMode=yes -o StrictHostKeyChecking=yes root@nodea.home.arpa 'pct exec 250 -- bash -se' <<'GUEST'
set -Eeuo pipefail
test "$(hostname -s)" = jns-mail
umask 077
install -d -m 700 /root/jns-mail
getent group vmail >/dev/null || groupadd --system --gid 5000 vmail
id vmail >/dev/null 2>&1 || useradd --system --uid 5000 --gid vmail --home-dir /var/vmail --shell /usr/sbin/nologin vmail
install -d -o vmail -g vmail -m 750 /var/vmail
install -d -m 700 /etc/jns-mail/tls
if ! test -s /etc/jns-mail/tls/server.key; then
  openssl req -x509 -newkey rsa:3072 -nodes -days 30 -subj '/CN=mail.jnsystems.xyz' -addext 'subjectAltName=DNS:mail.jnsystems.xyz,DNS:mail.sailing-uk.org,DNS:jns-mail.home.arpa' -keyout /etc/jns-mail/tls/server.key -out /etc/jns-mail/tls/server.crt 2>/dev/null
fi
python3 - <<'PY'
import pathlib,secrets,json,subprocess,os
domains=["jnsystems.xyz","sailing-uk.org"]
p=pathlib.Path("/root/jns-mail/credentials.json")
if p.exists(): creds=json.loads(p.read_text())
else:
    creds={"jamie@"+d:secrets.token_urlsafe(24) for d in domains}
    p.write_text(json.dumps(creds,indent=2)+"\n");p.chmod(0o600)
lines=[]
for d in domains:
    u="jamie@"+d
    proc=subprocess.run(["doveadm","pw","-s","SHA512-CRYPT"],input=creds[u]+"\n"+creds[u]+"\n",text=True,capture_output=True,check=True)
    hashed=proc.stdout.strip()
    assert hashed.startswith("{SHA512-CRYPT}")
    home="/var/vmail/"+d+"/jamie"
    lines.append(u+":"+hashed+":5000:5000::"+home+"::")
    for folder in ("cur","new","tmp"):
        path=pathlib.Path(home+"/Maildir/"+folder)
        path.mkdir(parents=True,exist_ok=True)
    for root,dirs,files in os.walk("/var/vmail/"+d):
        os.chown(root,5000,5000)
        for f in files: os.chown(os.path.join(root,f),5000,5000)
path=pathlib.Path("/etc/dovecot/jns-users")
path.write_text("\n".join(lines)+"\n")
path.chmod(0o640)
import grp
os.chown(path,0,grp.getgrnam("dovecot").gr_gid)
alias=[];mailboxes=[];senders=[]
for d in domains:
    user="jamie@"+d
    mailboxes.append(user+" "+d+"/jamie/Maildir/")
    for name in ["jamie","webadmin","mailadmin","postmaster","abuse"]:
        address=name+"@"+d
        senders.append(address+" "+user)
        if name!="jamie": alias.append(address+" "+user)
for name,rows in [("jns-aliases",alias),("jns-mailboxes",mailboxes),("jns-senders",senders)]:
    path=pathlib.Path("/etc/postfix/"+name);path.write_text("\n".join(rows)+"\n");path.chmod(0o644)
PY
version="$(dovecot --version)"
case "$version" in
  2.4.*)
cat >/etc/dovecot/dovecot.conf <<'DOVE'
dovecot_config_version = 2.4.0
dovecot_storage_version = 2.4.0
protocols = imap lmtp
listen = *, ::
auth_mechanisms = plain login
auth_allow_cleartext = no
auth_username_format = %{user | lower}
ssl = required
ssl_min_protocol = TLSv1.2
ssl_server_cert_file = /etc/jns-mail/tls/server.crt
ssl_server_key_file = /etc/jns-mail/tls/server.key
mail_driver = maildir
mail_path = ~/Maildir
first_valid_uid = 5000
passdb passwd-file {
  passwd_file_path = /etc/dovecot/jns-users
}
userdb passwd-file {
  passwd_file_path = /etc/dovecot/jns-users
}
namespace inbox {
  inbox = yes
  separator = /
  mailbox Sent {
    auto = subscribe
    special_use = \Sent
  }
  mailbox Drafts {
    auto = subscribe
    special_use = \Drafts
  }
  mailbox Trash {
    auto = subscribe
    special_use = \Trash
  }
  mailbox Junk {
    auto = subscribe
    special_use = \Junk
  }
}
service imap-login {
  process_limit = 8
  inet_listener imap {
    port = 0
  }
  inet_listener imaps {
    port = 993
    ssl = yes
  }
}
service imap {
  process_limit = 16
}
service lmtp {
  process_limit = 4
  unix_listener /var/spool/postfix/private/dovecot-lmtp {
    mode = 0600
    user = postfix
    group = postfix
  }
}
service auth {
  unix_listener /var/spool/postfix/private/auth {
    mode = 0660
    user = postfix
    group = postfix
  }
}
protocol lmtp {
  postmaster_address = postmaster@jnsystems.xyz
}
log_path = /dev/stderr
info_log_path = /dev/stderr
DOVE
;;
  *) echo "Unsupported Dovecot version: $version; leaving stopped"; exit 1;;
esac
postconf -e 'myhostname = mail.jnsystems.xyz' 'mydomain = jnsystems.xyz' 'myorigin = $mydomain' \
 'mydestination = localhost, localhost.localdomain, $myhostname' \
 'inet_interfaces = all' 'inet_protocols = all' 'mynetworks = 127.0.0.0/8 [::1]/128' \
 'virtual_mailbox_domains = jnsystems.xyz sailing-uk.org' \
 'virtual_mailbox_maps = hash:/etc/postfix/jns-mailboxes' \
 'virtual_alias_maps = hash:/etc/postfix/jns-aliases' \
 'virtual_transport = lmtp:unix:private/dovecot-lmtp' \
 'smtpd_relay_restrictions = reject_unauth_destination' \
 'smtpd_recipient_restrictions = reject_non_fqdn_recipient, reject_unknown_recipient_domain, reject_unlisted_recipient' \
 'smtpd_reject_unlisted_recipient = yes' 'smtpd_helo_required = yes' 'disable_vrfy_command = yes' \
 'smtpd_tls_security_level = may' 'smtpd_tls_cert_file = /etc/jns-mail/tls/server.crt' \
 'smtpd_tls_key_file = /etc/jns-mail/tls/server.key' 'smtpd_tls_protocols = >=TLSv1.2' \
 'smtpd_tls_mandatory_protocols = >=TLSv1.2' 'smtp_tls_security_level = may' \
 'smtpd_sasl_auth_enable = no' 'smtpd_sasl_type = dovecot' 'smtpd_sasl_path = private/auth' \
 'smtpd_sasl_security_options = noanonymous' 'smtpd_tls_auth_only = yes' \
 'smtpd_sender_login_maps = hash:/etc/postfix/jns-senders' \
 'default_process_limit = 20' 'smtpd_client_connection_count_limit = 5' \
 'smtpd_client_connection_rate_limit = 30' 'smtpd_client_auth_rate_limit = 10' \
 'message_size_limit = 26214400' 'mailbox_size_limit = 0' \
 'smtpd_milters =' 'non_smtpd_milters = inet:127.0.0.1:8891' \
 'milter_default_action = tempfail' 'milter_protocol = 6'
for name in jns-mailboxes jns-aliases jns-senders; do postmap "/etc/postfix/$name"; done
postconf -M 'submission/inet=submission inet n - n - 8 smtpd'
postconf -P 'submission/inet/smtpd_tls_security_level=encrypt' \
 'submission/inet/smtpd_sasl_auth_enable=yes' \
 'submission/inet/smtpd_relay_restrictions=permit_sasl_authenticated,reject' \
 'submission/inet/smtpd_recipient_restrictions=permit_sasl_authenticated,reject' \
 'submission/inet/smtpd_sender_restrictions=reject_authenticated_sender_login_mismatch' \
 'submission/inet/smtpd_milters=inet:127.0.0.1:8891'
install -d -o opendkim -g opendkim -m 750 /etc/opendkim/keys
: >/etc/opendkim/KeyTable
: >/etc/opendkim/SigningTable
for domain in jnsystems.xyz sailing-uk.org; do
  install -d -o opendkim -g opendkim -m 750 "/etc/opendkim/keys/$domain"
  if ! test -s "/etc/opendkim/keys/$domain/mail202611.private"; then
    opendkim-genkey -b 2048 -d "$domain" -s mail202611 -D "/etc/opendkim/keys/$domain"
  fi
  chown opendkim:opendkim /etc/opendkim/keys/"$domain"/*
  chmod 600 "/etc/opendkim/keys/$domain/mail202611.private"
  echo "mail202611._domainkey.$domain $domain:mail202611:/etc/opendkim/keys/$domain/mail202611.private" >>/etc/opendkim/KeyTable
  echo "*@$domain mail202611._domainkey.$domain" >>/etc/opendkim/SigningTable
done
cat >/etc/opendkim.conf <<'DKIM'
Syslog yes
UMask 007
UserID opendkim
Mode s
Canonicalization relaxed/simple
Socket inet:8891@127.0.0.1
KeyTable /etc/opendkim/KeyTable
SigningTable refile:/etc/opendkim/SigningTable
InternalHosts 127.0.0.1,::1
OversignHeaders From
DKIM
cat >/etc/aliases <<'ALIASES'
postmaster: root
root: jamie@jnsystems.xyz
ALIASES
newaliases
doveconf -n >/dev/null
postfix check
opendkim -n -x /etc/opendkim.conf
systemctl enable postfix dovecot opendkim
systemctl restart opendkim dovecot postfix
systemctl is-active dovecot opendkim postfix
echo '=== MAILBOX LOOKUP ==='
doveadm user jamie@jnsystems.xyz
doveadm user jamie@sailing-uk.org
echo '=== DKIM PUBLIC RECORDS ==='
cat /etc/opendkim/keys/*/mail202611.txt
echo '=== TLS FINGERPRINT ==='
openssl x509 -in /etc/jns-mail/tls/server.crt -noout -fingerprint -sha256 -dates
echo '=== LISTENERS ==='
ss -lntp
echo '=== MEMORY ==='
free -m
GUEST
