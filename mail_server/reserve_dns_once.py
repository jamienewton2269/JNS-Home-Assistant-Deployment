#!/usr/bin/env python3
"""One authorized DHCP reservation; preserve both nodes' existing DNS data."""
import subprocess,shlex,pathlib,hashlib,fcntl,tempfile,shutil,os,sys
MASTER=pathlib.Path("/mnt/jns-dns-publish/jns-dns")
LINE="dhcp-host=BC:24:11:52:AA:1F,10.10.110.232,jns-mail,infinite"
HOSTLINE="10.10.110.232 jns-mail.home.arpa jns-mail"
REMOTE=r'''
set -Eeuo pipefail
exec 9>/run/jns-dns-sync.lock
flock 9
root=/var/lib/jnsdns
prev="$(readlink -f "$root/active")"
old="$(cat "$root/applied")"
test "$old" = 18
test "$(sha256sum "$prev/reservations.conf" | cut -d' ' -f1)" = __CURRENT_RES_SHA__
final=
changed=0
made_final=0
done_ok=0
rollback() {
  rc=$?
  if test "$done_ok" != 1; then
    if test "$changed" = 1; then
      ln -s "$prev" "$root/active.mail-rollback"
      mv -Tf "$root/active.mail-rollback" "$root/active"
      printf '%s\n' "$old" >"$root/applied"
      systemctl restart jns-dns.service || true
    fi
    if test "$made_final" = 1 && test "$final" = "$root/releases/19" && test -d "$final"; then rm -rf -- "$final"; fi
  fi
  exit "$rc"
}
trap rollback EXIT
echo MAIL_READY
read -r rev
test "$rev" = 19
test "$(cat /mnt/master/current)" = "$rev"
final="$root/releases/$rev"
test ! -e "$final"
work="$(mktemp -d "$root/releases/.mail-stage.XXXXXXXX")"
for f in hosts.static reservations.conf manifest.sha256; do cp "/mnt/master/releases/$rev/$f" "$work/$f"; done
(cd "$work"; sha256sum -c manifest.sha256)
python3 - "$prev/reservations.conf" "$work/reservations.conf" <<'PY'
import pathlib,sys
a=pathlib.Path(sys.argv[1]).read_bytes()
b=pathlib.Path(sys.argv[2]).read_bytes()
line=b"dhcp-host=BC:24:11:52:AA:1F,10.10.110.232,jns-mail,infinite\n"
assert b==a,"Reservation changed during associated DNS update"
PY
# Preserve each node's pre-existing hosts file byte-for-byte.
cp "$prev/hosts.static" "$work/hosts.static"
printf '\\n10.10.110.232 jns-mail.home.arpa jns-mail\\n' >>"$work/hosts.static"
(cd "$work"; sha256sum hosts.static reservations.conf >manifest.sha256)
chmod 755 "$work"
chmod 644 "$work/"*
mv "$work" "$final"
made_final=1
/usr/local/sbin/jns-dns-build-config "$final"
python3 - "$prev/dnsmasq.conf" "$final/dnsmasq.conf" <<'PY'
import pathlib,re,sys
a,b=[pathlib.Path(x).read_text() for x in sys.argv[1:]]
normalize=lambda s: re.sub(r"/var/lib/jnsdns/releases/\d+","RELEASE",s)
assert normalize(a)==normalize(b),"Unexpected change to DNS/DHCP service configuration"
PY
dnsmasq --test -C "$final/dnsmasq.conf"
echo MAIL_PREPARED
read -r decision
test "$decision" = COMMIT
ln -s "$final" "$root/active.mail-new"
mv -Tf "$root/active.mail-new" "$root/active"
changed=1
systemctl restart jns-dns.service
systemctl is-active --quiet jns-dns.service
printf '%s\n' "$rev" >"$root/applied"
grep -Fx '10.10.110.232 jns-mail.home.arpa jns-mail' "$final/hosts.static"
grep -Fx 'dhcp-host=BC:24:11:52:AA:1F,10.10.110.232,jns-mail,infinite' "$final/reservations.conf"
echo MAIL_APPLIED
read -r decision
test "$decision" = DONE
done_ok=1
echo MAIL_DONE
'''
peers=[]
def wait_for(p,marker):
    while True:
        line=p.stdout.readline()
        if not line: raise RuntimeError("DHCP peer exited before "+marker)
        print(line.rstrip(),flush=True)
        if line.strip()==marker: return
