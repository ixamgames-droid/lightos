# LightOS Start-Script (PowerShell)
# Funktioniert auf Windows x64, ARM64 und in Linux PowerShell Core (pwsh)

Set-Location -Path $PSScriptRoot

# Architektur erkennen (zuverlaessig, auch unter ARM64-Emulation)
$osArch = [System.Runtime.InteropServices.RuntimeInformation]::OSArchitecture
$procArch = [System.Runtime.InteropServices.RuntimeInformation]::ProcessArchitecture
Write-Host "[start] OS-Arch: $osArch | Prozess-Arch: $procArch"

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

# XPLAT-50: Auf Windows-ARM ist x64-Python der empfohlene Weg (laeuft per
# Emulation, alles geht) - dazu kommt kein Hinweis. Natives ARM64-Python hat
# kein QtWebEngine und damit keinen 3D-Visualizer (XPLAT-45/46). Gefragt wird
# das Python, das main.py startet - nicht die Shell.
if ($osArch -eq "Arm64" -and $env:OS -eq "Windows_NT") {
    $pyPlattform = ""
    try { $pyPlattform = (& $python -c "import sysconfig; print(sysconfig.get_platform())" 2>$null) } catch { }
    if ("$pyPlattform".Trim() -eq "win-arm64") {
        Write-Host "[start] HINWEIS: natives ARM64-Python - LightOS laeuft ohne 3D-Visualizer. x64-Python empfohlen (winget install Python.Python.3.12 --architecture x64), Details in INSTALL.md."
    }
}

# Starten - Argumente weiterreichen
& $python main.py @args
