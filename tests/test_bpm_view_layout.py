"""BPM-09 (S4): Abnahme der Standardansicht „Erkennung".

* Standard (Erweitert eingeklappt): genau **6 Bedienelemente** — Quelle, TAP,
  Auto | Manuell, ×½, ×2, Aufklapper. Gezaehlt werden sichtbare
  ``QAbstractButton``/``QComboBox``/``QAbstractSpinBox``/``QSlider``; die
  Mitglieder EINER exklusiven ``QButtonGroup`` (Auto | Manuell, ein
  Segment-Schalter aus zwei QToolButtons) zaehlen als EIN Bedienelement
  (plan.md 1.2: „Auto | Manuell (Zweizustand)" ist ein Element). Roh sind es 7.
* Erweitert aufgeklappt: 6 + 11.
* Der 50-ms-Snapshot-Timer laeuft nur bei Sichtbarkeit (showEvent/hideEvent).
* Kein ``get_bpm(`` in der View und den beiden Helfern (Briefing 7c; die
  AudioInputView faellt erst in S5 und ist ausgenommen).
* Jedes Bedienelement traegt einen Tooltip.
"""
from __future__ import annotations
import os
import re

import pytest
from PySide6.QtWidgets import (
    QAbstractButton, QAbstractSpinBox, QApplication, QComboBox, QSlider, QWidget,
)

_app = QApplication.instance() or QApplication([])
_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

import pytest as _pytest_xplat15                      # noqa: E402
from _qt_lifecycle import destroy_all_top_level_widgets  # noqa: E402  XPLAT-15


@_pytest_xplat15.fixture(autouse=True)
def _xplat15_no_leaked_widgets():
    yield
    destroy_all_top_level_widgets(_app)


@pytest.fixture
def _isolated_prefs(tmp_path, monkeypatch):
    from src.core.audio import bpm_settings as bs
    monkeypatch.setattr(bs, "_PREFS_DIR", str(tmp_path))
    monkeypatch.setattr(bs, "_PREFS_PATH", str(tmp_path / "ui_prefs.json"))
    return bs


@pytest.fixture(autouse=True)
def _kein_echtes_capture(monkeypatch):
    """S2-Lehre: AudioCapture.start ist No-op (sonst Exit 134 am Prozessende)."""
    import src.core.audio.capture as cap_mod
    monkeypatch.setattr(cap_mod.AudioCapture, "start", lambda self: False)
    yield
    from src.core.engine.bpm_manager import get_bpm_manager
    get_bpm_manager().use_audio_source(False)


_KINDS = (QAbstractButton, QComboBox, QAbstractSpinBox, QSlider)


def visible_controls(view: QWidget) -> list[QWidget]:
    """Sichtbare Bedienelemente; Mitglieder einer exklusiven QButtonGroup einmal."""
    _app.processEvents()
    seen: list[QWidget] = []
    groups_seen: set = set()
    for kind in _KINDS:
        for w in view.findChildren(kind):
            if not w.isVisible() or w in seen:
                continue
            grp = w.group() if isinstance(w, QAbstractButton) else None
            if grp is not None and grp.exclusive():
                if id(grp) in groups_seen:
                    continue
                groups_seen.add(id(grp))
            seen.append(w)
    return seen


def _make():
    from src.ui.views.bpm_manager_view import BpmManagerView
    v = BpmManagerView()
    v.show()
    _app.processEvents()
    return v


def test_standardansicht_hat_genau_sechs_bedienelemente(_isolated_prefs):
    v = _make()
    try:
        assert not v._advanced.is_expanded()
        ctrls = visible_controls(v)
        assert len(ctrls) == 6, [type(w).__name__ + ":" + getattr(w, "text", lambda: "")() for w in ctrls]
        texts = {getattr(w, "text", lambda: "")() for w in ctrls}
        assert {"TAP", "×½", "×2"} <= texts
        assert any(t.endswith("Erweitert") for t in texts)
        assert v._cmb_source in ctrls
        assert v._btn_auto in ctrls or v._btn_manual in ctrls
        # roh (ohne Gruppenregel): 7 = 6 + zweiter Knopf des Segment-Schalters
        raw = [w for k in _KINDS for w in v.findChildren(k) if w.isVisible()]
        assert len(set(raw)) == 7
    finally:
        v.hide(); v.deleteLater(); _app.processEvents()


