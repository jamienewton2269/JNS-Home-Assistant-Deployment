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
- [x] Ctrl+C copies a selection, otherwise remains terminal interrupt
- [x] bounded terminal scrollback
- [x] Clear Screen Buffer purges local scrollback without disconnecting
- [x] Live clear-buffer test without dropping SSH
- [x] explicit memory reclamation after buffer purge
- [x] separate bounded command history
- [x] script/multiline history session-only unless pinned
- [x] credentials are not persisted
- [ ] Release build validated on Windows
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

## v0.1.3 - reliable interrupt

Acceptance gates:

- [x] Ctrl+C in a focused terminal always sends ETX / SIGINT
- [x] select-to-copy remains unchanged
- [x] Ctrl+Shift+C remains explicit copy
- [x] Stop (^C) button interrupts the foreground process on the active tab
- [x] no dependency on remote process names such as `killall watch`
- [ ] Windows build validated
- [ ] live interrupt test against a running `watch`

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

- tabs for multiple SSH sessions,
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
