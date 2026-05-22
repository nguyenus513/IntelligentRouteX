$ErrorActionPreference = "Stop"
$image = if ($env:VROOM_DOCKER_IMAGE) { $env:VROOM_DOCKER_IMAGE } else { "vroomvrp/vroom-docker:v1.14.0-rc.2" }

function Require-Docker {
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        throw "Docker CLI is required for VROOM Docker wrapper. Install Docker Desktop or run start.bat -InstallDeps."
    }
    docker info *> $null
    if ($LASTEXITCODE -ne 0) {
        throw "Docker Desktop is not running. Start Docker Desktop and retry."
    }
}

function Convert-ToContainerArg([string]$arg, [System.Collections.Generic.HashSet[string]]$mounts) {
    if (-not $arg) { return $arg }
    $candidate = $arg
    if ($candidate -match '^[A-Za-z]:[\\/]') {
        $full = [System.IO.Path]::GetFullPath($candidate)
    } elseif ($candidate -match '[\\/]' -and -not [System.IO.Path]::IsPathRooted($candidate)) {
        $full = [System.IO.Path]::GetFullPath((Join-Path (Get-Location) $candidate))
    } else {
        return $arg
    }
    $parent = Split-Path -Parent $full
    if (-not $parent) { return $arg }
    [void]$mounts.Add($parent)
    return "/work/" + (Split-Path -Leaf $full)
}

Require-Docker

$VroomArgs = @($args)

if ($VroomArgs.Count -eq 0 -or ($VroomArgs.Count -eq 1 -and $VroomArgs[0] -eq "--version")) {
    docker run --rm --entrypoint vroom $image --version
    exit $LASTEXITCODE
}

$mounts = [System.Collections.Generic.HashSet[string]]::new([System.StringComparer]::OrdinalIgnoreCase)
$converted = New-Object System.Collections.Generic.List[string]
foreach ($arg in $VroomArgs) {
    $converted.Add((Convert-ToContainerArg $arg $mounts))
}

$dockerArgs = New-Object System.Collections.Generic.List[string]
$dockerArgs.Add("run")
$dockerArgs.Add("--rm")
foreach ($mount in $mounts) {
    $dockerArgs.Add("-v")
    $dockerArgs.Add("${mount}:/work")
}
$dockerArgs.Add("--entrypoint")
$dockerArgs.Add("vroom")
$dockerArgs.Add($image)
foreach ($arg in $converted) { $dockerArgs.Add($arg) }

& docker @dockerArgs
exit $LASTEXITCODE
