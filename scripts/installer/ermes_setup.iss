; Inno Setup Script per Ermes Knowledge
; Genera l'installer 'Ermes-Setup.exe' per installare Ermes come qualsiasi programma Windows commerciale

#define MyAppName "Ermes Knowledge"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "Ermes Team"
#define MyAppExeName "Ermes.exe"

[Setup]
AppId={{E5F1B1C3-8A39-4D92-BB8A-1A8502E10741}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\Ermes
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
OutputDir=..\..\dist-installer
OutputBaseFilename=Ermes-Setup-v1.0.0
SetupIconFile=..\..\Ermes.ico
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64
DisableWelcomePage=no
PrivilegesRequired=lowest

[Languages]
Name: "italian"; MessagesFile: "compiler:Languages\Italian.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "..\..\Ermes.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\..\Ermes.ico"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\..\.env"; DestDir: "{app}"; Flags: ignoreversion onlyifdoesntexist
Source: "..\..\frontend\dist\*"; DestDir: "{app}\frontend\dist"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\..\api\*"; DestDir: "{app}\api"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\..\config\*"; DestDir: "{app}\config"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\..\rag\*"; DestDir: "{app}\rag"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\..\data\*"; DestDir: "{app}\data"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\..\.venv-ermes\*"; DestDir: "{app}\.venv-ermes"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\Ermes.ico"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\Ermes.ico"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent
