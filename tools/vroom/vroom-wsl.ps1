$ErrorActionPreference = 'Stop'

$converted = New-Object System.Collections.Generic.List[string]
foreach ($arg in $args) {
    if ($arg -match '^[A-Za-z]:\\') {
        $converted.Add((wsl -d Ubuntu-24.04 -- wslpath -a -u $arg).Trim())
    } elseif ($arg -match '^[A-Za-z]:/') {
        $converted.Add((wsl -d Ubuntu-24.04 -- wslpath -a -u $arg).Trim())
    } elseif ($arg -match '^[^/].*\\') {
        $full = [System.IO.Path]::GetFullPath($arg)
        $converted.Add((wsl -d Ubuntu-24.04 -- wslpath -a -u $full).Trim())
    } else {
        $converted.Add($arg)
    }
}

& wsl -d Ubuntu-24.04 -- /opt/irx/vroom/bin/vroom @converted
exit $LASTEXITCODE