def test_erweitert_hat_genau_elf_bedienelemente(_isolated_prefs):
    v = _make()
    try:
        v._advanced.set_expanded(True)
        _app.processEvents()
        ctrls = visible_controls(v)
        assert len(ctrls) == 6 + 11, [type(w).__name__ + ":" + getattr(w, "text", lambda: "")() for w in ctrls]
        for w in (v._sp_min, v._sp_max, v._btn_preset, v._sp_bpb, v._sp_latency,
                  v._btn_lock, v._chk_phase, *v._btn_nudge.values()):
            assert w in ctrls
        assert set(v._btn_nudge) == {-5, -1, 1, 5}          # kein ±10 mehr
        v._advanced.set_expanded(False)
        _app.processEvents()
        assert len(visible_controls(v)) == 6
    finally:
        v.hide(); v.deleteLater(); _app.processEvents()


def test_erweitert_ist_je_sitzung_und_schreibt_keine_prefs(_isolated_prefs):
    v = _make()
    try:
        assert v._advanced._prefs_key is None
        v._advanced.set_expanded(True)
        assert not os.path.exists(_isolated_prefs._PREFS_PATH)
    finally:
        v.hide(); v.deleteLater(); _app.processEvents()


def test_snapshot_timer_laeuft_nur_bei_sichtbarkeit(_isolated_prefs):
    from src.ui.views.bpm_manager_view import POLL_MS
    v = _make()
    try:
        assert v._poll.isActive() and v._poll.interval() == POLL_MS == 50
        v.hide()
        _app.processEvents()
        assert not v._poll.isActive()
        v.show()
        _app.processEvents()
        assert v._poll.isActive()
    finally:
        v.hide(); v.deleteLater(); _app.processEvents()


def test_jedes_bedienelement_hat_einen_tooltip(_isolated_prefs):
    v = _make()
    try:
        v._advanced.set_expanded(True)
        _app.processEvents()
        ohne = [type(w).__name__ + ":" + getattr(w, "text", lambda: "")()
                for w in visible_controls(v) if not w.toolTip().strip()]
        assert ohne == []
    finally:
        v.hide(); v.deleteLater(); _app.processEvents()


def test_kein_get_bpm_in_view_und_helfern():
    files = ["src/ui/views/bpm_manager_view.py", "src/ui/bpm_tap_helper.py",
             "src/ui/bpm_source_controller.py"]
    for rel in files:
        text = open(os.path.join(_REPO, rel), encoding="utf-8").read()
        assert not re.search(r"get_bpm\(", text), f"{rel}: get_bpm( gefunden"


def test_entfallene_bedienelemente_sind_weg(_isolated_prefs):
    v = _make()
    try:
        for name in ("_sl_sens", "_sl_smooth", "_cmb_genre", "_cmb_song", "_cmb_subdiv",
                     "_rb_auto", "_rb_manual", "_rb_kind_live", "_rb_kind_song",
                     "_rb_kind_manual", "_rb_loop", "_rb_input", "_rb_os2l", "_cmb_device"):
            assert not hasattr(v, name), name
        v._advanced.set_expanded(True)
        _app.processEvents()
        # nur Knopf-Beschriftungen (eine Spinbox liefert ihren Wert als text())
        texts = {w.text() for w in visible_controls(v) if isinstance(w, QAbstractButton)}
        assert not ({"4", "8", "16", "+10", "-10", "Anwenden", "↻"} & texts)
    finally:
        v.hide(); v.deleteLater(); _app.processEvents()
