# JNS SSH Terminal Roadmap

## v0.1 - reliable SSH console

Acceptance gates:

- [x] WPF native UI
- [x] SSH.NET transport through VirtualTerminal
- [x] password and private-key authentication
- [x] first-use host-key confirmation and stored SHA256 fingerprint
- [x] select-to-copy
- [x] right-click paste
- [x] Ctrl+V paste
- [x] Ctrl+C is reserved for copy
- [x] bounded terminal scrollback
- [x] Clear Screen Buffer purges local scrollback without disconnecting
- [x] Live clear-buffer test without dropping SSH
- [x] explicit memory reclamation after buffer purge
- [x] separate bounded command history
- [x] script/multiline history session-only unless pinned
- [x] credentials are not persisted
- [x] Release build validated on Windows
- [x] Live SSH test against Node C
- [x] Clipboard round-trip test with long multiline ChatGPT commands

## v0.1.2 - two SSH sessions

Acceptance gates:

- [x] two fixed terminal tabs
- [x] independent SSH connection per tab
- [x] independent screen buffer and scrollback per tab
- [x] switching tabs keeps both SSH sessions alive
- [x] connect/disconnect targets active tab
- [x] copy/paste/clear buffer targets active tab
- [x] Command Bar sends to active tab
- [x] shared bounded command history
- [ ] Windows build validated
- [ ] live simultaneous two-host test

## v0.1.4 - explicit stop button

Acceptance gates:

- [x] Ctrl+C remains a copy shortcut and never interrupts the remote process
- [x] select-to-copy remains unchanged
- [x] Stop Current (^C) sends ETX / SIGINT to the foreground process on the active tab
- [x] no dependency on remote process names such as `killall watch`
- [x] Windows build validated
- [x] live Stop Current test against a running `watch`

## v0.1.5 - dynamic terminal tabs

Acceptance gates:

- [x] + New Terminal button
- [x] create Terminal 3, 4, 5, etc. on demand
- [x] every added tab gets an independent SSH connection, screen buffer and scrollback
- [x] adding a tab does not disconnect or clear existing tabs
- [x] Connect / Disconnect / Copy / Paste / Clear Buffer / Stop Current target the active tab
- [x] Windows build validated
- [ ] live test creating a third terminal while two sessions remain connected

## v0.1.6 - persistent detach / reattach

Acceptance gates:

- [x] tmux-backed persistence when tmux is available on the remote host
- [x] Detach & Close removes the local tab without stopping the remote terminal
- [x] detached session metadata persists locally without credentials
- [x] Reattach Detached Session reconnects to the same tmux terminal after authentication
- [x] Kill Remote Session terminates the tmux session and closes the local tab
- [x] non-tmux hosts refuse safe detach rather than falsely claiming persistence
- [x] closing the Windows app records live tmux sessions for later reattachment
- [x] Connect cannot silently replace an already-connected terminal
- [x] Windows build validated
- [ ] live detach / reconnect test
- [ ] live kill-session cleanup test

## v0.1.7 - visible scrollbars and active-tab select all

Acceptance gates:

- [x] retain 3000 scrollback lines per terminal (well above requested 500 minimum)
- [x] visible vertical scrollbar on every startup and dynamically-created terminal tab
- [x] scrollbar operates only on its own terminal buffer
- [x] mouse-wheel scroll remains synchronized with the visible scrollbar
- [x] Select All button beside Copy / Paste
- [x] Select All targets only the active terminal tab
- [x] Windows build validated
- [ ] live scrollbar + Select All test with multiple connected tabs

## v0.1.8 - persistent registry, secure credentials and generated keys

Acceptance gates:

- [x] persistent tmux-session registry survives Windows restart/reboot
- [x] statuses are explicitly UNKNOWN / RUNNING DETACHED / RUNNING ATTACHED / ENDED
- [x] Refresh / Discover reconciles local state against remote tmux
- [x] orphaned remote `jns-*` tmux sessions can be rediscovered
- [x] New Terminal remains available regardless of old registry entries
- [x] ended entries are retained briefly for visibility, then watchdog-pruned after 7 days
- [x] UNKNOWN and RUNNING sessions are never age-pruned
- [x] startup + 24-hour watchdog removes stale temp files and enforces bounded history
- [x] optional SSH passwords use Windows Credential Manager, never JNS JSON/registry
- [x] password byte buffers are zeroed after authentication where SSH.NET permits
- [x] automated ECDSA P-256 key generation
- [x] generated private keys are DPAPI current-user protected at rest
- [x] public key can be copied for authorized_keys installation
- [x] Clear Screen Buffer also clears the active selection highlight immediately
- [ ] Windows build validated
- [ ] live generated-key login test
- [ ] live registry test across Windows reboot
- [ ] live remote discovery + ended cleanup test

## v0.1.8.1 - resizable connection panel

Acceptance gates:

- [x] draggable internal divider between left connection/session pane and terminal workspace
- [x] left pane starts at 275 px
- [x] left pane constrained to a practical 220-520 px range
- [x] terminal workspace retains a minimum usable width
- [x] Windows build validated
- [ ] live drag-resize test while multiple terminal tabs are connected

## v0.1.8.3 - high-visibility terminal scrollbars

Acceptance gates:

- [x] preserve the existing 18 px scrollbar width
- [x] draggable thumb has a 48 px minimum grab height
- [x] thumb uses a bright high-contrast idle state against the dark terminal
- [x] thumb has a visible three-line grip
- [x] near-white hover and active-drag states
- [x] visible up/down controls
- [x] track remains clickable for page-up/page-down
- [x] same style applied to startup and dynamically-created terminal tabs
- [x] Windows build validated
- [ ] live drag/hover/page-scroll test

## v0.1.9 - hardened self-contained release (after v0.1.8 live tests)

Planned release gates:

- [ ] win-x64 self-contained single executable
- [ ] no loose managed runtime/library files required beside the EXE
- [ ] ReadyToRun/startup-performance review where it improves real use
- [ ] no unsafe WPF trimming that risks runtime breakage
- [ ] dependency/security audit and pinned versions
- [ ] secret lifetime / memory-copy review
- [ ] filesystem and credential-storage permission review
- [ ] release integrity hash and signed-release path

## v0.2 - ChatGPT integration

Goal: the JNS SSH Terminal becomes the normal work surface so browser copy/paste is no
longer required.

Planned capabilities:

1. Native conversation pane in the same application.
2. Supported OpenAI authentication/integration only; no browser-cookie reuse or web scraping.
3. Prefer Sign in with ChatGPT when available to this application; fallback to API
   credentials stored using Windows secure credential storage.
4. Responses/Conversations-based state managed by the app.
5. Send:
   - selected terminal output,
   - visible terminal screen,
   - a manually selected command-history item,
   - optional host/profile metadata (never credentials).
6. Assistant responses can contain ordinary prose plus proposed shell commands.
7. Proposed commands have:
   - Copy
   - Insert into Command Bar
   - Save/pin
   - **no automatic Execute button**
8. Terminal output remains bounded and purgeable independently of conversation history.
9. Conversation history has its own explicit clear/export controls.
10. Existing chatgpt.com conversations/memory are not assumed accessible merely because
    the same ChatGPT account authenticated the application.

## Later, only if justified

Potential additions must earn their complexity:

- SFTP drop/send,
- SSH jump-host profile,
- Windows OpenSSH-agent support,
- signed portable release.

Not planned unless a real requirement appears:

- Electron/Chromium shell,
- plugin marketplace,
- themes ecosystem,
- terminal scripting language,
- embedded browser,
- cloud sync of SSH credentials.
