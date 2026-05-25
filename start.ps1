# LightOS Start-Script (PowerShell)
# Funktioniert auf Windows x64, ARM64 und in Linux PowerShell Core (pwsh)

Set-Location -Path $PSScriptRoot

# Architektur erkennen (nur Info)
$arch = [System.Runtime.InteropServices.RuntimeInformation]::OSArchitecture
Write-Host "[start] Arch: $arch"

# venv-Python suchen (Windows-Pfad ODER Unix-Pfad)
$pythonPaths = @(
    "venv\Scripts\python.exe",   # Windows
    "venv/bin/python",           # Linux/macOS
    "venv/bin/python3"
)

$python = $null
foreach ($p in $pythonPaths) {
    if (Test-Path $p) {
        $python = $p
        break
    }
}

if (-not $python) {
    Write-Host "[start] Kein venv gefunden - nutze System-Python"
    $python = "python"
}

Write-Host "[start] Verwende Python: $python"

# Starten - Argumente weiterreichen
& $python main.py @args
