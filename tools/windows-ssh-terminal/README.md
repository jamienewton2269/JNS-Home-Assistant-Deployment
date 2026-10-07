# JNS SSH Terminal

A deliberately small Windows SSH terminal for the JNS management workflow.

The design goal is not to compete with full terminal suites. It is to make the common
ChatGPT / shell workflow reliable:

- select terminal text -> copied to the Windows clipboard
- right-click -> paste
- Ctrl+V -> paste
- Ctrl+C -> copy only; remote interrupt is the explicit Stop Current (^C) button
- saved hosts without saved credentials
- independent terminal tabs; two are present at startup and **+ New Terminal** creates additional sessions on demand
- 3000 retained scrollback lines and a visible vertical scrollbar per terminal
- **Select All** / Copy / Paste operate only on the active terminal
- clear the complete local screen/scrollback buffer without dropping the SSH connection
- release references held by the cleared buffer and request managed/Windows working-set reclamation
- useful command history kept separately from terminal scrollback
- multiline/script blocks are session-only unless explicitly pinned

## Core stack

- .NET 10 WPF
- [VirtualTerminal](https://github.com/Rikitav/VirtualTerminal) 1.10.0
  - Apache-2.0
  - provides the VT/ANSI renderer and WPF terminal control
- [SSH.NET](https://github.com/sshnet/SSH.NET) 2026.0.0
  - MIT
  - provides SSH transport and authentication

No Electron, embedded Chromium, Node runtime, telemetry framework, cloud service or
background daemon is required.

## Clipboard behavior

The terminal intentionally uses ordinary Windows expectations:

- drag-select: copy
- right-click: paste
- Ctrl+V: paste
- Ctrl+Shift+C: copy
- Ctrl+C: copy only
- Stop Current (^C): send the terminal interrupt / SIGINT to the active session

## Clear Screen Buffer

**Clear Screen Buffer** is local-only.

It:

1. drops every retained scrollback row,
2. clears both terminal screen grids,
3. restores the configured bounded scrollback capacity,
4. keeps the SSH transport connected,
5. does not send `clear`, `reset`, `ESC[3J` or any other command to the server,
6. forces managed garbage collection after the purge,
7. asks Windows to trim the process working set.

The operating system remains free to manage process memory, so Task Manager working-set
figures are not a contractual measurement of bytes released. The important guarantee is
that the application no longer retains the old terminal-buffer objects.

## Command history

Terminal output is **not** command history.

The Command Bar is the explicit history boundary:

- commands sent from the Command Bar are recorded,
- ordinary direct terminal keystrokes are not recorded,
- this prevents password prompts such as `sudo` from being captured,
- single-line commands persist (maximum 500 entries / bounded total text),
- multiline blocks are marked `[BLOCK]` and remain session-only,
- pinning a block explicitly makes it persistent,
- history can be loaded back into the Command Bar without automatically executing it.

## Host security

Saved profiles contain host, port, username and optional key-file path only.
Passwords and key passphrases are never written to the profile store.

When the user explicitly enables **Remember SSH account password securely**, the password is stored in Windows Credential Manager under the current Windows account, not in JNS JSON files or the registry. During password authentication JNS uses SSH.NET's byte-array authentication path and zeroes the temporary password byte array after authentication.

**Generate Secure Key** creates an ECDSA P-256 keypair. The private PKCS#8 key is protected with Windows DPAPI in current-user scope before it is written under `%LOCALAPPDATA%\\JNS\\SshTerminal\\keys`. The OpenSSH-format public key is stored separately and can be copied for installation in `~/.ssh/authorized_keys`.

On first connection the SHA256 server host-key fingerprint is shown for approval.
The accepted key is stored locally. A later mismatch is rejected rather than silently
accepted.

Local files are stored under:

`%LOCALAPPDATA%\JNS\SshTerminal\`

## Build

Requires the .NET 10 SDK:

```powershell
dotnet restore .\JnsSshTerminal\JnsSshTerminal.csproj
dotnet build .\JnsSshTerminal\JnsSshTerminal.csproj -c Release
dotnet publish .\JnsSshTerminal\JnsSshTerminal.csproj -c Release --no-self-contained
```

A framework-dependent build is intentional: we do not bundle an entire private .NET
runtime into every copy of this small application.

## v0.1.2 - second terminal tab

The application provides two fixed terminal tabs. Each tab owns its own SSH client, shell stream, screen buffer and scrollback. Connect, Disconnect, Copy, Paste, Clear Screen Buffer and the Command Bar always target the active tab. Command history remains deliberately shared because it is a reusable command library rather than terminal output.

## v0.1.5 - dynamic terminal tabs

Two terminal tabs are available at startup. **+ New Terminal** adds more without reconnecting or disturbing existing sessions. Every tab owns an independent SSH client, shell stream, screen buffer and scrollback. All terminal actions operate on the currently active tab.

## v0.1.6 - persistent remote terminals

On hosts with **tmux** installed, new terminals are automatically wrapped in a uniquely named tmux session. **Detach & Close** removes the local view and SSH transport while leaving the remote terminal and its foreground command running. The app stores only the host/user/tmux identifier and optional key-file path in `%LOCALAPPDATA%\\JNS\\SshTerminal\\detached-sessions.json`; passwords and passphrases are never stored. **Reattach Detached Session** authenticates again and attaches to the same tmux session.

**Kill Remote Session** is intentionally destructive: it kills the remote tmux session and closes the local tab. If tmux is not available, the app refuses a persistence detach rather than implying an ordinary SSH PTY can be reconstructed later.

Closing the Windows application records connected tmux sessions as detached, so they can be found after reopening the app. This survives closing/restarting the client, but a reboot of the remote server normally destroys tmux sessions unless the workload has separate reboot persistence.

## v0.1.7 - terminal scrolling and selection

Every terminal retains up to **3000 scrollback lines** and has its own visible vertical scrollbar. The bar and mouse wheel navigate only that tab's retained buffer. **Select All** is beside Copy and Paste and applies only to the active terminal tab.

## v0.1.8 - persistent registry and local-data watchdog

Every JNS-created tmux session is written to the local registry as soon as it is created, so even an unexpected Windows reboot leaves enough metadata to find it again. On the next application start the status is deliberately **UNKNOWN / NOT CHECKED** until **Refresh / Discover** authenticates to the remote host and asks tmux for the authoritative state. Remote `jns-*` sessions missing from the laptop registry are rediscovered. Missing registered sessions are marked **ENDED**.

The local-data watchdog runs at startup and every 24 hours while the application is open. It removes stale transaction `*.tmp` files, reapplies command-history bounds, deduplicates the session registry and removes only entries that the remote host previously confirmed ended and that have then been ended for seven days. Unknown or running sessions are never removed because of age.

Clear Screen Buffer also clears any local selection highlight before purging the screen/scrollback, so the viewport returns immediately to the normal black background.

## v0.1.9 - hardened self-contained Windows release

After v0.1.8 has passed the live key/registry/reboot tests, the next packaging pass will publish a win-x64 self-contained single executable so the installed folder does not depend on loose .NET/runtime library files. That pass will also include the dependency, secret-lifetime, file-permission and startup-performance review. WPF trimming will not be enabled merely to reduce size if it compromises reliability.

## v0.2 - native ChatGPT workspace

The next version removes the browser copy/paste loop.

Planned layout:

```text
+----------------------+-------------------------------+
| Saved SSH hosts      | SSH terminal                  |
| connection controls  |                               |
|                      |                               |
+----------------------+-------------------------------+
| ChatGPT conversation / proposed commands             |
+------------------------------------------------------+
```

Key rules:

- use a supported OpenAI integration, never scrape or automate chatgpt.com,
- prefer **Sign in with ChatGPT** if the application can participate in that program;
  otherwise support the OpenAI Responses/Conversations API,
- API credentials, if required, go in Windows secure credential storage, never JSON,
- the app owns its native conversation state,
- authentication alone does not grant access to existing ChatGPT web conversations or memories,
- selected terminal output can be sent to ChatGPT directly,
- assistant commands are inserted into the Command Bar for review,
- **assistant output is never automatically executed over SSH**.

This preserves the JNS rule that AI can propose and prepare operations while the human
retains the final execution boundary.
