; Embedded Anki fork installer. Build only on an authorized Windows runner.
; Do not execute Setup.exe from CI. Personal data is never an installer input.
#ifndef MyAppVersion
  #error MyAppVersion must be passed by tools/build_setup.py
#endif
#ifndef BundleDir
  #error BundleDir must be passed by tools/build_setup.py
#endif
#ifndef RepoRoot
  #error RepoRoot must be passed by tools/build_setup.py
#endif
#ifndef InstallerIcon
  #error InstallerIcon must be passed by tools/build_setup.py
#endif
#ifndef InstallerOutput
  #error InstallerOutput must be passed by tools/build_setup.py
#endif

[Setup]
AppId={{CBFBCAC8-BA5D-46C1-90A9-A3CB3568AFAC}
AppName=DeskCal with Anki
AppVersion={#MyAppVersion}
AppVerName=DeskCal with Anki {#MyAppVersion}
AppPublisher=Z3O1
AppPublisherURL=https://github.com/Z3O1/DeskCal
AppSupportURL=https://github.com/Z3O1/DeskCal/issues
AppUpdatesURL=https://github.com/Z3O1/DeskCal/releases
DefaultDirName={localappdata}\Programs\DeskCal-Anki
DefaultGroupName=DeskCal - Anki
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
UsePreviousAppDir=yes
UsePreviousTasks=yes
DisableProgramGroupPage=yes
DirExistsWarning=no
WizardStyle=modern
LicenseFile={#RepoRoot}\COPYING
InfoBeforeFile={#RepoRoot}\tools\installer-notes.txt
OutputDir={#InstallerOutput}
OutputBaseFilename=DeskCal-{#MyAppVersion}-Setup
SetupIconFile={#InstallerIcon}
UninstallDisplayIcon={app}\DeskCal.exe
Compression=lzma2
SolidCompression=yes
AppMutex=DeskCal_single_instance
SetupMutex=DeskCal_Anki_Setup_CBFBCAC8_BA5D_46C1_90A9_A3CB3568AFAC
CloseApplications=no
RestartApplications=no

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"; Flags: unchecked

[Files]
Source: "{#BundleDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\DeskCal - Anki"; Filename: "{app}\DeskCal.exe"; WorkingDir: "{app}"; IconFilename: "{app}\DeskCal.exe"
Name: "{autodesktop}\DeskCal with Anki"; Filename: "{app}\DeskCal.exe"; WorkingDir: "{app}"; IconFilename: "{app}\DeskCal.exe"; Tasks: desktopicon

; No [Run], [InstallDelete] or [UninstallDelete]: never auto-start/close the app,
; and never recursively remove its data junction or shared personal data folder.
[Code]
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  CurrentCommand, OwnCommand: String;
begin
  if CurUninstallStep = usUninstall then
  begin
    OwnCommand := '"' + ExpandConstant('{app}\DeskCal.exe') + '" --autostart';
    if RegQueryStringValue(HKCU, 'Software\Microsoft\Windows\CurrentVersion\Run', 'DeskCal', CurrentCommand) then
      if CompareText(CurrentCommand, OwnCommand) = 0 then
        RegDeleteValue(HKCU, 'Software\Microsoft\Windows\CurrentVersion\Run', 'DeskCal');
  end;
end;
