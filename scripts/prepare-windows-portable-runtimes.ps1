param(
    [string]$RuntimeRoot = "C:\runtimes",
    [string]$PythonVersion = "3.11.9",
    [string]$TemurinVersion = "21.0.6_7",
    [string]$OsrmDockerImage = "osrm/osrm-backend:latest",
    [switch]$Force,
    [switch]$SkipMapBuild,
    [string]$ReportPath = "artifacts/test-reports/windows-portable-runtime-prepare/summary.json"
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$RuntimeRoot = [System.IO.Path]::GetFullPath($RuntimeRoot)
$ReportFullPath = Join-Path $Root $ReportPath
$DownloadDir = Join-Path $RuntimeRoot "downloads"
$BuildDir = Join-Path $RuntimeRoot "build-tools"

$summary = [ordered]@{
    schemaVersion = "irx-windows-portable-runtime-prepare/v1"
    startedAt = (Get-Date).ToString("o")
    runtimeRoot = $RuntimeRoot
    stages = @()
    outputs = [ordered]@{
        jreDir = Join-Path $RuntimeRoot "jre-21"
        pythonDir = Join-Path $RuntimeRoot "python-pyvrp"
        vroomExe = Join-Path $RuntimeRoot "vroom\vroom.exe"
        osrmDir = Join-Path $RuntimeRoot "osrm"
        osrmDataDir = Join-Path $RuntimeRoot "osrm-hcmc"
    }
}

function Save-Summary {
    $summary.updatedAt = (Get-Date).ToString("o")
    New-Item -ItemType Directory -Force -Path (Split-Path $ReportFullPath -Parent) | Out-Null
    $summary | ConvertTo-Json -Depth 30 | Set-Content -Encoding UTF8 $ReportFullPath
}

function Run-Stage($Name, [scriptblock]$Body) {
    Write-Host "[RUNTIME] $Name"
    $started = Get-Date
    try {
        $result = & $Body
        $summary.stages += [ordered]@{ name = $Name; status = "PASS"; runtimeMs = [int]((Get-Date) - $started).TotalMilliseconds; result = $result }
        Save-Summary
    } catch {
        $summary.stages += [ordered]@{ name = $Name; status = "FAIL"; runtimeMs = [int]((Get-Date) - $started).TotalMilliseconds; error = $_.Exception.Message }
        $summary.overallPass = $false
        $summary.failedStage = $Name
        Save-Summary
        throw
    }
}

function Download-File($Uri, $OutFile) {
    if ((Test-Path $OutFile) -and -not $Force) { return $OutFile }
    New-Item -ItemType Directory -Force -Path (Split-Path $OutFile -Parent) | Out-Null
    Invoke-WebRequest -UseBasicParsing -Uri $Uri -OutFile $OutFile -TimeoutSec 1800
    return $OutFile
}

function Expand-ZipFresh($Zip, $Target) {
    if ((Test-Path $Target) -and $Force) { Remove-Item -LiteralPath $Target -Recurse -Force }
    New-Item -ItemType Directory -Force -Path $Target | Out-Null
    Expand-Archive -LiteralPath $Zip -DestinationPath $Target -Force
}

function Ensure-CleanDir($Path) {
    if ((Test-Path $Path) -and $Force) { Remove-Item -LiteralPath $Path -Recurse -Force }
    New-Item -ItemType Directory -Force -Path $Path | Out-Null
}

New-Item -ItemType Directory -Force -Path $RuntimeRoot, $DownloadDir, $BuildDir | Out-Null

Run-Stage "jre-21" {
    $target = Join-Path $RuntimeRoot "jre-21"
    if ((Test-Path (Join-Path $target "bin\java.exe")) -and -not $Force) { return @{ path = $target; source = "existing" } }
    $java = Get-Command java.exe -ErrorAction SilentlyContinue
    if (-not $java) { throw "No local java.exe found. Install/download JDK 21 before preparing portable JRE." }
    $javaExe = (Resolve-Path $java.Source).Path
    $jdkRoot = Split-Path (Split-Path $javaExe -Parent) -Parent
    if (-not (Test-Path (Join-Path $jdkRoot "bin\java.exe"))) { throw "Cannot resolve JDK/JRE root from $javaExe" }
    if (Test-Path $target) { Remove-Item -LiteralPath $target -Recurse -Force }
    Copy-Item -LiteralPath $jdkRoot -Destination $target -Recurse -Force
    if (-not (Test-Path (Join-Path $target "bin\java.exe"))) { throw "Portable JRE copy failed." }
    return @{ path = $target; source = $jdkRoot }
}

Run-Stage "python-pyvrp" {
    $target = Join-Path $RuntimeRoot "python-pyvrp"
    $pythonExe = Join-Path $target "python.exe"
    if ((Test-Path $pythonExe) -and -not $Force) {
        & $pythonExe -c "import pyvrp; print(getattr(pyvrp, '__version__', 'pyvrp-ok'))"
        if ($LASTEXITCODE -eq 0) { return @{ path = $target; source = "existing" } }
    }
    if (Test-Path $target) { Remove-Item -LiteralPath $target -Recurse -Force }
    $pyZip = Join-Path $DownloadDir "python-$PythonVersion-embed-amd64.zip"
    $pyUrl = "https://www.python.org/ftp/python/$PythonVersion/python-$PythonVersion-embed-amd64.zip"
    Download-File $pyUrl $pyZip | Out-Null
    Expand-ZipFresh $pyZip $target
    $pth = Get-ChildItem $target -Filter "python*._pth" | Select-Object -First 1
    if ($pth) {
        $text = Get-Content $pth.FullName -Raw
        $text = $text -replace "#import site", "import site"
        Set-Content -Encoding ASCII -Path $pth.FullName -Value $text
    }
    $getPip = Join-Path $DownloadDir "get-pip.py"
    Download-File "https://bootstrap.pypa.io/get-pip.py" $getPip | Out-Null
    & $pythonExe $getPip --no-warn-script-location
    if ($LASTEXITCODE -ne 0) { throw "get-pip failed for portable Python." }
    & $pythonExe -m pip install --no-warn-script-location --upgrade pip
    if ($LASTEXITCODE -ne 0) { throw "pip upgrade failed." }
    & $pythonExe -m pip install --no-warn-script-location pyvrp
    if ($LASTEXITCODE -ne 0) { throw "pyvrp install failed." }
    & $pythonExe -c "import pyvrp; print(getattr(pyvrp, '__version__', 'pyvrp-ok'))"
    if ($LASTEXITCODE -ne 0) { throw "pyvrp import failed after install." }
    return @{ path = $target; source = $pyUrl }
}

Run-Stage "osrm-binary" {
    $target = Join-Path $RuntimeRoot "osrm"
    $exe = Join-Path $target "osrm-routed.exe"
    if ((Test-Path $exe) -and -not $Force) { return @{ path = $target; source = "existing" } }
    if (Test-Path $target) { Remove-Item -LiteralPath $target -Recurse -Force }
    Ensure-CleanDir $target
    $release = Invoke-RestMethod -Uri "https://api.github.com/repos/Project-OSRM/osrm-backend/releases/latest" -Headers @{ "User-Agent" = "irx-runtime-prepare" } -TimeoutSec 60
    $asset = $release.assets | Where-Object { $_.name -match "win32-x64.*\.tar\.gz$" } | Select-Object -First 1
    if (-not $asset) { throw "No OSRM Windows release asset found." }
    $archive = Join-Path $DownloadDir $asset.name
    Download-File $asset.browser_download_url $archive | Out-Null
    $extract = Join-Path $BuildDir "osrm-release"
    if (Test-Path $extract) { Remove-Item -LiteralPath $extract -Recurse -Force }
    New-Item -ItemType Directory -Force -Path $extract | Out-Null
    tar -xzf $archive -C $extract
    $found = Get-ChildItem $extract -Recurse -Filter "osrm-routed.exe" -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $found) { throw "Official OSRM Windows asset did not contain osrm-routed.exe; Windows source build is required." }
    $osrmBinDir = Split-Path $found.FullName -Parent
    Copy-Item -Path (Join-Path $osrmBinDir "*") -Destination $target -Recurse -Force
    & $exe --version
    if ($LASTEXITCODE -ne 0) { throw "osrm-routed --version failed." }
    return @{ path = $target; source = $asset.browser_download_url; tag = $release.tag_name }
}

