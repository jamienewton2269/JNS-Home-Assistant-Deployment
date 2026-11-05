#!/usr/bin/env python3
"""One authorized DHCP reservation; preserve both nodes' existing DNS data."""
import subprocess,shlex,pathlib,hashlib,fcntl,tempfile,shutil,os,sys
MASTER=pathlib.Path("/mnt/jns-dns-publish/jns-dns")
LINE="dhcp-host=BC:24:11:52:AA:1F,10.10.110.232,jns-mail,infinite"
EXPECTED="f852d386cb893eecbed8a3a65639d3b94857d5d3565910da1ec06a25b12dcd7e"
REMOTE=r'''
set -Eeuo pipefail
exec 9>/run/jns-dns-sync.lock
flock 9
root=/var/lib/jnsdns
prev="$(readlink -f "$root/active")"
old="$(cat "$root/applied")"
test "$old" = 17
test "$(sha256sum "$prev/reservations.conf" | cut -d' ' -f1)" = f852d386cb893eecbed8a3a65639d3b94857d5d3565910da1ec06a25b12dcd7e
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
    if test "$made_final" = 1 && test "$final" = "$root/releases/18" && test -d "$final"; then rm -rf -- "$final"; fi
  fi
  exit "$rc"
}
trap rollback EXIT
echo MAIL_READY
read -r rev
test "$rev" = 18
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
assert b==a+(b"" if a.endswith(b"\n") else b"\n")+line,"Reservation diff exceeds one authorized line"
PY
# Preserve each node's pre-existing hosts file byte-for-byte.
cp "$prev/hosts.static" "$work/hosts.static"
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
cmp "$prev/hosts.static" "$final/hosts.static"
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
    if previous!="17": raise SystemExit("Master changed since preflight; inspect before retry")
    src=MASTER/"releases"/previous
    oldres=(src/"reservations.conf").read_bytes()
    if hashlib.sha256(oldres).hexdigest()!=EXPECTED: raise SystemExit("Reservations changed")
    if any(x in oldres.lower() for x in [b"bc:24:11:52:aa:1f",b"10.10.110.232",b"jns-mail"]): raise SystemExit("Reservation already exists or conflicts")
    new=MASTER/"releases"/"18"
    if new.exists(): raise SystemExit("Revision 18 exists; inspect before retry")
    published=False
    try:
        for host,ct in [("nodea.home.arpa",247),("nodeb.home.arpa",248)]:
            cmd="pct exec "+str(ct)+" -- bash -c "+shlex.quote(REMOTE)
            p=subprocess.Popen(["ssh","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes","root@"+host,cmd],
                               stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,bufsize=1)
            peers.append(p);wait_for(p,"MAIL_READY")
        stage=pathlib.Path(tempfile.mkdtemp(prefix=".mail-stage.",dir=MASTER/"releases"))
        shutil.copyfile(src/"hosts.static",stage/"hosts.static")
        (stage/"reservations.conf").write_bytes(oldres+(b"" if oldres.endswith(b"\n") else b"\n")+LINE.encode()+b"\n")
        manifest="".join(hashlib.sha256((stage/f).read_bytes()).hexdigest()+"  "+f+"\n" for f in ["hosts.static","reservations.conf"])
        (stage/"manifest.sha256").write_text(manifest)
        stage.chmod(0o755)
        for path in stage.iterdir(): path.chmod(0o644)
        os.rename(stage,new)
        tmp=MASTER/".current.mail-new";tmp.write_text("18\n");tmp.chmod(0o644);os.replace(tmp,MASTER/"current")
        published=True
        for p in peers: send(p,"18")
        for p in peers: wait_for(p,"MAIL_PREPARED")
        for p in peers: send(p,"COMMIT")
        for p in peers: wait_for(p,"MAIL_APPLIED")
        for p in peers: send(p,"DONE")
        for p in peers:
            wait_for(p,"MAIL_DONE");p.stdin.close()
            if p.wait(timeout=20)!=0: raise RuntimeError("Peer completion failed")
        print("RESERVATION_APPLIED_BOTH_NODES revision=18 address=10.10.110.232",flush=True)
    except BaseException:
        if published and (MASTER/"current").read_text().strip()=="18":
            tmp=MASTER/".current.mail-rollback";tmp.write_text(previous+"\n");os.replace(tmp,MASTER/"current")
        for p in peers:
            if p.poll() is None:
                try: send(p,"ROLLBACK");p.stdin.close()
                except (BrokenPipeError,ValueError): pass
                try: p.wait(timeout=30)
                except subprocess.TimeoutExpired: p.terminate()
        if published and new.exists(): shutil.rmtree(new)
        raise
