#define AppName "JNS ScamShield Pilot"
#define AppVersion "0.4.0"
[Setup]
AppId=JNS-ScamShield-Pilot
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=JNS
DefaultDirName={autopf}\JNS\ScamShield
DefaultGroupName=JNS ScamShield
OutputDir=..\..\out
OutputBaseFilename=JNS-ScamShield-Setup-v0.4.0-UNSIGNED
Compression=lzma2
SolidCompression=yes
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
[Files]
Source: "..\publish\JNSScamShield.exe"; DestDir: "{app}"; Flags: ignoreversion
[Icons]
Name: "{group}\ScamShield Audit"; Filename: "{app}\JNSScamShield.exe"; Parameters: "audit"
[Run]
Filename: "{app}\JNSScamShield.exe"; Parameters: "enforce"; Flags: runhidden waituntilterminated
[UninstallRun]
Filename: "{app}\JNSScamShield.exe"; Parameters: "restore"; Flags: runhidden waituntilterminated
