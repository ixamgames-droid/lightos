# LightOS Start-Script (PowerShell)
# Funktioniert auf Windows x64, ARM64 und in Linux PowerShell Core (pwsh)

Set-Location -Path $PSScriptRoot

# Architektur erkennen (zuverlaessig, auch unter ARM64-Emulation)
# XPLAT-57: In einer interaktiven Windows PowerShell 5.1 ist PSReadLine 2.0
# geladen. Dessen DLL bringt einen eigenen Typ gleichen Namens OHNE
# OSArchitecture mit, und der Kurzname loest dann auf ihn auf: beide Werte waren
# leer, und die ARM64-Warnung unten fiel aus. Deshalb unter Windows PowerShell
# den Typ ausdruecklich aus mscorlib holen (dort ab .NET Framework 4.7.1).
$ri = $null
if ($PSVersionTable.PSEdition -ne "Core") {
    $ri = [Type]::GetType("System.Runtime.InteropServices.RuntimeInformation, mscorlib")
}
if (-not $ri) { $ri = [System.Runtime.InteropServices.RuntimeInformation] }
$osArch = $ri::OSArchitecture
$procArch = $ri::ProcessArchitecture
# Rueckfall wie in start.bat: PROCESSOR_IDENTIFIER zeigt auf ARM-Hardware stets
# "ARMv8", auch unter Emulation.
if (-not $osArch -and $env:OS -eq "Windows_NT" -and "$env:PROCESSOR_IDENTIFIER" -match "ARMv8") {
    $osArch = "Arm64"
}
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
# Emulation, alles geht) - dazu kommt kein Hinweis. Natives ARM64-Python ist
# nicht unterstuetzt: kein QtWebEngine und damit kein 3D-Visualizer
# (XPLAT-45/46), und LightOS stuerzte damit in 6 von 12 Starts ab (XPLAT-51).
# Gestartet wird trotzdem. Gefragt wird das Python, das main.py startet - nicht
# die Shell.
if ($osArch -eq "Arm64" -and $env:OS -eq "Windows_NT") {
    $pyPlattform = ""
    try { $pyPlattform = (& $python -c "import sysconfig; print(sysconfig.get_platform())" 2>$null) } catch { }
    if ("$pyPlattform".Trim() -eq "win-arm64") {
        Write-Host "[start] WARNUNG: natives ARM64-Python ist nicht unterstuetzt (instabil, kein 3D) - x64-Python nehmen: winget install Python.Python.3.12 --architecture x64, Details in INSTALL.md." -ForegroundColor Yellow
    }
}

# Starten - Argumente weiterreichen
& $python main.py @args
