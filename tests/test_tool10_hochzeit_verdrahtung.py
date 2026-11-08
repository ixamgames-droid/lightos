"""TOOL-10: Die Hochzeit-Demo tut an jedem Tempo-Bedienelement, was draufsteht.

Befunde (08.11., am Generator ``tools/build_hochzeit_komplett.py`` gemessen):

* **„Sync jetzt"** war ``AUTO_SYNC`` — ein Schalter fuer den Auto-Sync, kein
  „alle auf die Eins". Jetzt ``SYNC_BUS`` auf Bus A, den Bus aller Farb-,
  Dimmer- und Bewegungs-Effekte.
* **„Sub C (Dimmer ×2)"** stellte Bus C, an dem kein Effekt haengt. Das Rad
  heisst jetzt „Dimmer-Tempo ×" und stellt den Faktor der Dimmer-Effekte selbst
  (``TEMPO_BUS_MULT``); „Master A (Farbe ×1)" entsprechend „Farb-Tempo ×".
* **Tempo-Regler ohne Wirkung:** ein Effekt auf einem LAUFENDEN Tempo-Bus liest
  nur ``tempo_multiplier`` (``rgb_matrix._advance_step``/``efx._sync_from_bus``),
  ``speed``/``matrix_speed`` gelten nur im Free-Run. „Dimmer-Tempo",
  „Effekt-Tempo", „Mover-Speed" (``EFFECT_SPEED``) und die Encoder „Tempo"/
  „EFX-Tempo" (``speed``) stellten deshalb ins Leere.
* **Tap/Musik-BPM/„BPM global"** treiben den globalen Tempo-Leiter. Bus A lief
  als eigener Master mit festen 128 BPM daneben — die Effekte hoerten das nie.
  Bus A folgt jetzt der Haupt-BPM (Sub ×1, wie die Quelle „Sound" im Panel).
* Die Fehlermeldung bei fehlendem Profil schickte zu ``ensure_builtins`` —
  das legt das lokale QLC+-Profil „Speider" nie an.

Die Show wird im Unterprozess gebaut (``LIGHTOS_GEN_OUT`` → Wegwerf-Ordner,
``shows/`` bleibt unberuehrt) und hier geladen. Der Generator braucht das nur
lokal importierte Spider-Profil; fehlt es (CI), wird der Bau-Teil
uebersprungen — die statischen Pruefungen am Quelltext laufen immer.

Gemessen wird am Effekt selbst: Bus und Effekt laufen mit derselben Show-Zeit
(``dt`` je Frame), die Fortschrittsrate vor und nach dem Bedienen wird verglichen.
"""
from __future__ import annotations

import ast
import os
import subprocess
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

_app = QApplication.instance() or QApplication([])

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GENERATOR = os.path.join(REPO, "tools", "build_hochzeit_komplett.py")
DOCS = os.path.join(REPO, "docs", "anleitung_hochzeit_komplett")

DT = 0.05          # Show-Zeit je Frame
BPM = 128.0


def _quelle():
    with open(GENERATOR, encoding="utf-8") as fh:
        return fh.read()


# ── statisch (laeuft auch ohne Spider-Profil) ───────────────────────────────────

def test_profil_meldung_schickt_nicht_zu_ensure_builtins():
    """„Speider" ist ein lokal importiertes QLC+-Profil: der Hinweis
    „App einmal starten (ensure_builtins)" waere falsch."""
    baum = ast.parse(_quelle())
    fn = next(k for k in ast.walk(baum)
              if isinstance(k, ast.FunctionDef) and k.name == "profile_id")
    text = ast.unparse(fn)
    assert "Speider" in text or "LOKALE_PROFILE" in text, \
        "profile_id unterscheidet lokale Profile nicht"
    lokal = next((k for k in ast.walk(baum) if isinstance(k, ast.Assign)
                  and any(isinstance(t, ast.Name) and t.id == "LOKALE_PROFILE"
                          for t in k.targets)), None)
    assert lokal is not None and "Speider" in ast.unparse(lokal.value)


def test_quelltext_ohne_tote_tempo_verdrahtung():
    src = _quelle()
    assert '"Sync jetzt", ButtonAction.AUTO_SYNC' not in src
    assert "Sub C (Dimmer" not in src
    assert "SliderMode.EFFECT_SPEED" not in src, \
        "EFFECT_SPEED stellt speed — Bus-Effekte lesen nur tempo_multiplier"
    assert 'bus_a.set_role("sub")' in src, "Bus A folgt der Haupt-BPM nicht"


def test_anleitungen_nachgezogen():
    with open(os.path.join(DOCS, "mini_strobe_tempo", "ANLEITUNG.md"), encoding="utf-8") as fh:
        strobe = fh.read()
    with open(os.path.join(DOCS, "mini_live_editor", "ANLEITUNG.md"), encoding="utf-8") as fh:
        live = fh.read()
    with open(os.path.join(DOCS, "mini_bewegung_efx", "ANLEITUNG.md"), encoding="utf-8") as fh:
        efx = fh.read()
    with open(os.path.join(DOCS, "mini_dimmer_bewegungen", "ANLEITUNG.md"), encoding="utf-8") as fh:
        dim = fh.read()
    assert "Sub C" not in strobe and "schaltet **Auto-Sync**" not in strobe
    assert "Dimmer-Tempo ×" in strobe and "Farb-Tempo ×" in strobe
    assert "Haupt-BPM" in strobe
    for text in (live, efx, dim):
        assert "wirkt nicht, solange" not in text
        assert "nur, solange **keine BPM**" not in text
        assert "nur die Eigengeschwindigkeit" not in text


# ── am gebauten Generator-Ergebnis ──────────────────────────────────────────────

@pytest.fixture(scope="module")
def gebaut():
    """Generator einmal je Modul bauen lassen; liefert den Pfad der Show."""
    with tempfile.TemporaryDirectory(prefix="lightos_tool10_") as tmp:
        ziel = os.path.join(tmp, "Hochzeit_Komplett_2026.lshow")
        env = dict(os.environ)
        env.update({"LIGHTOS_GEN_OUT": ziel,
                    "LIGHTOS_SHOW_DB": os.path.join(tmp, "show.db"),
                    "QT_QPA_PLATFORM": "offscreen",
                    "PYTHONIOENCODING": "utf-8"})
        lauf = subprocess.run([sys.executable, GENERATOR], cwd=REPO, env=env,
                              capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=600)
        ausgabe = lauf.stdout + lauf.stderr
        if lauf.returncode != 0 and "Profil 'Speider' fehlt" in ausgabe:
            pytest.skip("lokales Spider-Profil 'Speider' fehlt (nur am Rig-Rechner)")
        assert lauf.returncode == 0, ausgabe[-3000:]
        assert "FERTIG" in lauf.stdout
        assert os.path.isfile(ziel), "LIGHTOS_GEN_OUT wurde nicht beachtet"
        yield ziel


@pytest.fixture()
def show(gebaut):
    """Je Test frisch laden — conftest setzt Tempo-Busse/BPM-Leiter je Test zurueck."""
    from src.core.show.show_file import load_show, reset_show
    from src.core.app_state import get_state
    ok, msg = load_show(gebaut)
    assert ok, msg
    yield get_state()
    reset_show()


@pytest.fixture()
def takt(show):
    """Haupt-BPM auf 128 (wie nach Tap/Musik-BPM), alles gestoppt."""
    from src.core.engine.bpm_manager import get_bpm_manager
    from src.core.engine.function_manager import get_function_manager
    get_bpm_manager().set_manual_bpm(BPM)
    yield
    get_function_manager().stop_all()
    get_bpm_manager().reset()


def _w(state, caption, bank):
    treffer = [d for d in state._vc_layout["widgets"]
               if d.get("caption") == caption and d.get("bank") == bank]
    assert len(treffer) == 1, f"{caption!r} auf Bank {bank}: {len(treffer)} Treffer"
    return treffer[0]


def _bauen(d):
    from src.ui.virtualconsole.vc_canvas import WIDGET_REGISTRY
    w = WIDGET_REGISTRY[d["type"]]()
    w.apply_dict(d)
    return w


def _fn(name):
    from src.core.engine.function_manager import get_function_manager
    return next(f for f in get_function_manager().all() if f.name == name)


def _rate(fn, frames=12):
    """Fortschritt je Sekunde Show-Zeit (Matrix: Schritte, EFX: Umlaeufe)."""
    from src.core.engine.tempo_bus import get_tempo_bus_manager
    from src.core.engine.efx import EfxInstance
    mgr = get_tempo_bus_manager()
    weg, vorher = 0.0, None
    for _ in range(frames):
        mgr.advance_frame(DT)
        if isinstance(fn, EfxInstance):
            fn._advance(DT)
            jetzt = fn._phase
            if vorher is not None:
                weg += (jetzt - vorher) % 1.0
        else:
            fn._advance_step(DT)
            jetzt = fn._step
            if vorher is not None:
                weg += jetzt - vorher
        vorher = jetzt
    return weg / ((frames - 1) * DT)


def _start(fn):
    from src.core.engine.function_manager import get_function_manager
    get_function_manager().start(fn.id)
    assert fn.is_running


def test_sync_jetzt_setzt_bus_a_auf_die_eins(show, takt):
    from src.core.engine.tempo_bus import get_tempo_bus_manager
    from src.ui.virtualconsole.vc_button import ButtonAction
    d = _w(show, "Sync jetzt", 3)
    knopf = _bauen(d)
    assert knopf.action == ButtonAction.SYNC_BUS and knopf.tempo_bus_id == "A"
    farbe, dimmer, kreis = _fn("Farbwechsel"), _fn("Lauflicht"), _fn("Kreis")
    for f in (farbe, dimmer, kreis):
        _start(f)
    _rate(farbe)
    bus = get_tempo_bus_manager().get("A")
    knopf._trigger_primary(True)
    pos = bus.position()
    for f in (farbe, dimmer, kreis):
        assert f._beat_anchor == pytest.approx(pos), f"{f.name} nicht auf der Eins"


