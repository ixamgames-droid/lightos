; XPLAT-47: Inno-Setup-Skript fuer LightOS-Setup.exe.
;
; Voraussetzung: der PyInstaller-Build liegt in dist\LightOS\ (siehe
; LightOS.spec). Bauen:
;     iscc /DAppVersion=1.0.0 packaging\windows\LightOS.iss
; Ergebnis: dist\setup\LightOS-Setup.exe
;
; Die Version kommt aus dem Repo (APP_VERSION in main.py); der Workflow
; .github/workflows/windows-setup.yml liest sie aus und reicht sie per
; /DAppVersion herein. Ohne Angabe steht hier ein erkennbarer Platzhalter.
;
; Installiert nach "Programme" (x64). Auf Windows-ARM laeuft das x64-Paket in
; der Emulation - inklusive QtWebEngine, also mit 3D-Visualizer (XPLAT-46).
; Nutzerdaten liegen NICHT im Programmordner, sondern in %APPDATA%\LightOS;
; der Deinstaller laesst sie deshalb unangetastet.

#ifndef AppVersion
  #define AppVersion "0.0.0-dev"
#endif
#define RepoDir "..\.."
#ifndef DistDir
  #define DistDir RepoDir + "\dist\LightOS"
#endif

[Setup]
AppId={{CB37FA43-6DFC-4892-8CCF-617F60194DF6}
AppName=LightOS
AppVersion={#AppVersion}
AppVerName=LightOS {#AppVersion}
AppPublisher=LightOS
AppComments=DMX-Lichtsteuerung
DefaultDirName={autopf}\LightOS
DefaultGroupName=LightOS
DisableProgramGroupPage=yes
OutputDir={#RepoDir}\dist\setup
OutputBaseFilename=LightOS-Setup
SetupIconFile={#RepoDir}\assets\icons\lightos.ico
UninstallDisplayIcon={app}\LightOS.exe
UninstallDisplayName=LightOS {#AppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
; x64compatible = x64-Windows UND Windows 11 auf ARM64 (x64-Emulation).
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
; Standard: fuer alle Benutzer nach "Programme" (Admin). Im Dialog laesst sich
; stattdessen "nur fuer mich" waehlen ({autopf} zeigt dann in den Nutzerordner).
PrivilegesRequired=admin
PrivilegesRequiredOverridesAllowed=dialog
CloseApplications=yes
MinVersion=10.0

[Languages]
Name: "german"; MessagesFile: "compiler:Languages\German.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; Der komplette PyInstaller-onedir-Build (LightOS.exe + _internal\ mit Python,
; Qt/QtWebEngine und den mitgelieferten Daten).
Source: "{#DistDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
; Lizenzen der Fremd-Komponenten sichtbar neben der exe (liegen zusaetzlich
; im Bundle, wo die App sie findet).
Source: "{#RepoDir}\THIRD_PARTY_NOTICES.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#RepoDir}\licenses\*"; DestDir: "{app}\licenses"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\LightOS"; Filename: "{app}\LightOS.exe"; WorkingDir: "{app}"
Name: "{autoprograms}\LightOS deinstallieren"; Filename: "{uninstallexe}"
Name: "{autodesktop}\LightOS"; Filename: "{app}\LightOS.exe"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\LightOS.exe"; Description: "{cm:LaunchProgram,LightOS}"; Flags: nowait postinstall skipifsilent
