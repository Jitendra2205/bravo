; Inno Setup script: wraps dist\Bravo\ into BravoSetup.exe (Next, Next, Finish).
; Installs for the current user only, so no admin prompt. Built by .github/workflows/windows-installer.yml.
#define AppVersion GetEnv("BRAVO_VERSION")
#if AppVersion == ""
  #define AppVersion "0.0.0-dev"
#endif

[Setup]
AppId={{8C6B1E2A-5B7F-4A3C-9D61-2F0E7B4A9C11}
AppName=Bravo
AppVersion={#AppVersion}
AppPublisher=Jitendra Singh
AppPublisherURL=https://github.com/Jitendra2205/bravo
AppSupportURL=https://github.com/Jitendra2205/bravo/issues
DefaultDirName={localappdata}\Programs\Bravo
DisableProgramGroupPage=yes
DisableDirPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=dist
OutputBaseFilename=BravoSetup
SetupIconFile=ui\bravo.ico
UninstallDisplayIcon={app}\Bravo.exe
UninstallDisplayName=Bravo
LicenseFile=..\LICENSE
WizardStyle=modern
Compression=lzma2/ultra64
SolidCompression=yes
CloseApplications=yes

[Tasks]
Name: "desktopicon"; Description: "Put a Bravo icon on my desktop"

[Files]
Source: "dist\Bravo\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
; Same app ID as the running window, so a pinned icon and the open app share one taskbar button.
Name: "{autoprograms}\Bravo"; Filename: "{app}\Bravo.exe"; AppUserModelID: "Bravo.Desktop"; Comment: "Bravo, your AI agent"
Name: "{autodesktop}\Bravo"; Filename: "{app}\Bravo.exe"; AppUserModelID: "Bravo.Desktop"; Comment: "Bravo, your AI agent"; Tasks: desktopicon

[Run]
Filename: "{app}\Bravo.exe"; Description: "Start Bravo now"; Flags: nowait postinstall skipifsilent
