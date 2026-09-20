# JNS Deployment Platform v5.5.5

## Public-key SFTP authentication hotfix

Live management-PC enrollment reached the verified SSH host-key stage but the
subsequent SFTP login was rejected with "Authentication failed".

The JNS Secure SFTP startup script disabled password authentication correctly,
but also ran `passwd -l` on the dedicated `jnstransfer` Unix account.
OpenSSH rejects a shadow-locked account before evaluating its authorized key,
so valid enrolled management-PC keys could never authenticate.

### Changes

- JNS Secure SFTP App v0.4.2 no longer shadow-locks the SFTP account in
  public-key-only mode.
- A high-entropy, unrecorded local password is assigned at startup solely to
  keep the Unix account valid; SSH password authentication remains disabled.
- Shell access, forwarding, tunnelling and root login remain disabled.
- Enrollment now auto-updates an already-installed JNS Secure SFTP app before
  applying management-PC key policy.
- Existing legacy gateway credentials remain untouched until commissioning
  succeeds.

No Windows-side protocol change is required; Windows Management Console v5.5.2
remains compatible.