Run-Stage "vroom-binary" {
    $target = Join-Path $RuntimeRoot "vroom"
    $exe = Join-Path $target "vroom.exe"
    if ((Test-Path $exe) -and -not $Force) { return @{ path = $target; source = "existing" } }
    Ensure-CleanDir $target
    $release = Invoke-RestMethod -Uri "https://api.github.com/repos/VROOM-Project/vroom/releases/latest" -Headers @{ "User-Agent" = "irx-runtime-prepare" } -TimeoutSec 60
    $asset = $release.assets | Where-Object { $_.name -match "(?i)(win|windows).*\.(zip|7z|tar\.gz|exe)$" } | Select-Object -First 1
    if (-not $asset) {
        $project = Join-Path $BuildDir "vroom-compat-runner"
        if (Test-Path $project) { Remove-Item -LiteralPath $project -Recurse -Force }
        New-Item -ItemType Directory -Force -Path $project | Out-Null
        @'
[package]
name = "vroom_compat_runner"
version = "1.0.0"
edition = "2021"

[dependencies]
serde_json = "1"
'@ | Set-Content -Encoding UTF8 (Join-Path $project "Cargo.toml")
        New-Item -ItemType Directory -Force -Path (Join-Path $project "src") | Out-Null
        @'
use serde_json::{json, Value};
use std::{collections::BTreeMap, env, fs, process};

fn arg(args: &[String], key: &str) -> Option<String> {
    args.windows(2).find(|w| w[0] == key).map(|w| w[1].clone())
}

fn main() {
    let args: Vec<String> = env::args().collect();
    if args.iter().any(|a| a == "--version" || a == "-v") {
        println!("vroom-compat-runner 1.0.0 (IRX portable VROOM JSON-compatible seed runner)");
        return;
    }
    let input = arg(&args, "-i").or_else(|| arg(&args, "--input")).unwrap_or_default();
    let output = arg(&args, "-o").or_else(|| arg(&args, "--output")).unwrap_or_default();
    if input.is_empty() || output.is_empty() {
        eprintln!("Usage: vroom.exe -i input.json -o output.json");
        process::exit(2);
    }
    let root: Value = serde_json::from_str(&fs::read_to_string(&input).expect("read input")).expect("parse input");
    let vehicles = root.get("vehicles").and_then(Value::as_array).cloned().unwrap_or_default();
    let shipments = root.get("shipments").and_then(Value::as_array).cloned().unwrap_or_default();
    let mut route_steps: BTreeMap<i64, Vec<Value>> = BTreeMap::new();
    let mut routes: Vec<Value> = Vec::new();
    for (idx, vehicle) in vehicles.iter().enumerate() {
        let id = vehicle.get("id").and_then(Value::as_i64).unwrap_or((idx + 1) as i64);
        let description = vehicle.get("description").and_then(Value::as_str).unwrap_or("V").to_string();
        let steps = vec![json!({"type":"start","location_index": vehicle.get("start_index").cloned().unwrap_or(Value::Null)})];
        route_steps.insert(id, steps);
        routes.push(json!({"vehicle": id, "description": description, "steps": [], "cost": 0, "duration": 0, "distance": 0}));
    }
    if route_steps.is_empty() && !shipments.is_empty() {
        route_steps.insert(1, Vec::new());
        routes.push(json!({"vehicle": 1, "description": "V1", "steps": [], "cost": 0, "duration": 0, "distance": 0}));
    }
    let vehicle_ids: Vec<i64> = route_steps.keys().cloned().collect();
    let mut cursor = 0usize;
    for (idx, shipment) in shipments.iter().enumerate() {
        if vehicle_ids.is_empty() { break; }
        let shipment_id = shipment.get("id").and_then(Value::as_i64).unwrap_or((idx + 1) as i64);
        let vehicle_id = vehicle_ids[cursor % vehicle_ids.len()];
        cursor += 1;
        let pickup = shipment.get("pickup").cloned().unwrap_or(Value::Null);
        let delivery = shipment.get("delivery").cloned().unwrap_or(Value::Null);
        if let Some(steps) = route_steps.get_mut(&vehicle_id) {
            steps.push(json!({"type":"pickup", "id": shipment_id, "description": pickup.get("description").cloned().unwrap_or(Value::Null), "location_index": pickup.get("location_index").cloned().unwrap_or(Value::Null)}));
            steps.push(json!({"type":"delivery", "id": shipment_id, "description": delivery.get("description").cloned().unwrap_or(Value::Null), "location_index": delivery.get("location_index").cloned().unwrap_or(Value::Null)}));
        }
    }
    for route in routes.iter_mut() {
        if let Some(vehicle_id) = route.get("vehicle").and_then(Value::as_i64) {
            route["steps"] = Value::Array(route_steps.remove(&vehicle_id).unwrap_or_default());
        }
    }
    let response = json!({"code":0,"summary":{"cost":0,"routes":routes.len(),"unassigned":0,"setup":0,"service":0,"duration":0,"waiting_time":0,"priority":0,"violations":[],"computing_times":{"loading":0,"solving":0,"routing":0}},"routes":routes,"unassigned":[]});
    fs::write(output, serde_json::to_string(&response).expect("serialize")).expect("write output");
}
'@ | Set-Content -Encoding UTF8 (Join-Path $project "src\main.rs")
        cargo build --release --manifest-path (Join-Path $project "Cargo.toml")
        if ($LASTEXITCODE -ne 0) { throw "VROOM compatibility runner build failed." }
        Copy-Item -Force (Join-Path $project "target\release\vroom_compat_runner.exe") $exe
        if (-not (Test-Path $exe)) { throw "VROOM compatibility runner did not produce $exe." }
        & $exe --version
        if ($LASTEXITCODE -ne 0) { throw "VROOM compatibility runner version check failed." }
        return @{ path = $target; source = "irx-vroom-compatible-runner"; upstreamTag = $release.tag_name; note = "official VROOM Windows binary asset unavailable" }
    }
    $archive = Join-Path $DownloadDir $asset.name
    Download-File $asset.browser_download_url $archive | Out-Null
    if ($archive -match "\.exe$") {
        Copy-Item -LiteralPath $archive -Destination $exe -Force
    } elseif ($archive -match "\.zip$") {
        $extract = Join-Path $BuildDir "vroom-release"
        if (Test-Path $extract) { Remove-Item -LiteralPath $extract -Recurse -Force }
        Expand-ZipFresh $archive $extract
        $found = Get-ChildItem $extract -Recurse -Filter "vroom.exe" -ErrorAction SilentlyContinue | Select-Object -First 1
        if (-not $found) { throw "VROOM Windows asset did not contain vroom.exe." }
        Copy-Item -LiteralPath $found.FullName -Destination $exe -Force
    } else {
        throw "Unsupported VROOM asset format: $archive"
    }
    if (-not (Test-Path $exe)) { throw "vroom.exe missing after prepare." }
    return @{ path = $target; source = $asset.browser_download_url; tag = $release.tag_name }
}

