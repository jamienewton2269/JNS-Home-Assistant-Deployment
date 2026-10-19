# Veyra reproducible PXE release gate — graphics and Escape navigation
Date: 2026-10-19
Status: REQUIREMENTS / NOT YET DEPLOYED OR ACCEPTED

## Reference environment
Use the working Lenovo Veyra installation as the reference state, with the individually verified graphical changes recorded in docs/veyra-working-display-baseline-2026-10-19.md. Capture both the Lenovo runtime/configuration and the Node C PXE deployment tree before changing the installer. The verified Node C backup archive was Veyra-NodeC-Complete-20261019-132942.tar.gz (6.6 GB, sha256 checked), and the recovery capture script ran out of disk; do not treat that failed second archive as a backup. Keep archives private: browser profiles, secrets and password hashes may be present.

## Non-negotiable graphical fixes
- Include systemd unit WorkingDirectory=/opt/veyra and Environment=PYTHONPATH=/opt/veyra in the installed kiosk service, not only a manual post-install override. Proof: import veyra.kiosk succeeds in installed virtualenv.
- Install, enable and configure seatd; check veyra's access to /run/seatd.sock (seatd -g video and veyra in video group) or a validated equivalent.
- Keep the tested Cage/Wayland path and Intel graphics support, Debian dependencies, Chrome runtime and UEFI/GRUB fixes.
- Replace the diagnostic ExecStart wrapper with the validated production launcher only after testing; do not ship debug redirects or unbounded Restart=always. Limit restart bursts and avoid PAM session leakage.
- Kiosk must launch automatically following cold boot and reboot. Verify physical screen displays interactive Veyra and keyboard/mouse work without manual SSH commands.
- Do not assume the historical PXE v0.9.2 payload contains these fixes: rebuild from the current captured working configuration, then test from a wiped/test target.

## Escape-key behaviour — required
Single Esc follows actual navigation history: modal or overlay -> underlying Veyra view; programme details -> result/list view; settings -> page that opened Settings; search results -> preceding view; provider browser/playback -> originating Veyra page; repeated Esc backtracks until Home; Esc at Home stays Home and NEVER quits the kiosk or opens a console. No lost provider sessions/logins. Fullscreen/player overlays must be closed/handled appropriately while retaining media continuity only where supported. When text suggestion menus are open, first Esc closes suggestions; subsequent Esc navigates back. Prevent websites swallowing Esc when returning to Veyra; browser-page JS listeners alone are insufficient. Implement the fallback at the *kiosk-level keyboard event handling / compositor or trusted input interception*, with a safe policy not to interfere with entering text or expected website controls. Persistent back-stack state is local and bounded; clear invalid history after reload.

## Test cases (run on real device)
1. Clean PXE install finishes; app automatically displays after restart; desktop keyboard and mouse respond.
2. From Home > Search > programme details: Esc -> Search; Esc -> Home; Esc at Home does nothing.
3. From Home > Settings > language/keyboard: Esc -> Home; no settings unexpectedly lost or changed.
4. From Home > Provider > playback/fullscreen: Esc -> previous provider/view or originating Veyra screen in the defined order; repeated Esc -> Home; no kiosk crash.
5. External streaming provider captures keyboard: Esc still returns through a reliable escape path.
6. Repeat flows after switching browser profiles and after reboot.
7. Kiosk failure injected once: bounded restart, no logind session explosion.
8. Verify keyboard defaults English UK; planned in-app keyboard+language choice and programme autocomplete are *separate features* and not claimed shipped until implemented.

## PXE host refactor
Current server files run from Node C /srv/veyra-pxe. Proposed dedicated LXC jns-pxe (CT215 provisional, check free ID). Create infrastructure-as-code LXC build, services, mount storage, restore, DNS, health tests, and explicit/manual controlled cutover. Do not interrupt live PXE until replacement passes. Preserve versioned immutable payloads and hashes. Avoid storing secret-containing archives in GitHub.

## Release declaration
Do not announce 'redeployable' or 'Esc working everywhere' until a clean install and the entire physical-device test matrix above are passed. Record installer checksum, test date, hardware and exact commit.
