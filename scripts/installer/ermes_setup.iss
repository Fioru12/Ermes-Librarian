; Inno Setup Script per Ermes Knowledge  --  SPERIMENTALE, NON PROVATO
;
; Stato onesto (22 ottobre 2026): questo script non e' mai stato compilato ne' provato su un
; PC pulito. Una revisione ha trovato che la versione precedente
;   - impacchettava il file `.env` dello sviluppatore (chiavi e password) e la cartella `data/`
;     (database, utenti, configurazione) dentro l'installer, cioe' li avrebbe consegnati a chiunque
;     lo installasse;
;   - includeva `.venv-ermes`, che non e' trasferibile (contiene percorsi assoluti) e pesa GB;
;   - non copiava `core/`, che l'applicazione importa, e puntava a una cartella `rag/` che non esiste.
; Ora non porta con se' segreti ne' dati (un test lo impedisce: tests/test_installer_safety.py).
;
; Cosa NON fa ancora: non include Python. Chi installa deve avere Python 3.11 e creare
; l'ambiente con `pip install -r requirements.txt` nella cartella di installazione. Finche' non
; esiste un runtime incluso e una prova su un PC pulito, per l'uso quotidiano e per le
; aziende la strada supportata e' CREA_COLLEGAMENTO_DESKTOP.bat dal repository.

#define MyAppName "Ermes Knowledge"
#define MyAppVersion "2.5.0"
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
OutputBaseFilename=Ermes-Setup-v{#MyAppVersion}
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
; Il lanciatore e l'icona
Source: "..\..\Ermes.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\..\Ermes.ico"; DestDir: "{app}"; Flags: ignoreversion
; Configurazione di partenza: il MODELLO, mai il `.env` vero dello sviluppatore
Source: "..\..\.env.example"; DestDir: "{app}"; DestName: ".env"; Flags: onlyifdoesntexist
; Codice dell'applicazione (nessun dato, nessun segreto, nessun ambiente virtuale)
Source: "..\..\api\*"; DestDir: "{app}\api"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\..\core\*"; DestDir: "{app}\core"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\..\config\*"; DestDir: "{app}\config"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\..\frontend\dist\*"; DestDir: "{app}\frontend\dist"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\..\requirements.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\..\pyproject.toml"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\Ermes.ico"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\Ermes.ico"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent
