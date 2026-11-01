"""TOOL-30: ``tools/app.ps1`` gibt im Probelauf die Lizenz NUR LESEND mit — wie
``tools/app.sh`` seit STAB-39.

**Warum.** Aus einer Claude-Code-Shell (``CLAUDECODE=1``) ist ein App-Start ein
PROBELAUF mit leerem Wegwerf-Datenordner. Darin fehlt die Lizenzdatei, und statt
des Hauptfensters kam der Dialog „Testlizenz erforderlich“ — ``wait``/``shot``
griffen dann den Dialog. ``app.sh`` setzt deshalb ``LIGHTOS_LIZENZ`` auf die
Lizenzdatei im echten Datenordner (gefunden ueber
``paths.regulaerer_app_data_dir``); ``app.ps1`` tat das nicht (gemessen am
01.11.2026 unter Windows 11 x64).

Geprueft ueber den Unterbefehl ``lizenz``, der genau die Entscheidung von
``start`` zeigt, ohne die App zu starten. Nie mit einer echten Lizenz: die Datei
hier ist ein Platzhalter in einem tmp-Datenordner.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SKRIPT = REPO / "tools" / "app.ps1"

pytestmark = pytest.mark.skipif(sys.platform != "win32",
                                reason="tools/app.ps1 ist der Windows-Treiber")


def _lauf(tmp_path: Path, **extra: str) -> str:
    env = {k: v for k, v in os.environ.items()
           if not k.startswith("LIGHTOS_") and k != "CLAUDECODE"}
    env["APPDATA"] = str(tmp_path / "Roaming")
    env.update(extra)
    r = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
         "-File", str(SKRIPT), "lizenz"],
        cwd=str(REPO), env=env, capture_output=True, timeout=120)
    aus = (r.stdout + r.stderr).decode("utf-8", "replace")
    assert r.returncode == 0, aus
    return aus


def _wert(aus: str) -> str:
    m = re.search(r"^LIGHTOS_LIZENZ=(.*)$", aus, re.MULTILINE)
    assert m, aus
    return m.group(1).strip()


@pytest.fixture
def platzhalter(tmp_path):
    p = tmp_path / "Roaming" / "LightOS" / "lightos-lizenz.lic"
    p.parent.mkdir(parents=True)
    p.write_text("PLATZHALTER - keine Lizenz", encoding="utf-8")
    return p


def test_probelauf_bekommt_die_lizenz_des_rechners_lesend(tmp_path, platzhalter):
    aus = _lauf(tmp_path, CLAUDECODE="1")
    assert os.path.normcase(_wert(aus)) == os.path.normcase(str(platzhalter)), aus
    assert "Probelauf" in aus
    assert platzhalter.read_text(encoding="utf-8") == "PLATZHALTER - keine Lizenz"


def test_gesetzte_lizenz_gewinnt(tmp_path, platzhalter):
    andere = tmp_path / "andere.lic"
    aus = _lauf(tmp_path, CLAUDECODE="1", LIGHTOS_LIZENZ=str(andere))
    assert _wert(aus) == str(andere), aus


def test_ohne_agent_shell_wird_nichts_gesetzt(tmp_path, platzhalter):
    """Ein normaler Start ist die echte App — sie findet ihre Lizenz selbst."""
    assert _wert(_lauf(tmp_path)) == "", "ausserhalb der Agent-Shell nichts setzen"


def test_ohne_lizenzdatei_ein_hinweis_und_nichts_gesetzt(tmp_path):
    aus = _lauf(tmp_path, CLAUDECODE="1")
    assert _wert(aus) == ""
    assert "keine Lizenzdatei" in aus, aus


def test_start_setzt_die_lizenz_vor_dem_start():
    """``Start-App`` ruft die Entscheidung VOR ``Start-Process`` — sonst erbte
    die App die Variable nicht."""
    text = SKRIPT.read_text(encoding="utf-8")
    rumpf = text[text.index("function Start-App"):]
    rumpf = rumpf[:rumpf.index("\n}\n")]
    assert "Set-ProbelaufLizenz" in rumpf, rumpf
    assert rumpf.index("Set-ProbelaufLizenz") < rumpf.index("Start-Process"), rumpf
