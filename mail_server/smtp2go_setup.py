#!/usr/bin/env python3
"""Authenticate to SMTP2GO, then configure the existing Postfix relay."""
import argparse,getpass,json,os,pathlib,shutil,smtplib,ssl,subprocess,datetime,sys
p=argparse.ArgumentParser()
p.add_argument("--credentials",help="Root-owned mode-600 JSON file with username and password")
args=p.parse_args()
if os.geteuid()!=0:sys.exit("Run as root inside CT250.")
if args.credentials:
    source=pathlib.Path(args.credentials)
    stat=source.stat()
    if stat.st_uid!=0 or stat.st_mode&0o077:sys.exit("Credential input must be owned by root with mode 600.")
    data=json.loads(source.read_text())
    username=data["username"];password=data["password"]
else:
    username=input("SMTP2GO SMTP username (not account login): ").strip()
    password=getpass.getpass("SMTP2GO SMTP password: ")
if not isinstance(username,str) or not isinstance(password,str) or not username or not password:
    sys.exit("Both SMTP username and password are required.")
if any(c in username+password for c in "\r\n\0") or ":" in username:
    sys.exit("Unsupported characters in SMTP credentials.")
host="mail-eu.smtp2go.com"
try:
    with smtplib.SMTP(host,587,timeout=20) as smtp:
        smtp.ehlo()
        smtp.starttls(context=ssl.create_default_context())
        smtp.ehlo()
        smtp.login(username,password)
except Exception as exc:
    sys.exit("SMTP2GO authentication/TLS check failed ("+type(exc).__name__+"); Postfix was not changed.")
root=pathlib.Path("/root/jns-mail")
root.mkdir(mode=0o700,exist_ok=True)
backup=root/("main.cf.before-smtp2go-"+datetime.datetime.now().strftime("%Y%m%dT%H%M%S"))
shutil.copy2("/etc/postfix/main.cf",backup)
backup.chmod(0o600)
path=pathlib.Path("/etc/postfix/smtp2go_passwd")
# Write the credential map privately; no credentials enter command arguments or logs.
fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
with os.fdopen(fd,"w") as out:out.write("[mail-eu.smtp2go.com]:587 "+username+":"+password+"\n")
path.chmod(0o600)
try:
    subprocess.run(["postmap","hash:"+str(path)],check=True)
    pathlib.Path(str(path)+".db").chmod(0o600)
    settings=[
      "relayhost = [mail-eu.smtp2go.com]:587",
      "smtp_sasl_auth_enable = yes",
      "smtp_sasl_password_maps = hash:/etc/postfix/smtp2go_passwd",
      "smtp_sasl_security_options = noanonymous",
      "smtp_sasl_tls_security_options = noanonymous",
      "smtp_tls_security_level = verify",
      "smtp_tls_verify_cert_match = nexthop",
      "smtp_tls_CAfile = /etc/ssl/certs/ca-certificates.crt",
      "smtp_tls_loglevel = 1",
    ]
    subprocess.run(["postconf","-e"]+settings,check=True)
    subprocess.run(["postfix","check"],check=True)
    subprocess.run(["systemctl","reload","postfix"],check=True)
except BaseException:
    shutil.copy2(backup,"/etc/postfix/main.cf")
    subprocess.run(["systemctl","reload","postfix"],check=False)
    raise
print("SMTP2GO authentication and verified TLS passed; Postfix relay configured.")
print("Both sending domains must be verified in SMTP2GO before delivery testing.")
