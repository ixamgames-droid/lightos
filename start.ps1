# LightOS Start-Script (PowerShell)
# Funktioniert auf Windows x64, ARM64 und in Linux PowerShell Core (pwsh)

Set-Location -Path $PSScriptRoot

# Architektur erkennen (zuverlaessig, auch unter ARM64-Emulation)
$osArch = [System.Runtime.InteropServices.RuntimeInformation]::OSArchitecture
$procArch = [System.Runtime.InteropServices.RuntimeInformation]::ProcessArchitecture
Write-Host "[start] OS-Arch: $osArch | Prozess-Arch: $procArch"

# Hinweis, wenn auf ARM64 ein emuliertes (nicht-ARM64) Python genutzt wird
if ($osArch -eq "Arm64" -and $procArch -ne "Arm64") {
    Write-Host "[start] WARN: Python laeuft emuliert ($procArch auf ARM64). Fuer beste Stabilitaet/Performance ARM64-Python nutzen (winget install Python.Python.3.13 --arch arm64)."
}

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
