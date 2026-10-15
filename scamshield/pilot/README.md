# JNS ScamShield — Windows 11 pilot (NOT a customer release)

This is an **unsigned PowerShell pilot** for an isolated clean Windows 11 testing machine. No antivirus replacement, browser injection, Defender bypass, downloads, telemetry, or Cloudflare publication.

## Install on a CLEAN test machine
1. Get the `scamshield-win11-pilot` artifact from the Windows validation GitHub Actions run on this branch (requires successful workflow).
2. Extract it. In an elevated Windows PowerShell window, change to the extracted folder.
3. Run `powershell.exe -NoProfile -File .\ScamShield.ps1 -Mode Audit` to inspect.
4. Run `powershell.exe -NoProfile -File .\Install-Pilot.ps1` to enforce Edge and Chrome website-notification and pop-up blocking.
5. Completely restart Edge and Chrome; inspect `edge://policy` and `chrome://policy`; verify websites cannot request notification permission, and Windows Security remains healthy.
6. Reboot and verify protection again. The scheduled task runs at startup and hourly.

## Undo
Elevated PowerShell: `powershell.exe -NoProfile -File .\Install-Pilot.ps1 -Uninstall`.
The pilot removes only registry values it created and only if still matching the deployed setting. Existing conflicting managed settings are not overwritten. It leaves the audit logs and installed files in `C:\ProgramData\JNS\ScamShield` for inspection.

## Known limits
- **Not an installer EXE**; not Authenticode signed; do not deploy to real customers.
- Not a universal blocker of in-page scam content, phishing, all pop-up mechanisms, Firefox notifications or malware.
- Windows SmartScreen is intentionally **not altered**. Defender is read-only; real-time protection, tamper status and PUA status are reported, not repaired.
- Tests performed by GitHub Actions are code syntax/audit checks, **not verification of website behavior**.
- Policy settings may differ on managed devices. Do not test on a company-managed PC.
- Windows may show standard PowerShell safety prompts. **Never disable SmartScreen or Defender to run this pilot.**
