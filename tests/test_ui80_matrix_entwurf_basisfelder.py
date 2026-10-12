"""UI-80: der Matrix-Editor meldet nur, was er selbst bearbeiten kann.

Befund (DOC-60, Bild ``01_matrix_gruppe.png``): bei der unberuehrten Matrix
„PAR Dimmer-Welle links → rechts" stand „● ungespeicherte Änderungen" —
gespeichert ``speed`` 2,057, Arbeitskopie 1,0. Der VC-Regler „Tempo Welle L→R"
(Effekt-Tempo) setzt das Basisfeld ``Function.speed`` am laufenden Effekt; der
Entwurf des Editors (``from_dict(to_dict())``) stellte es nicht her.

Nachgemessen gehen auf diesem Weg VIER Basisfelder verloren:

* ``speed``, ``intensity`` (VC-Regler Effekt-Tempo / Effekt-Helligkeit) und
  ``folder`` (Bibliotheks-Ordner) — der Editor bearbeitet keins davon. Jedes
  erzeugte den Hinweis, und „Speichern" bekam ihn nie weg.
* ``align_on_start`` — dafuer HAT der Editor einen Haken. ``apply_dict``
  uebernahm ihn nicht: der Haken liess sich umstellen, aber nie speichern.

Jetzt: die drei fremden Felder uebernimmt der Entwurf (Vorschau so schnell wie
der echte Effekt), sie zaehlen nicht als Aenderung und werden beim Speichern
nicht zurueckgeschrieben; ``align_on_start`` gehoert zu ``apply_dict``.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest                                          # noqa: E402
from PySide6.QtWidgets import QApplication             # noqa: E402

from _qt_lifecycle import destroy_all_top_level_widgets  # noqa: E402  XPLAT-15
from src.core.engine.rgb_matrix import RgbMatrixInstance  # noqa: E402

_app = QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def _xplat15_no_leaked_widgets():
    yield
    destroy_all_top_level_widgets(QApplication.instance())


@pytest.fixture
def view():
    from src.ui.views.rgb_matrix_view import RgbMatrixView
    v = RgbMatrixView()
    if len(v._instances) == 0:
        v._add()
    v._list.setCurrentRow(0)
    assert v._saved is not None and v._current is not None
    # Die Matrix gehoert dem geteilten FunctionManager — jeden Test mit den
    # Vorgabewerten beginnen und danach wieder so hinterlassen.
    m = v._saved
    vorher = {f: getattr(m, f) for f in
              ("speed", "intensity", "folder", "align_on_start", "matrix_speed")}
    m.speed, m.intensity, m.folder, m.align_on_start = 1.0, 1.0, "", True
    v._select(v._list.currentRow())
    yield v
    for feld, wert in vorher.items():
        setattr(m, feld, wert)


def _neu_oeffnen(v):
    """Die Matrix im Editor neu oeffnen — derselbe Weg wie ein Klick in der Liste."""
    v._select(v._list.currentRow())


def _hinweis(v) -> str:
    return v._dirty_lbl.text()


# ── Felder, die der Editor NICHT bearbeitet ──────────────────────────────────

@pytest.mark.parametrize("feld, wert", [
    ("speed", 2.057),             # VC-Regler „Effekt-Tempo"
    ("intensity", 0.42),          # VC-Regler „Effekt-Helligkeit"
    ("folder", "Front/Wash"),     # Bibliotheks-Ordner
])
def test_fremdes_basisfeld_macht_keinen_aenderungshinweis(view, feld, wert):
    setattr(view._saved, feld, wert)
    _neu_oeffnen(view)
    assert _hinweis(view) == "", (
        f"unberuehrte Matrix mit {feld}={wert!r} zeigt „ungespeicherte Änderungen“")
    assert not view._btn_save.isEnabled()
    assert not view._btn_reset.isEnabled()
    # Der Entwurf laeuft mit demselben Wert wie der echte Effekt (Vorschau).
    assert getattr(view._current, feld) == wert


def test_regler_bewegt_waehrend_der_editor_offen_ist(view):
    _neu_oeffnen(view)
    view._saved.speed = 3.0            # jemand zieht den VC-Regler
    view._saved.intensity = 0.5
    view._update_dirty()
    assert _hinweis(view) == ""


def test_speichern_behaelt_das_regler_tempo(view):
    view._saved.speed = 2.057
    view._saved.intensity = 0.42
    view._saved.folder = "Front/Wash"
    _neu_oeffnen(view)
    view._current.matrix_speed = view._saved.matrix_speed + 2.5     # echte Aenderung
    view._update_dirty()
    assert _hinweis(view) != ""
    view._saved.speed = 3.5            # Regler bewegt sich NACH dem Oeffnen weiter
    view._save_edit()
    assert view._saved.matrix_speed == view._current.matrix_speed
    assert view._saved.speed == 3.5, "Speichern im Editor hat das Regler-Tempo zurueckgesetzt"
    assert view._saved.intensity == 0.42
    assert view._saved.folder == "Front/Wash"
    assert _hinweis(view) == "", "nach dem Speichern bleibt der Hinweis stehen"


def test_echte_aenderung_wird_weiter_gemeldet(view):
    """Gegenprobe: der Vergleich ist nicht einfach abgeschaltet."""
    view._saved.speed = 2.057
    _neu_oeffnen(view)
    assert _hinweis(view) == ""
    view._current.matrix_speed = view._saved.matrix_speed + 1.0
    view._update_dirty()
    assert "ungespeicherte" in _hinweis(view)
    assert view._btn_save.isEnabled()
    view._reset_edit()
    assert _hinweis(view) == ""
    assert view._current.speed == 2.057      # auch nach „Verwerfen" der echte Master


# ── align_on_start: der Editor HAT den Haken ─────────────────────────────────

def test_align_on_start_aus_macht_keinen_aenderungshinweis(view):
    view._saved.align_on_start = False
    _neu_oeffnen(view)
    assert view._current.align_on_start is False, "der Entwurf fiel auf die Vorgabe zurueck"
    assert view._tempo_align_check.isChecked() is False
    assert _hinweis(view) == ""


def test_align_on_start_laesst_sich_im_editor_speichern(view):
    assert view._saved.align_on_start is True
    _neu_oeffnen(view)
    view._current.align_on_start = False        # was der Haken im Editor setzt
    view._update_dirty()
    assert "ungespeicherte" in _hinweis(view)
    view._save_edit()
    assert view._saved.align_on_start is False, "der Haken kam beim Speichern nie an"
    assert _hinweis(view) == ""


# ── Engine: der Vertrag von apply_dict ───────────────────────────────────────

def test_apply_dict_uebernimmt_align_on_start():
    quelle = RgbMatrixInstance(name="Q")
    quelle.align_on_start = False
    ziel = RgbMatrixInstance(name="Z")
    ziel.apply_dict(quelle.to_dict())
    assert ziel.align_on_start is False
    # Fehlt der Schluessel (Alt-Show), bleibt der vorhandene Wert.
    d = quelle.to_dict()
    d.pop("align_on_start")
    ziel.align_on_start = True
    ziel.apply_dict(d)
    assert ziel.align_on_start is True


def test_apply_dict_fasst_die_master_und_den_ordner_nicht_an():
    """Darauf beruht „Speichern behaelt das Regler-Tempo"."""
    ziel = RgbMatrixInstance(name="Z")
    ziel.speed, ziel.intensity, ziel.folder = 2.5, 0.3, "Front"
    quelle = RgbMatrixInstance(name="Q")            # speed 1.0, intensity 1.0, folder ""
    quelle.matrix_speed = 7.0
    ziel.apply_dict(quelle.to_dict())
    assert ziel.matrix_speed == 7.0
    assert (ziel.speed, ziel.intensity, ziel.folder) == (2.5, 0.3, "Front")


def test_altlast_speed_als_animationsrate_bleibt():
    """Alt-Shows ohne ``matrix_speed`` trugen die Animationsrate unter ``speed``."""
    m = RgbMatrixInstance(name="Alt")
    d = m.to_dict()
    d.pop("matrix_speed")
    d["speed"] = 6.0
    alt = RgbMatrixInstance.from_dict(d)
    assert alt.matrix_speed == 6.0
