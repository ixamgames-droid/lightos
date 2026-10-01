"""UI-64 — Programmer- und Playback-Feinschliff.

(a) Programmer ohne Auswahl: der Tab-Hinweis stand doppelt im Reiter — der
    alte Hinweis wurde beim Neuaufbau nur aus dem Layout genommen und blieb
    bis zum (verzoegerten) deleteLater sichtbar stehen.
(b) Hilfetexte „Hervorheben"/„Abdunkeln" versprachen „vorübergehend"; beide
    schreiben aber bleibende Programmer-Werte.
(c) Leerhinweis der Cue-Tabelle nannte „+ Cue", der Knopf heisst
    „+ Cue aufnehmen".
(d) GO-Taste der Executor-Leiste: Grün auf Grün kaum lesbar.
(i) VC-Cueliste bot Executor-Slots 0–19 an, die Executor-Leiste zeigt (und
    belegt) nur Ex 1–10.
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import (QApplication, QDialog, QLabel, QPushButton,
                               QSpinBox)


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _isolate_prefs(tmp_path, monkeypatch):
    import src.ui.views.programmer_view as pv
    monkeypatch.setattr(pv, "_PREFS_DIR", str(tmp_path))
    monkeypatch.setattr(pv, "_PREFS_PATH", str(tmp_path / "ui_prefs.json"))


# ── (a) Leer-Hinweis nur einmal ────────────────────────────────────────────────

def _sichtbare_hinweise(view, cont):
    from src.ui.views.programmer_view import _EMPTY_TAB_HINT
    return [l for l in cont.findChildren(QLabel)
            if l.text() == _EMPTY_TAB_HINT and l.isVisibleTo(view)]


def test_leerhinweis_steht_je_reiter_nur_einmal(tmp_path, monkeypatch):
    app = _app()
    _isolate_prefs(tmp_path, monkeypatch)
    from src.ui.views.programmer_view import ProgrammerView

    pv = ProgrammerView()
    pv.resize(1200, 800)
    pv.show()
    app.processEvents()
    # Neuaufbau OHNE Event-Schleife dazwischen (wie bei schnellem
    # Auswahlwechsel): der alte Hinweis darf nicht stehenbleiben.
    pv._rebuild_attr_editor()
    pv._rebuild_attr_editor()
    app.processEvents()
    for key, cont in pv._attr_group_tabs.items():
        assert len(_sichtbare_hinweise(pv, cont)) <= 1, (
            f"Leer-Hinweis im Reiter {key} mehrfach sichtbar")
    aktiv = pv._main_tabs.currentWidget()
    if aktiv in pv._attr_group_tabs.values():
        assert len(_sichtbare_hinweise(pv, aktiv)) == 1
    pv.close()


# ── (b) Hilfetexte ehrlich ─────────────────────────────────────────────────────

def test_hilfetexte_hervorheben_abdunkeln_ehrlich():
    from src.ui.views.programmer_view import _PROGRAMMER_HELP
    hi = _PROGRAMMER_HELP["Hervorheben"]
    lo = _PROGRAMMER_HELP["Abdunkeln"]
    assert "vorübergehend" not in hi.lower()
    for text in (hi, lo):
        assert "bleiben im Programmer" in text
        assert "Rückgängig" in text
    # Hervorheben: Intensity 255, Weiss, Pan/Tilt Mitte.
    assert "Weiß" in hi and "Pan/Tilt" in hi
    # Abdunkeln: Intensity 76 von 255 = ~30 %, auf alle NICHT gewaehlten.
    assert "30 %" in lo and "NICHT" in lo
    assert round(76 / 255 * 100) == 30


def test_anleitung_nennt_bleibende_werte():
    text = (ROOT / "docs" / "anleitung_programmer_grundlagen"
            / "ANLEITUNG.md").read_text(encoding="utf-8")
    abschnitt = text.split("## 7. Hervorheben und Abdunkeln", 1)[1]
    abschnitt = abschnitt.split("\n## ", 1)[0]
    assert "etwa 30 %" in abschnitt
    assert "bleiben stehen" in abschnitt
    assert "Rückgängig" in abschnitt


# ── (c) Leerhinweis nennt den echten Knopf ─────────────────────────────────────

def _playback_view():
    from src.core.app_state import get_state
    from src.ui.views.playback_view import PlaybackView
    get_state()
    return PlaybackView()


def test_cue_leerhinweis_nennt_knopfbeschriftung():
    _app()
    view = _playback_view()
    knoepfe = [b.text() for b in view.findChildren(QPushButton)
               if b.text().startswith("+ Cue")]
    assert knoepfe == ["+ Cue aufnehmen"]
    assert "„+ Cue aufnehmen\"" in view._table_empty.text()


# ── (d) GO-Taste lesbar ────────────────────────────────────────────────────────

def _luminanz(hexfarbe: str) -> float:
    h = hexfarbe.lstrip("#")
    kan = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    lin = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
           for c in kan]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def _kontrast(a: str, b: str) -> float:
    la, lb = sorted((_luminanz(a), _luminanz(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def test_go_taste_executor_leiste_kontrast():
    _app()
    from src.core.app_state import get_state
    from src.ui.views.playback_view import ExecutorWidget
    ex = ExecutorWidget(1, get_state())
    go = [b for b in ex._fn_buttons if b.text() == "GO"]
    assert go, "GO-Taste fehlt"
    stil = go[0].styleSheet()
    bg = re.search(r"background:\s*(#[0-9a-fA-F]{6})", stil).group(1)
    fg = re.search(r"(?<!-)color:\s*(#[0-9a-fA-F]{6})", stil).group(1)
    # Stil der Leiste bleibt: gruene Taste.
    r, g, b = (int(bg[i:i + 2], 16) for i in (1, 3, 5))
    assert g > r and g > b
    # Kleine 10px-Schrift -> AAA-Kontrast (7:1) statt nur AA; fett.
    assert _kontrast(fg, bg) >= 7.0, f"{fg} auf {bg}: {_kontrast(fg, bg):.2f}"
    assert "font-weight: bold" in stil


# ── (i) VC-Cueliste nur sichtbare Executoren ───────────────────────────────────

def _dialog_spin(widget, monkeypatch, neuer_wert=None):
    """Oeffnet den Eigenschaften-Dialog, liest die Slot-Spinbox aus und setzt
    optional einen Wert (Dialog wird bestaetigt)."""
    gefunden = {}

    def _exec(dlg):
        spin = dlg.findChildren(QSpinBox)[0]
        gefunden.update(min=spin.minimum(), max=spin.maximum(),
                        wert=spin.value(), text=spin.text())
        if neuer_wert is not None:
            spin.setValue(neuer_wert)
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(QDialog, "exec", _exec)
    widget._open_properties()
    return gefunden


def test_vc_cueliste_bietet_nur_sichtbare_executoren(monkeypatch):
    _app()
    from src.ui.virtualconsole.vc_cuelist import VCCueList
    view = _playback_view()
    sichtbar = len(view._executors_widgets)
    assert VCCueList.SICHTBARE_EXECUTOREN == sichtbar

    w = VCCueList()
    w._refresh_timer.stop()
    info = _dialog_spin(w, monkeypatch, neuer_wert=sichtbar)
    assert (info["min"], info["max"]) == (1, sichtbar)
    assert info["wert"] == 1 and info["text"] == "Ex 1"   # Slot 0 = „Ex 1"
    # Gespeichert bleibt der 0-basierte Index -> letzter sichtbarer Executor.
    assert w.stack_slot == sichtbar - 1
    assert w.to_dict()["stack_slot"] == sichtbar - 1


def test_vc_cueliste_alter_hoher_slot_bleibt_erhalten(monkeypatch):
    _app()
    from src.ui.virtualconsole.vc_cuelist import VCCueList
    w = VCCueList()
    w._refresh_timer.stop()
    w.apply_dict({"stack_slot": 14})
    info = _dialog_spin(w, monkeypatch)
    assert info["wert"] == 15
    assert w.stack_slot == 14     # nicht stillschweigend umgebogen
