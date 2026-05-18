param(
  [string]$OutputDir = "artifacts/test-reports/docs-rewrite"
)
$ErrorActionPreference = "Stop"
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
$required = @(
  "README.md",
  "docs/README.md",
  "docs/SYSTEM_OVERVIEW.md",
  "docs/ARCHITECTURE.md",
  "docs/API_REFERENCE.md",
  "docs/API_EXAMPLES.md",
  "docs/BIGDATA_LITE_API.md",
  "docs/ADAPTIVE_ML_POLICY.md",
  "docs/BENCHMARKS.md",
  "docs/OPERATIONS.md",
  "docs/PLAYGROUND.md",
  "docs/RELEASE.md",
  "docs/THESIS_GUIDE.md",
  "docs/openapi/irx-api-v1.yaml"
)
$legacy = @(
  "docs/IRX_FINAL_SYSTEM_STATUS.md",
  "docs/IRX_FINAL_CERTIFICATION_REPORT.md",
  "docs/IRX_BENCHMARK_METHODOLOGY.md",
  "docs/IRX_QUALITY_BENCHMARK_REPORT.md",
  "docs/IRX_OPERATIONS_DEMO_GUIDE.md",
  "docs/IRX_REPRODUCIBILITY_GUIDE.md",
  "docs/production/rest_dispatch_api.md",
  "docs/benchmark",
  "docs/production"
)
$banned = @(
  "ML replaces VROOM",
  "production distributed big data",
  "guaranteed best route",
  "native exe completed",
  "FAST distance is production benchmark"
)
function Assert($condition, $message){ if(-not $condition){ throw $message } }
function ContainsAll($path, [string[]]$needles){ $text=Get-Content $path -Raw; foreach($n in $needles){ Assert ($text -match [regex]::Escape($n)) "$path missing $n" } }

foreach($path in $required){ Assert (Test-Path $path) "required doc missing: $path" }
foreach($path in $legacy){ Assert (-not (Test-Path $path)) "legacy doc still present: $path" }

ContainsAll "docs/API_REFERENCE.md" @("/jobs", "/static/dispatch", "/live/start", "/rescue/jobs", "/bigdata/batches", "/artifacts", "/events", "/metrics", "Idempotency", "Error envelope")
ContainsAll "docs/BIGDATA_LITE_API.md" @("Batch ingest", "Queue", "backpressure", "Dead-letter", "Pagination", "Limitations")
ContainsAll "docs/ADAPTIVE_ML_POLICY.md" @("does not replace VROOM/PyVRP", "QUALITY_SEEKING", "TOP_K_ASSISTED", "0", "Limitations")
ContainsAll "docs/BENCHMARKS.md" @("7/7", "20/20", "1.6 km", "artifact", "Limitations")
ContainsAll "docs/OPERATIONS.md" @("irx.ps1 up", "irx.ps1 status", "irx.ps1 test -Quick", "irx.ps1 down", "irx.ps1 package")
ContainsAll "docs/PLAYGROUND.md" @("/playground", "static", "live", "rescue", "BigData", "raw JSON")
ContainsAll "docs/RELEASE.md" @("zip", "not committed", "irx.ps1 package")
ContainsAll "docs/THESIS_GUIDE.md" @("Java", "Adaptive ML", "BigData-lite", "Testing")

$allDocText = (Get-ChildItem README.md,docs -Recurse -File -Include *.md,*.yaml | ForEach-Object { Get-Content $_.FullName -Raw }) -join "`n"
foreach($phrase in $banned){ Assert ($allDocText -notmatch [regex]::Escape($phrase)) "banned overclaim phrase found: $phrase" }

$markdownFiles = Get-ChildItem README.md,docs -Recurse -File -Include *.md
$broken = @()
foreach($file in $markdownFiles){
  $text = Get-Content $file.FullName -Raw
  $matches = [regex]::Matches($text, '\[[^\]]+\]\(([^)]+)\)')
  foreach($match in $matches){
    $link = $match.Groups[1].Value
    if($link -match '^(http|https|mailto):'){ continue }
    if($link.StartsWith('#')){ continue }
    $clean = ($link -split '#')[0]
    if([string]::IsNullOrWhiteSpace($clean)){ continue }
    $target = Join-Path $file.DirectoryName $clean
    if(-not (Test-Path $target)){ $broken += "$($file.FullName) -> $link" }
  }
}
Assert ($broken.Count -eq 0) ("broken relative links: " + ($broken -join '; '))

$summary = [ordered]@{
  version = "v0.9.9.7-production-docs-rewrite"
  overallPass = $true
  requiredDocs = "PASS"
  legacyDocsRemoved = "PASS"
  legacyDocDirsRemoved = "PASS"
  apiReference = "PASS"
  bigDataLite = "PASS"
  adaptiveMlPolicy = "PASS"
  benchmarks = "PASS"
  operations = "PASS"
  playground = "PASS"
  release = "PASS"
  thesisGuide = "PASS"
  brokenLinks = 0
  bannedOverclaimPhrases = 0
}
$path = Join-Path $OutputDir "docs-gate-summary.json"
$summary | ConvertTo-Json -Depth 20 | Set-Content $path
Write-Output "SUMMARY=$path"
