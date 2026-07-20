; ScriptureSound QC - Inno Setup Installer Script
; How to use:
;   1. Build the .exe first: run build_windows.bat
;   2. Install Inno Setup: https://jrsoftware.org/isdl.php
;   3. Open this file in Inno Setup Compiler
;   4. Click Build -> Compile
;   5. Your installer will be at: Output\ScriptureSoundQC_Setup.exe

[Setup]
AppName=ScriptureSound QC
AppVersion=2.5
AppPublisher=Voxsama
AppPublisherURL=https://github.com/Voxsama/BibleAudioChecker
DefaultDirName={autopf}\ScriptureSoundQC
DefaultGroupName=ScriptureSound QC
OutputBaseFilename=ScriptureSoundQC_v2.5_Setup
OutputDir=Output
Compression=lzma2
SolidCompression=yes
; SetupIconFile=icon.ico  (uncomment this line if you have icon.ico in this folder)
UninstallDisplayIcon={app}\ScriptureSoundQC.exe
WizardStyle=modern
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"
Name: "startmenu"; Description: "Create Start Menu shortcut"; GroupDescription: "Additional shortcuts:"; Flags: checkedonce

[Files]
; Main application (entire dist folder)
Source: "dist\ScriptureSoundQC\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

; ffmpeg (optional - only if you placed it in the folder)
; Source: "ffmpeg.exe"; DestDir: "{app}"; Flags: ignoreversion skipifsourcedoesntexist

; Icon (optional)
; Source: "icon.ico"; DestDir: "{app}"; Flags: ignoreversion skipifsourcedoesntexist

; Assets
Source: "assets\*"; DestDir: "{app}\assets"; Flags: ignoreversion recursesubdirs createallsubdirs skipifsourcedoesntexist

; Documentation
Source: "README.md"; DestDir: "{app}"; Flags: ignoreversion skipifsourcedoesntexist
Source: "INSTALL.md"; DestDir: "{app}"; Flags: ignoreversion skipifsourcedoesntexist
Source: "CHANGELOG.md"; DestDir: "{app}"; Flags: ignoreversion skipifsourcedoesntexist
Source: "LICENSE"; DestDir: "{app}"; Flags: ignoreversion skipifsourcedoesntexist

[Icons]
Name: "{group}\ScriptureSound QC"; Filename: "{app}\ScriptureSoundQC.exe"; IconFilename: "{app}\icon.ico"
Name: "{group}\Uninstall ScriptureSound QC"; Filename: "{uninstallexe}"
Name: "{autodesktop}\ScriptureSound QC"; Filename: "{app}\ScriptureSoundQC.exe"; IconFilename: "{app}\icon.ico"; Tasks: desktopicon

[Run]
Filename: "{app}\ScriptureSoundQC.exe"; Description: "Launch ScriptureSound QC"; Flags: nowait postinstall skipifsilent
