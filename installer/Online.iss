; Built with release-specific URL, size and SHA-256 by build_online_installer.py.
; Inno Setup's native downloader verifies the payload before launching Setup.
#if Ver < EncodeVer(6, 5, 0)
  #error Inno Setup 6.5 or newer is required
#endif
[Setup]
AppName=ScriptureSoundQC Online Installer
AppVersion=4.0.0
AppPublisher=VerseVox Studio
CreateAppDir=no
Uninstallable=no
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
DisableProgramGroupPage=yes
DisableReadyPage=yes
OutputDir={#OutputPath}
OutputBaseFilename={#OutputName}
SetupIconFile=..\icon.ico
WizardStyle=modern
SetupLogging=yes

[Messages]
WelcomeLabel2=This installer downloads ScriptureSoundQC and its dependencies, verifies the download, then opens the full Setup wizard.%n%nInternet access is required. Language models are separate downloads.
FinishedLabel=The ScriptureSoundQC Setup wizard has completed.

[Files]
Source: "{#PayloadURL}"; DestDir: "{tmp}"; DestName: "ScriptureSoundQC-Offline.exe"; ExternalSize: {#PayloadSize}; Hash: "{#PayloadHash}"; Flags: external download ignoreversion deleteafterinstall; AfterInstall: RunFullSetup

[Code]
var
  ChildExitCode: Integer;

procedure RunFullSetup;
var
  Parameters: String;
begin
  Parameters := '/SP- /NORESTART';
  if WizardSilent then
    Parameters := Parameters + ' /VERYSILENT /SUPPRESSMSGBOXES';
  if not Exec(ExpandConstant('{tmp}\ScriptureSoundQC-Offline.exe'),
      Parameters, '', SW_SHOWNORMAL, ewWaitUntilTerminated, ChildExitCode) then
    RaiseException('Could not start the downloaded Setup.');
  if (ChildExitCode <> 0) and (ChildExitCode <> 3010) then
    RaiseException(Format('Setup did not complete (exit code %d). You can run this online installer again.', [ChildExitCode]));
end;

function GetCustomSetupExitCode: Integer;
begin
  Result := ChildExitCode;
end;
