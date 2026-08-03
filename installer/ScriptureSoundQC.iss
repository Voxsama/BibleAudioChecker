#define MyAppName "ScriptureSoundQC"
#define MyAppVersion "4.0.0"
#define MyAppDisplayVersion "v4.0 Beta"
#define MyAppPublisher "VerseVox Studio"
#define MyAppExeName "ScriptureSoundQC.exe"
#ifndef AppBinaryDir
  #define AppBinaryDir "..\dist-beta\ScriptureSoundQC"
#endif

[Setup]
AppId={{F397141C-C3D6-49DB-A98B-C8D4EF7A976A}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppDisplayVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL=https://github.com/Voxsama/BibleAudioChecker
AppSupportURL=https://github.com/Voxsama/BibleAudioChecker/issues
AppUpdatesURL=https://github.com/Voxsama/BibleAudioChecker/releases
DefaultDirName={localappdata}\Programs\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\dist\installer
OutputBaseFilename=ScriptureSoundQC-Setup-v4.0-Beta
SetupIconFile=..\icon.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
LicenseFile=..\LICENSE
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
CloseApplications=force
RestartApplications=no
SetupLogging=yes
VersionInfoVersion=4.0.0.0
VersionInfoCompany={#MyAppPublisher}
VersionInfoDescription={#MyAppName} installer
VersionInfoProductName={#MyAppName}
VersionInfoProductVersion=4.0.0.0
VersionInfoCopyright=Copyright (C) 2024-2026 {#MyAppPublisher}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked

[Files]
Source: "{#AppBinaryDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\LICENSE"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\README.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\BRAND_POLICY.md"; DestDir: "{app}"; Flags: ignoreversion

[InstallDelete]
; Remove files extracted by an older one-folder release before replacing them.
Type: filesandordirs; Name: "{app}\_internal"

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent
