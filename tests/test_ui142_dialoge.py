"""UI-142: Klick-Test 16.11.2026 — Dialoge (BPM-Generator, MVR-Import,
Sprachmix, Fehlertext der BPM-Erkennung).

* **Fund 1** BPM-Generator bei 1280x800 (Touch): der Plot schrumpfte fast auf
  null, die Beatgrid-Knoepfe lagen im Plotfeld. Jetzt scrollt die Seite, der
  Plot behaelt seine Mindesthoehe und kein Knopf liegt auf ihm.
* **Fund 2** MVR-Import: die Status-Spalte lag ausserhalb der Sicht, und aus
  einem Adresskonflikt fuehrte nur die Wahl Zeile fuer Zeile. Jetzt steht der
  Status neben „Konflikt“ und bricht um, ueber der Tabelle stehen „Alle
  Konflikte: überspringen / auf freie Adresse“ und ein Hinweis, wenn nichts
  angelegt wuerde. Vorhandene Geraete werden nie veraendert.
* **Fund 3** Sprachmix: Channel-Modifier, Chaser-Editor und Input-Profile
  sprechen Deutsch (Kennlinie, Universum, Adresse; Ablauf, Richtung; Kanal,
  Aktion, Parameter).
* **Fund 4** BPM-Erkennung ohne Audio: Haupttext nennt den naechsten Schritt
  („Kein Audioeingang“ — OS2L/Lied-Analyse oder TAP), die Technik steht im
  Tooltip.
"""
from __future__ import annotations

import os
from dataclasses import replace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest                                                        # noqa: E402
from PySide6.QtCore import QPoint, QRect                             # noqa: E402
from PySide6.QtWidgets import (                                      # noqa: E402
    QApplication, QComboBox, QLabel, QPushButton, QTableWidget, QWidget,
)

from src.ui import touch_keyboard as tk                              # noqa: E402
from _qt_lifecycle import destroy_all_top_level_widgets              # noqa: E402

_app = QApplication.instance() or QApplication([])


def _ruhe(n=6):
    for _ in range(n):
        QApplication.processEvents()


@pytest.fixture(autouse=True)
def _aufraeumen():
    alt = tk.is_touch_mode()
    yield
    tk.setze_touch_modus(alt)
    destroy_all_top_level_widgets(_app)


def _rect_in(widget, bezug) -> QRect:
    oben_links = widget.mapTo(bezug, QPoint(0, 0))
    return QRect(oben_links, widget.size())


# ── Fund 1: BPM-Generator ───────────────────────────────────────────────────

@pytest.mark.parametrize("touch", [False, True], ids=["maus", "touch"])
@pytest.mark.parametrize("hoehe", [585, 420])
def test_generator_plot_wird_nicht_von_knoepfen_verdeckt(touch, hoehe):
    """1280x800: unter Menue, Kopfleiste und Reitern bleiben ~585 px fuer die
    Seite. Der Plot behaelt seine Mindesthoehe, kein Knopf liegt in ihm."""
    from src.ui.views.bpm_generator_view import BpmGeneratorView
    tk.setze_touch_modus(touch)
    rahmen = QWidget()
    if touch:
        rahmen.setStyleSheet(tk.touch_qss())
    v = BpmGeneratorView(rahmen)
    v.setGeometry(0, 0, 1280, hoehe)
    rahmen.resize(1280, hoehe)
    rahmen.show()
    _ruhe()
    plot = v._plot
    assert plot.isVisible()
    assert plot.height() >= 180
    p = _rect_in(plot, v)
    knoepfe = [b for b in v.findChildren(QPushButton) if b.isVisible()]
    assert knoepfe
    for b in knoepfe:
        assert not _rect_in(b, v).intersects(p), b.text()
    # Die Knopfzeilen liegen unter dem Plot und sind (per Scrollen) erreichbar
    for b in (v._btn_use, v._btn_export, v._btn_preview):
        assert _rect_in(b, v).top() >= p.bottom()


# ── Fund 2: MVR-Import ──────────────────────────────────────────────────────

from test_viz56_mvr_import import (  # noqa: E402,F401
    PAR, bib, fixture_xml, gdtf_bytes, gdtf_xml, mvr_schreiben, state, szene_xml,
)


def _konflikt_datei(tmp_path, n=4):
    """``n`` PARs (8 Kanaele) auf 1.1, 1.9, … — der Patch belegt 1.1–1.40."""
    par = gdtf_bytes(gdtf_xml("Generic", "stage light  zq01424",
                              [("8-Kanal RGBW", [(str(i), "Dimmer", "Base")
                                                 for i in range(1, 9)])]))
    inhalt = "".join(fixture_xml(f"PAR {i + 1}", None, "par.gdtf", "8-Kanal RGBW",
                                 f"1.{1 + 8 * i}", str(200 + i)) for i in range(n))
    from src.core.mvr import lesen as L
    return L.lies_mvr(mvr_schreiben(tmp_path / "konflikt.mvr", szene_xml(inhalt),
                                    {"par.gdtf": par}))


def _belegt(state, bib, bis=40):
    from src.core.database.models import PatchedFixture
    par = bib.finde("Generic", PAR).profil
    for i, a in enumerate(range(1, bis, 8)):
        state.add_fixture(PatchedFixture(
            fid=1 + i, label=f"Alt {i + 1}", fixture_profile_id=par.id,
            mode_name="8-Kanal RGBW", universe=1, address=a, channel_count=8,
            manufacturer_name="Generic", fixture_name=PAR, fixture_type="par"),
            undoable=False)


def _bild(state):
    return sorted((f.fid, f.label, f.universe, f.address)
                  for f in state.get_patched_fixtures())


def _dialog(tmp_path, state, bib):
    from src.ui.widgets import mvr_import_dialog as D
    _belegt(state, bib)
    dlg = D.MvrImportDialog(state, _konflikt_datei(tmp_path), bib, "rig.mvr")
    return D, dlg


def test_mvr_status_steht_neben_konflikt_und_ist_ganz_zu_sehen(tmp_path, bib, state):
    from src.core.mvr import importieren as I
    D, dlg = _dialog(tmp_path, state, bib)
    assert D.S_STATUS == D.S_KONFLIKT + 1
    assert D.SPALTEN[D.S_STATUS] == "Status" and D.SPALTEN[D.S_KONFLIKT] == "Konflikt"
    dlg.show()
    _ruhe()
    t = dlg.tabelle
    vp = t.viewport().width()
    # Ganz in der Sicht (ohne Waagrecht-Scrollen) und breit genug fuer Text
    x = t.columnViewportPosition(D.S_STATUS)
    assert x >= 0 and x + t.columnWidth(D.S_STATUS) <= vp + 1
    assert t.columnWidth(D.S_STATUS) >= 220
    assert t.horizontalScrollBar().value() == 0
    # Text bricht um: die Zeile ist hoch genug fuer den ganzen Status
    assert t.wordWrap()
    e = dlg.plan.eintraege[0]
    assert e.status == I.UEBERSPRUNGEN
    text = t.item(0, D.S_STATUS).text()
    fm = t.fontMetrics()
    noetig = fm.boundingRect(QRect(0, 0, t.columnWidth(D.S_STATUS) - 8, 10000),
                             0x1000, text).height()   # Qt.TextWordWrap
    assert t.rowHeight(0) >= min(noetig, 200)
    assert t.rowHeight(0) < 100        # nicht nach der Anfangsbreite bemessen
    # Kopf ungekuerzt
    kopf = t.horizontalHeader()
    assert kopf.sectionSize(D.S_STATUS) >= fm.horizontalAdvance("Status") + 12


def test_mvr_hinweis_und_sammelwahl_fuehren_aus_dem_konflikt(tmp_path, bib, state):
    from src.core.mvr import importieren as I
    D, dlg = _dialog(tmp_path, state, bib)
    vorher = _bild(state)
    dlg.show()
    _ruhe()
    # Ausgangslage: alles uebersprungen, Importieren grau, Hinweis sichtbar
    assert not dlg.plan.anlegbare()
    assert not dlg.knopf_importieren.isEnabled()
    assert dlg.hinweis_konflikt.isVisible()
    assert "auf freie Adresse" in dlg.hinweis_konflikt.text()
    assert dlg.knopf_alle_frei.isEnabled() and dlg.knopf_alle_frei.isVisible()
    # Sammelwahl: alle auf freie Adresse
    dlg.knopf_alle_frei.click()
    _ruhe()
    assert len(dlg.plan.anlegbare()) == 4
    adressen = [(e.universum, e.adresse) for e in dlg.plan.eintraege]
    assert all(a is not None and a >= 41 for _u, a in adressen)
    assert len(set(adressen)) == 4
    assert all(dlg._konflikt_auswahl[r].currentData() == I.FREIE_ADRESSE
               for r in range(4))
    assert dlg.knopf_importieren.isEnabled()
    assert not dlg.hinweis_konflikt.isVisible()
    # Einzelne Zeile bleibt waehlbar
    cb = dlg._konflikt_auswahl[1]
    cb.setCurrentIndex(cb.findData(I.UEBERSPRINGEN))
    assert len(dlg.plan.anlegbare()) == 3
    # Sammelwahl zurueck: alle ueberspringen
    dlg.knopf_alle_ueberspringen.click()
    assert not dlg.plan.anlegbare()
    # Nichts wurde still ueberschrieben: der Patch ist unveraendert
    assert _bild(state) == vorher


def test_mvr_ohne_konflikt_keine_sammelwahl(tmp_path, bib, state):
    from src.ui.widgets import mvr_import_dialog as D
    dlg = D.MvrImportDialog(state, _konflikt_datei(tmp_path), bib, "rig.mvr")
    dlg.show()
    _ruhe()
    assert len(dlg.plan.anlegbare()) == 4
    assert not dlg.hinweis_konflikt.isVisible()
    assert not dlg.knopf_alle_frei.isEnabled()
    assert not dlg.knopf_alle_ueberspringen.isEnabled()


