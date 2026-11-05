#!/bin/bash
set -Eeuo pipefail
ssh -o BatchMode=yes -o StrictHostKeyChecking=yes root@nodea.home.arpa 'pct exec 250 -- bash -se' <<'GUEST'
set -Eeuo pipefail
chown root:opendkim /etc/opendkim/KeyTable /etc/opendkim/SigningTable
chmod 640 /etc/opendkim/KeyTable /etc/opendkim/SigningTable
systemctl restart opendkim
python3 - <<'PY'
import smtplib,ssl,imaplib,json,pathlib,time,email
from email.message import EmailMessage
creds=json.loads(pathlib.Path("/root/jns-mail/credentials.json").read_text())
ctx=ssl.create_default_context(cafile="/etc/jns-mail/tls/server.crt")
# Connect through the actual server name, resolved to localhost for this in-guest check.
import socket
real=socket.getaddrinfo
def lookup(host,*args,**kwargs):
    return real("127.0.0.1" if host=="mail.jnsystems.xyz" else host,*args,**kwargs)
socket.getaddrinfo=lookup
def require(value,label):
    if not value: raise RuntimeError(label)
    print("PASS",label)
with smtplib.SMTP("mail.jnsystems.xyz",25,timeout=10) as s:
    s.ehlo("jns-mail.home.arpa")
    require(not s.has_extn("auth"),"port 25 does not advertise authentication")
    s.mail("probe@jnsystems.xyz")
    code,msg=s.rcpt("nobody@example.net")
    require(code==554 or code==550,"unauthenticated external relay rejected")
    s.rset();s.mail("probe@jnsystems.xyz")
    code,msg=s.rcpt("unknown-local-user@jnsystems.xyz")
    require(code==550,"unknown local mailbox rejected")
    s.rset()
with smtplib.SMTP("mail.jnsystems.xyz",587,timeout=10) as s:
    s.ehlo()
    require(not s.has_extn("auth"),"submission login hidden before TLS")
    s.starttls(context=ctx);s.ehlo()
    s.mail("jamie@jnsystems.xyz")
    code,msg=s.rcpt("jamie@sailing-uk.org")
    require(code>=500,"submission requires authentication")
stamp=str(time.time_ns())
for domain in ["jnsystems.xyz","sailing-uk.org"]:
    user="jamie@"+domain
    with smtplib.SMTP("mail.jnsystems.xyz",587,timeout=10) as s:
        s.ehlo();s.starttls(context=ctx);s.ehlo()
        s.login(user,creds[user])
        require(True,"TLS SMTP login "+user)
        for alias in ["webadmin","mailadmin"]:
            msg=EmailMessage()
            msg["From"]=user
            msg["To"]=alias+"@"+domain
            msg["Subject"]="JNS local commissioning "+stamp+" "+alias
            msg["Message-ID"]="<"+stamp+"."+alias+"@"+domain+">"
            msg.set_content("Internal commissioning test of mailbox alias delivery.")
            s.send_message(msg)
            print("SUBMITTED",alias+"@"+domain)
        other="sailing-uk.org" if domain=="jnsystems.xyz" else "jnsystems.xyz"
        code,_=s.mail("jamie@"+other)
        if code==250: code,_=s.rcpt(user)
        require(code>=500,"cross-domain sender impersonation rejected for "+user)
        s.rset()
    for attempt in range(15):
        with imaplib.IMAP4_SSL("mail.jnsystems.xyz",993,ssl_context=ctx,timeout=10) as imap:
            status,_=imap.login(user,creds[user])
            require(status=="OK","TLS IMAP login "+user) if attempt==0 else None
            imap.select("INBOX")
            status,data=imap.search(None,"SUBJECT",'"JNS local commissioning '+stamp+'"')
            ids=data[0].split()
            if len(ids)==2:
                for mid in ids:
                    status,data=imap.fetch(mid,"(BODY.PEEK[])")
                    raw=next(x[1] for x in data if isinstance(x,tuple))
                    parsed=email.message_from_bytes(raw)
                    require(bool(parsed.get("DKIM-Signature")),"DKIM signature present on "+parsed["To"])
                require(True,"both requested aliases delivered to "+user)
                break
        time.sleep(1)
    else: raise RuntimeError("alias delivery timeout "+user)
print("ALL LOCAL MAIL TESTS PASSED")
PY
echo '=== RESOURCE USAGE ==='
free -m
ps -eo comm,rss --sort=-rss | head -15
echo '=== MAIL QUEUE ==='
postqueue -p
echo '=== ADDRESS ==='
hostname -f
getent ahostsv4 jns-mail.home.arpa || true
echo '=== OUTBOUND SMTP CONNECTIVITY (NO MESSAGE SENT) ==='
python3 - <<'PY'
import socket
for host in ["gmail-smtp-in.l.google.com","outlook-com.olc.protection.outlook.com"]:
    try:
        with socket.create_connection((host,25),timeout=8) as s:
            print(host,s.recv(256).decode(errors="replace").strip())
    except Exception as e: print(host,type(e).__name__,str(e))
PY
GUEST
