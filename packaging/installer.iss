; Installeur Windows (Inno Setup 6) : DofusPriceHelper-Setup-vX.Y.Z.exe
; ---------------------------------------------------------------------
; Construit APRÈS packaging/build.py (qui crée dist/DofusPriceHelper et build/logo.ico) :
;   iscc /DAppVersion=v1.6.1 /DNumVersion=1.6.1 packaging\installer.iss
; Installe dans le dossier de l'utilisateur (%LOCALAPPDATA%\Programs) : pas besoin des droits
; administrateur, et la mise à jour en un clic de l'outil peut remplacer ses fichiers.
; Les réglages (%APPDATA%\Dofus Price Helper) ne sont jamais touchés, même à la désinstallation.

#ifndef AppVersion
  #define AppVersion "dev"
#endif
; Propriétés du fichier : chiffres seulement (1.6.1)
#ifndef NumVersion
  #define NumVersion "0.0.0"
#endif
#define AppName "Dofus Price Helper"
#define AppExe "DofusPriceHelper.exe"
#define Root AddBackslash(SourcePath) + ".."

[Setup]
; Identifiant fixe : ne jamais le changer (sinon Windows voit une autre application)
AppId={{6E03D591-AAFD-4052-AAE6-9FE7BBB6779E}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
VersionInfoVersion={#NumVersion}
AppPublisher=Jul1111
AppPublisherURL=https://github.com/Jul1111/Auto-Dofus-Price-Update
AppSupportURL=https://github.com/Jul1111/Auto-Dofus-Price-Update/discussions
AppUpdatesURL=https://github.com/Jul1111/Auto-Dofus-Price-Update/releases/latest
DefaultDirName={localappdata}\Programs\DofusPriceHelper
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir={#Root}\dist
OutputBaseFilename=DofusPriceHelper-Setup-{#AppVersion}
SetupIconFile={#Root}\build\logo.ico
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
LicenseFile={#Root}\LICENSE
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
; L'outil ouvert (verrou « un seul exemplaire ») : l'installeur demande de le fermer
AppMutex=Local\DofusPriceHelper-instance
CloseApplications=yes

[Languages]
Name: "fr"; MessagesFile: "compiler:Languages\French.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "{#Root}\dist\DofusPriceHelper\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[InstallDelete]
; Restes d'une mise à jour interrompue
Type: filesandordirs; Name: "{app}\_internal.old"

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{group}\Lisez-moi"; Filename: "{app}\LISEZ-MOI.txt"
Name: "{group}\{cm:UninstallProgram,{#AppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Fichiers créés par l'outil à côté de l'exe (les réglages, eux, sont dans %APPDATA%)
Type: filesandordirs; Name: "{app}\_internal.old"
