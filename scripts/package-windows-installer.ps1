param(
    [string]$BundleDir = "build/release/windows-portable/irx-portable-windows-x64",
    [string]$ReleaseDir = "build/release",
    [string]$AppName = "IRX Control Tower"
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$BundlePath = Join-Path $Root $BundleDir
$ReleasePath = Join-Path $Root $ReleaseDir
New-Item -ItemType Directory -Force -Path $ReleasePath | Out-Null
if (-not (Test-Path $BundlePath)) { throw "Portable bundle missing: $BundlePath. Run scripts/package-windows-portable.ps1 first." }

$iscc = Get-Command iscc.exe -ErrorAction SilentlyContinue
if ($iscc) {
    $iss = Join-Path $ReleasePath "irx-installer.iss"
    @"
[Setup]
AppName=$AppName
AppVersion=1.0.0
DefaultDirName={localappdata}\IntelligentRouteX
DefaultGroupName=$AppName
OutputDir=$ReleasePath
OutputBaseFilename=IRX-ControlTower-Setup
Compression=lzma2
SolidCompression=yes

[Files]
Source: "$BundlePath\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs

[Icons]
Name: "{group}\$AppName"; Filename: "{app}\start-irx.bat"; WorkingDir: "{app}"
Name: "{commondesktop}\$AppName"; Filename: "{app}\start-irx.bat"; WorkingDir: "{app}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create desktop shortcut"; GroupDescription: "Additional icons:"

[Run]
Filename: "{app}\start-irx.bat"; Description: "Launch $AppName"; Flags: postinstall skipifsilent nowait
"@ | Set-Content -Encoding UTF8 $iss
    & $iscc.Source $iss
    if ($LASTEXITCODE -ne 0) { throw "Inno Setup build failed." }
    Write-Host "INSTALLER=$(Join-Path $ReleasePath 'IRX-ControlTower-Setup.exe')"
    exit 0
}

$sevenZip = Get-Command 7z.exe -ErrorAction SilentlyContinue
if ($sevenZip) {
    $archive = Join-Path $ReleasePath "IRX-ControlTower-Portable.7z"
    $exe = Join-Path $ReleasePath "IRX-ControlTower-Portable.exe"
    if (Test-Path $archive) { Remove-Item -Force $archive }
    if (Test-Path $exe) { Remove-Item -Force $exe }
    & $sevenZip.Source a -t7z $archive (Join-Path $BundlePath "*") -mx=7
    if ($LASTEXITCODE -ne 0) { throw "7z archive build failed." }
    Copy-Item -Force $archive $exe
    Write-Host "PORTABLE_EXE=$exe"
    exit 0
}

throw "Neither Inno Setup (iscc.exe) nor 7z.exe found. Portable zip is still available; install Inno Setup for Setup.exe."
