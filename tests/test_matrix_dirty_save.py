"""Tests fuer den Dirty-State / Speichern-Modell des Matrix-Editors (I2.6).

Prueft:
- Engine: apply_dict uebernimmt alle Felder korrekt (DRY-Refactor).
- View: Parameteraenderungen landen zuerst im Draft (_current), nicht in _saved.
- View: _save_edit kopiert Draft nach _saved; danach kein dirty.
- View: _reset_edit verwirft Draft; danach wieder identisch mit _saved.
- View: Grid-Zuweisung via _assign_from_selection landet in BEIDEN Instanzen
  (kein dirty durch Grid).
"""
from __future__ import annotations
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from src.core.engine.rgb_matrix import RgbMatrixInstance, RgbAlgorithm


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _make_view_with_matrix():
    """RgbMatrixView aufbauen und sicherstellen, dass eine Matrix ausgewaehlt ist."""
    from src.ui.views.rgb_matrix_view import RgbMatrixView
    view = RgbMatrixView()
    if len(view._instances) == 0:
        view._add()
    view._list.setCurrentRow(0)
    assert view._saved is not None, "_saved muss nach Auswahl gesetzt sein"
    assert view._current is not None, "_current (Draft) muss nach Auswahl gesetzt sein"
    return view


# ── Engine: apply_dict ────────────────────────────────────────────────────────

def test_apply_dict_uebernimmt_alle_felder():
    """apply_dict schreibt alle editierbaren Felder in die bestehende Instanz."""
    m = RgbMatrixInstance(name="Original", cols=8, rows=4)
    m.matrix_speed = 1.0
    m.algorithm = RgbAlgorithm.PLAIN

    clone = RgbMatrixInstance.from_dict(m.to_dict())
    clone.algorithm = RgbAlgorithm.RAINBOW
    clone.matrix_speed = 3.5
    clone.cols = 12
    clone.rows = 6

    m.apply_dict(clone.to_dict())

    assert m.algorithm == RgbAlgorithm.RAINBOW
    assert m.matrix_speed == 3.5
    assert m.cols == 12
    assert m.rows == 6
    # to_dict-Vergleich: nach apply_dict muessen beide identisch sein
    # (id unterscheidet sich => direkt Felder pruefen, nicht to_dict-Gesamt)
    d_m = m.to_dict()
    d_c = clone.to_dict()
    for key in ("algorithm", "matrix_speed", "cols", "rows", "color1",
                "color2", "color3", "style", "white_amount", "direction",
                "intensity_min", "intensity_max", "shutter_min", "shutter_max"):
        assert d_m[key] == d_c[key], f"Feld '{key}' stimmt nicht ueberein"


def test_apply_dict_aendert_nicht_id():
    """apply_dict darf die id der Ziel-Instanz NICHT ueberschreiben."""
    m = RgbMatrixInstance(name="A", fid=42)
    andere = RgbMatrixInstance(name="B", fid=99)
    m.apply_dict(andere.to_dict())
    assert m.id == 42, "id muss unveraendert bleiben"


# ── View: Deferred Param-Aenderung ───────────────────────────────────────────

def test_param_change_aendert_nur_draft():
    """Nach _param_change ist _saved unveraendert, Draft geaendert, Save-Button aktiv."""
    _app()
    view = _make_view_with_matrix()

    # Ausgangswert merken
    saved_speed_before = view._saved.matrix_speed

    # Draft direkt aendern + _param_change ausfuehren (wie das Widget-Signal)
    view._speed_spin.setValue(9.99)
    # _param_change schreibt Widgets -> Draft
    view._param_change()

    assert view._current.matrix_speed == 9.99, "Draft-Speed muss 9.99 sein"
    assert view._saved.matrix_speed == saved_speed_before, (
        "_saved darf sich durch _param_change nicht aendern"
    )
    assert view._btn_save.isEnabled(), "Speichern-Button muss nach dirty aktiv sein"
    assert view._btn_reset.isEnabled(), "Zuruecksetzen-Button muss nach dirty aktiv sein"
    assert "ungespeicherte" in view._dirty_lbl.text(), "Dirty-Label muss Hinweis zeigen"


# ── View: _save_edit ──────────────────────────────────────────────────────────

def test_save_edit_kopiert_draft_nach_saved():
    """_save_edit: Draft-Werte landen in _saved; danach kein dirty."""
    _app()
    view = _make_view_with_matrix()

    view._speed_spin.setValue(7.77)
    view._param_change()
    assert view._btn_save.isEnabled()

    view._save_edit()

    assert view._saved.matrix_speed == 7.77, "_saved.matrix_speed muss 7.77 sein"
    # to_dict-Vergleich (ohne id, da Draft eigene id hat)
    d_saved = view._saved.to_dict()
    d_draft = view._current.to_dict()
    for key in ("matrix_speed", "algorithm", "cols", "rows", "color1"):
        assert d_saved[key] == d_draft[key], f"Feld '{key}' nach Save nicht gleich"
    assert not view._btn_save.isEnabled(), "Speichern-Button muss nach Save deaktiviert sein"
    assert not view._btn_reset.isEnabled(), "Zuruecksetzen-Button muss nach Save deaktiviert sein"
    assert view._dirty_lbl.text() == "", "Dirty-Label muss leer sein"


# ── View: Name-Aenderung ist deferred (dirty + Speichern persistiert) ────────

