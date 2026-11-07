#!/usr/bin/env python3
"""Provision only new identity guests; existing authentication is untouched."""
import subprocess, shlex, pathlib, base64

NODES = [('nodea.home.arpa',251,'auth-a'),('nodeb.home.arpa',252,'auth-b')]
def ssh(host,args,**kw):
    return subprocess.run(['ssh','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','root@'+host,shlex.join(args)],check=True,**kw)
def guest(host,ct,source):
    # Transfer source through an argument, never depend on nested stdin forwarding.
    code='import base64;exec(compile(base64.b64decode('+repr(base64.b64encode(source.encode()).decode())+'),"identity-stage","exec"))'
    return ssh(host,['pct','exec',str(ct),'--','python3','-c',code])
for host,ct,name in NODES:
    source=f'''set -eu
test ! -e /etc/pve/qemu-server/{ct}.conf
if test -e /etc/pve/lxc/{ct}.conf; then
  pct config {ct} | grep -qx 'hostname: {name}'
else
  pct create {ct} local:vztmpl/debian-13-standard_13.6-1_amd64.tar.zst --hostname {name} --unprivileged 1 --cores 1 --memory 512 --swap 256 --rootfs vmdata:4 --net0 name=eth0,bridge=vmbr0,ip=dhcp,ip6=auto --nameserver 10.10.10.247 --searchdomain home.arpa --onboot 1 --description 'Identity: OpenLDAP and self-service HTTPS; separate local disk; no existing login migration'
fi
pct status {ct} | grep -q running || pct start {ct}
for i in $(seq 1 30); do pct exec {ct} -- getent hosts deb.debian.org >/dev/null && break; sleep 2; done
'''
    ssh(host,['bash','-c',source])
    guest(host,ct,r'''
import subprocess,pathlib,os
os.environ['DEBIAN_FRONTEND']='noninteractive'
root=pathlib.Path('/root/identity');root.mkdir(mode=0o700,exist_ok=True)
with open(root/'install.log','a') as log:
 def run(args,**kw):subprocess.run(args,check=True,stdout=log,stderr=log,timeout=300,**kw)
 run(['apt-get','update','-qq'])
 run(['debconf-set-selections'],input=b'slapd slapd/no_configuration boolean true\n')
 run(['apt-get','install','-y','--no-install-recommends','slapd','ldap-utils','openssl','ca-certificates','curl','gnupg','nginx','php-fpm','php-ldap','php-mbstring','php-gd','php-curl','python3-ldap','ldap-account-manager'])
 key=subprocess.check_output(['curl','--connect-timeout','15','--max-time','60','-fsSL','https://ltb-project.org/documentation/_static/ltb-project-debian-keyring.gpg'])
 run(['gpg','--dearmor','--yes','-o','/usr/share/keyrings/ltb-project-debian-keyring.gpg'],input=key)
 pathlib.Path('/etc/apt/sources.list.d/ltb-project.sources').write_text('Types: deb\nURIs: https://ltb-project.org/debian/stable\nSuites: stable\nComponents: main\nSigned-By: /usr/share/keyrings/ltb-project-debian-keyring.gpg\nArchitectures: amd64\n')
 run(['apt-get','update','-qq'])
 run(['apt-get','install','-y','--no-install-recommends','self-service-password'])
print('INSTALLED',subprocess.check_output(['hostname']).decode().strip())
print(subprocess.check_output(['dpkg-query','-W','slapd','ldap-account-manager','self-service-password']).decode())
print(subprocess.check_output(['hostname','-I']).decode())
''')