def send(p,line):
    p.stdin.write(line+"\n");p.stdin.flush()
if subprocess.check_output(["hostname","-s"],text=True).strip()!="nodec": raise SystemExit("Wrong gateway")
with open(MASTER/".publish.lock","a") as lock:
    fcntl.flock(lock,fcntl.LOCK_EX)
    previous=(MASTER/"current").read_text().strip()
    if previous!="18": raise SystemExit("Master changed since preflight; inspect before retry")
    src=MASTER/"releases"/previous
    oldres=(src/"reservations.conf").read_bytes()
    current_res_sha=hashlib.sha256(oldres).hexdigest()
    if oldres.decode().splitlines().count(LINE)!=1: raise SystemExit("Expected mail reservation missing")
    oldhosts=(src/"hosts.static").read_bytes()
    if b"jns-mail" in oldhosts or b"10.10.110.232" in oldhosts: raise SystemExit("DNS entry already exists; inspect first")
    new=MASTER/"releases"/"19"
    if new.exists(): raise SystemExit("Revision 19 exists; inspect before retry")
    published=False
    try:
        for host,ct in [("nodea.home.arpa",247),("nodeb.home.arpa",248)]:
            cmd="pct exec "+str(ct)+" -- bash -c "+shlex.quote(REMOTE.replace("__CURRENT_RES_SHA__",current_res_sha))
            p=subprocess.Popen(["ssh","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes","root@"+host,cmd],
                               stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,bufsize=1)
            peers.append(p);wait_for(p,"MAIL_READY")
        stage=pathlib.Path(tempfile.mkdtemp(prefix=".mail-stage.",dir=MASTER/"releases"))
        (stage/"hosts.static").write_bytes(oldhosts+b"\n"+HOSTLINE.encode()+b"\n")
        (stage/"reservations.conf").write_bytes(oldres)
        manifest="".join(hashlib.sha256((stage/f).read_bytes()).hexdigest()+"  "+f+"\n" for f in ["hosts.static","reservations.conf"])
        (stage/"manifest.sha256").write_text(manifest)
        stage.chmod(0o755)
        for path in stage.iterdir(): path.chmod(0o644)
        os.rename(stage,new)
        tmp=MASTER/".current.mail-new";tmp.write_text("19\n");tmp.chmod(0o644);os.replace(tmp,MASTER/"current")
        published=True
        for p in peers: send(p,"19")
        for p in peers: wait_for(p,"MAIL_PREPARED")
        for p in peers: send(p,"COMMIT")
        for p in peers: wait_for(p,"MAIL_APPLIED")
        for p in peers: send(p,"DONE")
        for p in peers:
            wait_for(p,"MAIL_DONE");p.stdin.close()
            if p.wait(timeout=20)!=0: raise RuntimeError("Peer completion failed")
        print("MAIL_DNS_APPLIED_BOTH_NODES revision=19 address=10.10.110.232",flush=True)
    except BaseException:
        if published and (MASTER/"current").read_text().strip()=="19":
            tmp=MASTER/".current.mail-rollback";tmp.write_text(previous+"\n");os.replace(tmp,MASTER/"current")
        for p in peers:
            if p.poll() is None:
                try: send(p,"ROLLBACK");p.stdin.close()
                except (BrokenPipeError,ValueError): pass
                try: p.wait(timeout=30)
                except subprocess.TimeoutExpired: p.terminate()
        if published and new.exists(): shutil.rmtree(new)
        raise