def test_name_change_macht_dirty():
    """Namensaenderung landet nur im Draft -> dirty, _saved unveraendert."""
    _app()
    view = _make_view_with_matrix()
    alter_name = view._saved.name

    view._name_edit.setText("Mein neuer Name")

    assert view._current.name == "Mein neuer Name", "Draft-Name muss gesetzt sein"
    assert view._saved.name == alter_name, "_saved.name darf sich nicht aendern"
    assert view._btn_save.isEnabled(), "Speichern-Button muss nach Namensaenderung aktiv sein"


def test_name_save_persistiert_und_benachrichtigt():
    """_save_edit uebernimmt den neuen Namen in _saved und feuert FUNCTION_CHANGED."""
    _app()
    view = _make_view_with_matrix()

    events = []
    from src.core.sync import get_sync, SyncEvent
    get_sync().subscribe(SyncEvent.FUNCTION_CHANGED, lambda *a: events.append(a))

    view._name_edit.setText("Gespeicherter Name")
    assert view._btn_save.isEnabled()
    view._save_edit()

    assert view._saved.name == "Gespeicherter Name", "_saved.name muss nach Save aktualisiert sein"
    assert not view._btn_save.isEnabled(), "Nach Save kein dirty mehr"
    assert len(events) >= 1, "FUNCTION_CHANGED muss gefeuert werden (Bibliothek refreshen)"


def test_name_reset_verwirft_listeneintrag():
    """_reset_edit setzt Draft-Name und Listeneintrag auf den gespeicherten Wert zurueck."""
    _app()
    view = _make_view_with_matrix()
    alter_name = view._saved.name
    row = view._list.currentRow()

    view._name_edit.setText("Verworfener Name")
    assert view._list.item(row).text() == "Verworfener Name", "Live-Vorschau in der Liste"

    view._reset_edit()

    assert view._current.name == alter_name, "Draft muss zurueckgesetzt sein"
    assert view._list.item(row).text() == alter_name, "Listeneintrag muss zurueckgesetzt sein"
    assert not view._btn_save.isEnabled()


# ── View: _reset_edit ─────────────────────────────────────────────────────────

def test_reset_edit_verwirft_draft():
    """_reset_edit: Draft wird auf _saved zurueckgesetzt; danach kein dirty."""
    _app()
    view = _make_view_with_matrix()

    original_speed = view._saved.matrix_speed

    # Draft aendern
    view._speed_spin.setValue(5.55)
    view._param_change()
    assert view._current.matrix_speed == 5.55
    assert view._btn_save.isEnabled()

    # Zuruecksetzen
    view._reset_edit()

    assert view._current.matrix_speed == original_speed, (
        "Draft muss nach Reset den Original-Speed haben"
    )
    assert not view._btn_save.isEnabled(), "Speichern-Button muss nach Reset deaktiviert sein"
    assert view._dirty_lbl.text() == "", "Dirty-Label muss nach Reset leer sein"


# ── View: Grid bleibt live (kein dirty) ──────────────────────────────────────

def test_assign_from_selection_kein_dirty():
    """_assign_from_selection schreibt Grid in beide Instanzen -> kein dirty."""
    _app()
    view = _make_view_with_matrix()

    # Direkt fids setzen und _assign_from_selection mit simuliertem Fallback aufrufen.
    # Wir patchen get_selected_fids so, dass es eine bekannte Liste zurueckgibt.
    from src.core.app_state import get_state
    state = get_state()

    # Monkey-Patch fuer diesen Test: Gruppen-Pfad wird nicht betreten
    # (get_selected_group_id gibt None zurueck), Fallback liefert fids.
    original_group = getattr(state, "get_selected_group_id", None)
    original_fids  = getattr(state, "get_selected_fids", None)

    try:
        state.get_selected_group_id = lambda: None
        state.get_selected_fids = lambda: [1, 2, 3]

        view._assign_from_selection()
    finally:
        # Patch zuruecknehmen
        if original_group is not None:
            state.get_selected_group_id = original_group
        if original_fids is not None:
            state.get_selected_fids = original_fids

    # Beide Instanzen muessen das gleiche Grid haben
    assert view._current.fixture_grid == [1, 2, 3], (
        f"Draft-Grid falsch: {view._current.fixture_grid!r}"
    )
    assert view._saved.fixture_grid == [1, 2, 3], (
        f"Saved-Grid falsch: {view._saved.fixture_grid!r}"
    )
    # Grid-Aenderung darf KEIN dirty erzeugen
    assert not view._btn_save.isEnabled(), (
        "Speichern-Button darf nach Grid-Zuweisung NICHT aktiv sein"
    )


# ── Doppelte Sicherung: from_dict-Roundtrip bleibt grueen ────────────────────

def test_from_dict_roundtrip_unveraendert():
    """Bestehende from_dict-Semantik: Roundtrip erhaelt alle Felder."""
    m = RgbMatrixInstance(name="Test", cols=5, rows=3)
    m.algorithm = RgbAlgorithm.CHASE
    m.matrix_speed = 2.0
    m.color1 = (10, 20, 30)
    m.params = {"runner_count": 2}

    restored = RgbMatrixInstance.from_dict(m.to_dict())

    assert restored.algorithm == RgbAlgorithm.CHASE
    assert restored.matrix_speed == 2.0
    assert restored.cols == 5
    assert restored.rows == 3
    assert restored.color1 == (10, 20, 30)
    assert restored.params.get("runner_count") == 2