# ── Fund 3: Sprachmix ───────────────────────────────────────────────────────

_ENGLISCH = ("Curve", "Universe", "Add:", "U:", "Adr:", "Channel", "Action",
             "Param", "Run Order", "Direction", "Speed")


def _sichtbare_texte(w) -> list[str]:
    texte = [lb.text() for lb in w.findChildren(QLabel)]
    for t in w.findChildren(QTableWidget):
        texte += [t.horizontalHeaderItem(s).text() for s in range(t.columnCount())
                  if t.horizontalHeaderItem(s) is not None]
    return texte


def _ohne_englisch(texte):
    import re
    schlecht = []
    for t in texte:
        for wort in _ENGLISCH:
            if re.search(r"(?<![\w-])" + re.escape(wort) + r"(?![\w])", t):
                schlecht.append((wort, t))
    return schlecht


def test_channel_modifier_spricht_deutsch():
    from src.ui.widgets.channel_modifier_dialog import ChannelModifierDialog
    d = ChannelModifierDialog()
    texte = _sichtbare_texte(d)
    assert _ohne_englisch(texte) == []
    kopf = [d._table.horizontalHeaderItem(s).text() for s in range(4)]
    assert kopf == ["Universum", "Adresse", "Kennlinie", "Name"]
    joined = " ".join(texte)
    assert "Kennlinie" in joined and "DMX-Kanal" in joined


def test_input_profil_editor_spricht_deutsch():
    from src.ui.widgets.input_profile_editor import InputProfileEditor
    ed = InputProfileEditor()
    kopf = [ed._table.horizontalHeaderItem(s).text()
            for s in range(ed._table.columnCount())]
    assert "Kanal" in kopf and "Aktion" in kopf and "Parameter" in kopf
    assert _ohne_englisch(kopf) == []


def test_chaser_editor_spricht_deutsch():
    from src.core.engine.function import Direction
    from src.ui.views import chaser_editor as CE
    quelle = open(CE.__file__, encoding="utf-8").read()
    for alt in ('"Run Order:"', '"Direction:"', '"Speed:"'):
        assert alt not in quelle
    for neu in ('"Ablauf:"', '"Richtung:"', '"Geschwindigkeit:"'):
        assert neu in quelle
    # Richtung zeigt deutsche Woerter, speichert weiter den Enum-Wert
    assert CE.RICHTUNG_TEXT[Direction.Forward] == "Vorwärts"
    assert CE.RICHTUNG_TEXT[Direction.Backward] == "Rückwärts"


# ── Fund 4: Fehlertext der BPM-Erkennung ────────────────────────────────────

from src.ui.bpm_status_rules import MgrState, status_line    # noqa: E402

_IN = MgrState(kind="input", device_label="USB Audio CODEC", bpm=128.0)


@pytest.mark.parametrize("grund", ["server", "bibliothek", "paket", None])
def test_audio_fehlt_nennt_naechsten_schritt(grund):
    line = status_line(None, None, replace(_IN, audio_available=False, audio_grund=grund),
                       None, 0)
    assert line.problem == "Kein Audioeingang"
    assert "TAP" in line.abhilfe and "OS2L" in line.abhilfe
    assert line.aktion == "source"
    sichtbar = line.text
    for technik in ("pactl", "PulseAudio", "sudo", "pip install", "(Paket ist installiert)"):
        assert technik not in sichtbar
    assert line.details and "neu starten" in line.details


from test_bpm_view_status import (  # noqa: E402,F401
    _isolated_prefs, _tick, env,
)


def test_audio_server_details_im_tooltip(env, monkeypatch):
    line = status_line(None, None, replace(_IN, audio_available=False, audio_grund="server"),
                       None, 0)
    assert "pactl info" in line.details and "Audiodienst" in line.details
    import src.core.audio.capture as cap_mod
    make, cap, clock, det = env
    monkeypatch.setattr(cap_mod, "HAS_SOUNDCARD", False)
    monkeypatch.setattr(cap_mod, "AUDIO_FEHLT_GRUND", "server", raising=False)
    v, *_ = make()
    txt = _tick(v, clock, 0.0)
    assert txt.startswith("Kein Audioeingang")
    sichtbar = v._lbl_problem.text() + v._lbl_ursache.text() + v._lbl_abhilfe.text()
    assert "pactl" not in sichtbar and "TAP" in sichtbar
    for w in (v._lbl_problem, v._lbl_ursache, v._lbl_abhilfe):
        assert "pactl info" in w.toolTip()
    # Problem behoben: wieder die normalen Tooltips
    monkeypatch.setattr(cap_mod, "HAS_SOUNDCARD", True)
    _tick(v, clock, 10.0)
    assert "pactl" not in v._lbl_problem.toolTip()
    assert v._lbl_problem.toolTip() == "Was los ist."
