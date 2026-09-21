; RhinoSpotter standalone. Built by installer/build.py, which passes
; Version, Icon and Source (the PyInstaller folder) with /D.
; Per-user install: no admin, %LOCALAPPDATA%\Programs\RhinoSpotter.
; Data stays in %LOCALAPPDATA%\RhinoSpotter, shared with the EDMC plugin,
; and is not removed by the uninstaller.

[Setup]
AppId={{5B7C1E2A-9D4F-4E6B-8A3C-2F1D7E9B4C60}
AppName=RhinoSpotter
AppVersion={#Version}
AppPublisher=Fumlop
AppPublisherURL=https://github.com/Fumlop/EDRhinoSpotter
DefaultDirName={localappdata}\Programs\RhinoSpotter
DefaultGroupName=RhinoSpotter
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputBaseFilename=RhinoSpotter-{#Version}-Setup
SetupIconFile={#Icon}
UninstallDisplayIcon={app}\RhinoSpotter.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
LicenseFile=..\LICENSE

[Tasks]
Name: "desktopicon"; Description: "Desktop shortcut"; Flags: unchecked

[InstallDelete]
; An upgrade: the previous build's bundle, so no stale module outlives it.
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "{#Source}\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{group}\RhinoSpotter"; Filename: "{app}\RhinoSpotter.exe"
Name: "{userdesktop}\RhinoSpotter"; Filename: "{app}\RhinoSpotter.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\RhinoSpotter.exe"; Description: "Start RhinoSpotter"; Flags: nowait postinstall skipifsilent