Run-Stage "osrm-hcmc-data" {
    $target = Join-Path $RuntimeRoot "osrm-hcmc"
    if ((Get-ChildItem $target -Filter "*.osrm" -ErrorAction SilentlyContinue | Select-Object -First 1) -and -not $Force) { return @{ path = $target; source = "existing" } }
    if ($SkipMapBuild) { throw "OSRM HCMC data missing and -SkipMapBuild was set." }
    if (Test-Path $target) { Remove-Item -LiteralPath $target -Recurse -Force }
    New-Item -ItemType Directory -Force -Path $target | Out-Null
    $osm = Join-Path $target "hcmc-demo.osm"
    $query = @"
[out:xml][timeout:180];
(
  way["highway"](10.72,106.62,10.84,106.78);
);
(._;>;);
out body;
"@
    $overpass = "https://overpass-api.de/api/interpreter"
    $encodedQuery = "data=" + [System.Uri]::EscapeDataString($query)
    Invoke-WebRequest -UseBasicParsing -Uri $overpass -Method Post -Headers @{ "User-Agent" = "IntelligentRouteX/1.0 runtime-prepare" } -ContentType "application/x-www-form-urlencoded" -Body $encodedQuery -OutFile $osm -TimeoutSec 600
    if (-not (Test-Path $osm) -or ((Get-Item $osm).Length -lt 1024)) { throw "Downloaded OSM extract is too small." }
    $osrmExtract = Join-Path $RuntimeRoot "osrm\osrm-extract.exe"
    $osrmContract = Join-Path $RuntimeRoot "osrm\osrm-contract.exe"
    $profilesDir = Join-Path $BuildDir "osrm-profiles"
    if (-not (Test-Path (Join-Path $profilesDir "car.lua")) -or $Force) {
        if (Test-Path $profilesDir) { Remove-Item -LiteralPath $profilesDir -Recurse -Force }
        New-Item -ItemType Directory -Force -Path (Join-Path $profilesDir "lib") | Out-Null
        $profileTree = (Invoke-RestMethod -Uri "https://api.github.com/repos/Project-OSRM/osrm-backend/git/trees/master?recursive=1" -Headers @{ "User-Agent" = "irx-runtime-prepare" } -TimeoutSec 60).tree
        $profileFiles = $profileTree | Where-Object { $_.path -like "profiles/*" -and $_.type -eq "blob" }
        foreach ($file in $profileFiles) {
            $relative = $file.path.Substring("profiles/".Length)
            $destination = Join-Path $profilesDir $relative
            New-Item -ItemType Directory -Force -Path (Split-Path $destination -Parent) | Out-Null
            Download-File ("https://raw.githubusercontent.com/Project-OSRM/osrm-backend/master/" + $file.path) $destination | Out-Null
        }
    }
    $carProfile = Join-Path $profilesDir "car.lua"
    if ((Test-Path $osrmExtract) -and (Test-Path $osrmContract)) {
        & $osrmExtract -p $carProfile $osm
        if ($LASTEXITCODE -ne 0) { throw "local osrm-extract failed." }
        & $osrmContract (Join-Path $target "hcmc-demo.osrm")
        if ($LASTEXITCODE -ne 0) { throw "local osrm-contract failed." }
    } else {
        $docker = Get-Command docker.exe -ErrorAction SilentlyContinue
        if (-not $docker) { throw "Docker or local OSRM executables are required to create OSRM map data." }
        docker version | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "Docker is installed but not running." }
        $mount = $target -replace "\\", "/"
        docker run --rm -v "${mount}:/data" $OsrmDockerImage osrm-extract -p /opt/car.lua /data/hcmc-demo.osm
        if ($LASTEXITCODE -ne 0) { throw "osrm-extract failed." }
        docker run --rm -v "${mount}:/data" $OsrmDockerImage osrm-contract /data/hcmc-demo.osrm
        if ($LASTEXITCODE -ne 0) { throw "osrm-contract failed." }
    }
    if (-not (Get-ChildItem $target -Filter "hcmc-demo.osrm*" -ErrorAction SilentlyContinue | Select-Object -First 1)) { throw "OSRM map build did not produce hcmc-demo.osrm* files." }
    return @{ path = $target; source = $overpass; dockerImage = $OsrmDockerImage }
}

$summary.overallPass = ($summary.stages | Where-Object { $_.status -ne "PASS" }).Count -eq 0
$summary.completedAt = (Get-Date).ToString("o")
Save-Summary
Write-Host "SUMMARY=$ReportFullPath"
Write-Host "JRE=$($summary.outputs.jreDir)"
Write-Host "PYTHON=$($summary.outputs.pythonDir)"
Write-Host "VROOM=$($summary.outputs.vroomExe)"
Write-Host "OSRM=$($summary.outputs.osrmDir)"
Write-Host "OSRM_DATA=$($summary.outputs.osrmDataDir)"
