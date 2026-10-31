"""XPLAT-59: Startskripte unter Windows - Warnung lesbar, Prozess-Arch im Rueckfall.

Befund von Sitzung B beim Gegentest zu XPLAT-57 (Windows 11 ARM, Windows
Terminal mit Farbschema Campbell):

1. Die Warnung vor nativem ARM64-Python (XPLAT-51) war in ``start.ps1``
   (``-ForegroundColor Yellow``) blassgelb und in ``start.bat`` gar nicht
   hervorgehoben - kaum von normalem Text zu unterscheiden. Jetzt Schwarz auf
   Gelb: in PowerShell per ``-BackgroundColor``, in cmd per ANSI-Folge. Die
   Folge ist dort sicher, weil der Zweig nur auf Windows-ARM laeuft (Windows 10
   1709 oder neuer, Konsole kann ANSI). Das ESC-Zeichen entsteht zur Laufzeit
   (``prompt $E``), beide Dateien bleiben reines ASCII.
2. Griff in ``start.ps1`` der Rueckfall ueber ``PROCESSOR_IDENTIFIER``, blieb
   ``$procArch`` leer und die Kopfzeile zeigte "Prozess-Arch: " ohne Wert.

Die Skripte laufen nur unter Windows; geprueft wird ihr Text.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _text(name: str) -> str:
    return (ROOT / name).read_bytes().decode("utf-8")


def _warnzeile(name: str) -> str:
    zeilen = [z for z in _text(name).splitlines()
              if "WARNUNG" in z and ("echo" in z or "Write-Host" in z)]
    assert len(zeilen) == 1, zeilen
    return zeilen[0]


class TestWarnungLesbar:
    def test_ps1_schwarz_auf_gelb(self):
        zeile = _warnzeile("start.ps1")
        assert re.search(r"-BackgroundColor\s+Yellow\b", zeile), zeile
        assert re.search(r"-ForegroundColor\s+Black\b", zeile), zeile

    def test_bat_hebt_per_ansi_hervor_und_setzt_zurueck(self):
        zeile = _warnzeile("start.bat").strip()
        assert zeile.startswith("echo %ESC%[30;43m[start] WARNUNG:"), zeile
        assert zeile.endswith("%ESC%[0m"), "Farbe muss am Zeilenende zurueck"

    def test_bat_erzeugt_esc_zur_laufzeit_nur_im_arm_zweig(self):
        text = _text("start.bat")
        m = re.search(r"""(?m)^for /F %%(\w) in \('echo prompt \$E\^\| cmd'\) do set "ESC=%%\1"\r?$""",
                      text)
        assert m, "ESC-Zeichen muss per prompt $E entstehen"
        assert text.index("ARMv8") < m.start() < text.index("echo %ESC%["), \
            "ESC erst im ARM-Zweig, vor der Warnung"
        # Die Warnung kommt nur bei Exit-Code genau 3 (win-arm64).
        zweig = text[text.index("if errorlevel 4 goto :arch_fertig"):m.start()]
        assert "if not errorlevel 3 goto :arch_fertig" in zweig

    def test_beide_bleiben_ascii(self):
        for name in ("start.bat", "start.ps1"):
            (ROOT / name).read_bytes().decode("ascii")


class TestProzessArchImRueckfall:
    def test_ps1_setzt_procarch_aus_der_umgebung(self):
        text = _text("start.ps1")
        m = re.search(r"if \(-not \$procArch[^\n]*\)\s*\{\s*\$procArch = \$env:PROCESSOR_ARCHITECTURE\s*\}",
                      text)
        assert m, "Rueckfall fuer $procArch fehlt"
        kopf = text.index('Write-Host "[start] OS-Arch')
        assert text.index("$procArch = $ri::ProcessArchitecture") < m.start() < kopf, \
            "nach dem Auslesen und vor der Kopfzeile"