def test_bpm_regler_und_tap_treffen_bus_a(show, takt):
    from src.core.engine.tempo_bus import get_tempo_bus_manager
    from src.core.engine.bpm_manager import get_bpm_manager
    fader = _bauen(_w(show, "BPM global", 3))
    fader._value = 0          # 30 BPM
    fader._apply()
    get_tempo_bus_manager().advance_frame(DT)
    assert get_bpm_manager().bpm == pytest.approx(30.0)
    assert get_tempo_bus_manager().get("A").bpm == pytest.approx(30.0), \
        "Bus A laeuft am globalen Leiter vorbei"
    farbe = _fn("Farbwechsel")
    _start(farbe)
    langsam = _rate(farbe)
    get_bpm_manager().nudge(+90.0)          # BPM +/Tap-Pfad: MANUAL am Leiter
    assert _rate(farbe) == pytest.approx(langsam * 4.0, rel=0.05)


@pytest.mark.parametrize("caption,bank,ziel,wert", [
    ("Dimmer-Tempo", 1, "Lauflicht", 255),
    ("Effekt-Tempo", 4, "Lauflicht", 255),
    ("Mover-Speed", 2, "Kreis", 255),
])
def test_tempo_fader_trifft_den_laufenden_effekt(show, takt, caption, bank, ziel, wert):
    fn = _fn(ziel)
    _start(fn)
    vorher = _rate(fn)
    assert vorher > 0
    fader = _bauen(_w(show, caption, bank))
    fader._value = wert
    fader._apply()
    nachher = _rate(fn)
    assert nachher > vorher * 1.5, f"{caption}: {vorher:.3f} -> {nachher:.3f} je s"


@pytest.mark.parametrize("caption,bank,ziel", [
    ("Tempo", 4, "Lauflicht"),
    ("EFX-Tempo", 2, "Kreis"),
])
def test_tempo_encoder_trifft_den_laufenden_effekt(show, takt, caption, bank, ziel):
    fn = _fn(ziel)
    _start(fn)
    vorher = _rate(fn)
    enc = _bauen(_w(show, caption, bank))
    enc.nudge(10)
    nachher = _rate(fn)
    assert nachher > vorher * 1.2, f"{caption}: {vorher:.3f} -> {nachher:.3f} je s"


@pytest.mark.parametrize("caption,ziel,gruppe", [
    ("Dimmer-Tempo ×", "Lauflicht", "dim"),
    ("Farb-Tempo ×", "Farbwechsel", "farbe"),
])
def test_tempo_rad_bank4_trifft_seine_effekte(show, takt, caption, ziel, gruppe):
    from src.core.engine.rgb_matrix import RgbMatrixInstance, MatrixStyle
    from src.core.engine.function_manager import get_function_manager
    from src.ui.virtualconsole.vc_speedial import SpeedTarget
    rad = _bauen(_w(show, caption, 3))
    assert rad.target_mode == SpeedTarget.TEMPO_BUS_MULT
    mats = [f for f in get_function_manager().all()
            if isinstance(f, RgbMatrixInstance) and f.tempo_bus_id == "A"]
    soll = {f.id for f in mats
            if (f.style == MatrixStyle.DIMMER) == (gruppe == "dim")}
    assert set(rad._targets()) == soll
    fn = _fn(ziel)
    _start(fn)
    vorher = _rate(fn)
    rad._set_factor(4.0)
    assert _rate(fn) > vorher * 1.5


def test_kein_tempo_element_auf_bus_ohne_effekt(show):
    """Ein Tempo-Knoten auf einem Bus, an dem nichts haengt, ist ein totes Element
    (der alte „Sub C")."""
    from src.core.engine.function_manager import get_function_manager
    from src.ui.virtualconsole.vc_speedial import SpeedTarget
    busse = {getattr(f, "tempo_bus_id", "") for f in get_function_manager().all()}
    for d in show._vc_layout["widgets"]:
        if d["type"] == "VCSpeedDial" and d.get("target_mode") == SpeedTarget.SPEED_NODE:
            assert d.get("tempo_bus_id") in busse, d.get("caption")


def test_lint_strict_auf_das_ergebnis(gebaut):
    """``tools/lint_show.py --strict`` (eigene Werkzeug-Sandbox) auf die gebaute Show."""
    lauf = subprocess.run([sys.executable, os.path.join(REPO, "tools", "lint_show.py"),
                           "--strict", gebaut], cwd=REPO,
                          env=dict(os.environ, QT_QPA_PLATFORM="offscreen",
                                   PYTHONIOENCODING="utf-8"),
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=300)
    assert lauf.returncode == 0, (lauf.stdout + lauf.stderr)[-3000:]
