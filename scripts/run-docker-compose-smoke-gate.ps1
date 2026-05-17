param([string]$OutputDir="artifacts/test-reports/v0.9.9.2-production-runtime/docker")
$ErrorActionPreference="Stop"; New-Item -ItemType Directory -Force -Path $OutputDir|Out-Null
$files=@("docker-compose.yml","Dockerfile.backend","dashboard/Dockerfile",".env.example")
$pass=($files|Where-Object{Test-Path $_}).Count -eq $files.Count
$summary=[pscustomobject]@{gate="docker-compose-smoke";overallPass=$pass;mode="file-level-smoke";files=$files}
$path=Join-Path $OutputDir "docker-compose-smoke-summary.json"; $summary|ConvertTo-Json -Depth 10|Set-Content $path; Write-Output "SUMMARY=$path"; if(-not $pass){exit 1}
