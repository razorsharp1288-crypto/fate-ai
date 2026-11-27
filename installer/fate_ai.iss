; Inno Setup script for FATE AI. Per-user install: no administrator rights required.
; Build: iscc /DAppVersion=0.1.0 installer\fate_ai.iss   (after PyInstaller produced dist\FateAI)
#ifndef AppVersion
  #define AppVersion "0.1.0"
#endif

[Setup]
AppId={{7B6C4E3A-6F1D-4C55-9C1E-FA7EA1D0A1E5}
AppName=FATE AI
AppVersion={#AppVersion}
AppPublisher=FATE AI
AppPublisherURL=https://github.com/
DefaultDirName={localappdata}\Programs\FATE AI
DefaultGroupName=FATE AI
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=Output
OutputBaseFilename=FateAI-{#AppVersion}-setup
SetupIconFile=..\assets\fate_ai.ico
UninstallDisplayIcon={app}\FateAI.exe
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.17763
LicenseFile=..\LICENSE
CloseApplications=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "..\dist\FateAI\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\FATE AI"; Filename: "{app}\FateAI.exe"
Name: "{group}\Uninstall FATE AI"; Filename: "{uninstallexe}"
Name: "{autodesktop}\FATE AI"; Filename: "{app}\FateAI.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\FateAI.exe"; Description: "{cm:LaunchProgram,FATE AI}"; Flags: nowait postinstall skipifsilent
; After an in-app automatic update (/UPDATE=1) relaunch FATE AI even though setup ran silently.
Filename: "{app}\FateAI.exe"; Flags: nowait; Check: IsAppUpdate

[UninstallRun]
; Remove the optional "launch at sign-in" entry if the user enabled it.
Filename: "{sys}\reg.exe"; Parameters: "delete HKCU\Software\Microsoft\Windows\CurrentVersion\Run /v ""FATE AI"" /f"; Flags: runhidden; RunOnceId: "RemoveAutostart"

; User data (%LOCALAPPDATA%\FateAI) and API keys are intentionally kept on uninstall so a reinstall keeps
; your chats. Use Settings > Privacy > "Delete all local data" before uninstalling to remove everything.

[Code]
function IsAppUpdate: Boolean;
begin
  Result := ExpandConstant('{param:UPDATE|0}') = '1';
end;
