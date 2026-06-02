param(
    [int]$Port = 18116,
    [switch]$SkipDockerStart
)

$ErrorActionPreference = "Stop"

function Test-DockerReady {
    $previous = $ErrorActionPreference
    $ErrorActionPreference = "SilentlyContinue"
    try {
        docker info *> $null
        return $LASTEXITCODE -eq 0
    } catch {
        return $false
    } finally {
        $ErrorActionPreference = $previous
    }
}

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "Docker CLI not found. Install/start Docker Desktop, then rerun this script."
}

if (-not (Test-DockerReady)) {
    throw "Docker daemon is not running. Start Docker Desktop and wait until 'docker info' works."
}

if (-not $SkipDockerStart) {
    docker compose --profile optional-kafka --profile optional-persistent up -d kafka postgres
}

$env:IRX_BIGDATA_KAFKA_ENABLED = "true"
$env:IRX_BIGDATA_KAFKA_FALLBACK_TO_LOCAL = "true"
$env:IRX_STREAMING_ENABLED = "false"
$env:IRX_KAFKA_BOOTSTRAP_SERVERS = "localhost:9092"
$env:IRX_BIGDATA_POSTGRES_ENABLED = "true"
$env:IRX_BIGDATA_POSTGRES_URL = "jdbc:postgresql://localhost:5432/irx"
$env:IRX_BIGDATA_POSTGRES_USER = "irx"
$env:IRX_BIGDATA_POSTGRES_PASSWORD = "irx"
$env:IRX_BIGDATA_CHUNK_SIZE = "100"
$env:IRX_BIGDATA_WORKER_COUNT = "2"
$env:IRX_BIGDATA_CORE_ENABLED = "true"
$env:IRX_BIGDATA_CORE_MAX_ORDERS_PER_CHUNK = "1000"
$env:IRX_BIGDATA_SYNTHETIC_DRIVER_COUNT = "500"
$env:IRX_BIGDATA_CORE_TIMEOUT_MS = "5000"

Write-Host "Starting IRX API on port $Port with Kafka + Postgres enabled..."
.\gradlew.bat bootRun --args="--server.port=$Port" --no-daemon --console=plain
