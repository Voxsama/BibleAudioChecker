; ScriptureSound QC v2.5 - self-contained Windows installer
; build_windows.bat creates Output\ScriptureSoundQC_v2.5_Setup.exe.
; End users need only that installer; Python, packages, Qt, and FFmpeg are
; embedded in dist\ScriptureSoundQC.exe by PyInstaller.

[Setup]
AppId=Voxsama.ScriptureSoundQC
AppName=ScriptureSound QC
AppVersion=2.5
AppPublisher=Voxsama
AppPublisherURL=https://github.com/Voxsama/BibleAudioChecker
AppSupportURL=https://github.com/Voxsama/BibleAudioChecker/issues
DefaultDirName={localappdata}\Programs\ScriptureSoundQC
DefaultGroupName=ScriptureSound QC
OutputBaseFilename=ScriptureSoundQC_v2.5_Setup
OutputDir=Output
Compression=lzma2/ultra64
SolidCompression=yes
UninstallDisplayIcon={app}\ScriptureSoundQC.exe
WizardStyle=modern
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"

[Files]
Source: "dist\ScriptureSoundQC\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "README.md"; DestDir: "{app}"; Flags: ignoreversion skipifsourcedoesntexist
Source: "INSTALL.md"; DestDir: "{app}"; Flags: ignoreversion skipifsourcedoesntexist
Source: "CHANGELOG.md"; DestDir: "{app}"; Flags: ignoreversion skipifsourcedoesntexist
Source: "LICENSE"; DestDir: "{app}"; Flags: ignoreversion skipifsourcedoesntexist

[Icons]
Name: "{group}\ScriptureSound QC"; Filename: "{app}\ScriptureSoundQC.exe"
Name: "{group}\Uninstall ScriptureSound QC"; Filename: "{uninstallexe}"
Name: "{autodesktop}\ScriptureSound QC"; Filename: "{app}\ScriptureSoundQC.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\ScriptureSoundQC.exe"; Description: "Launch ScriptureSound QC"; Flags: nowait postinstall skipifsilent
