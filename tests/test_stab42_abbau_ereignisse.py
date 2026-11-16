"""STAB-42: Qt-Ereignisse waehrend des Abbaus eines Widgets.

Befund (UI-143, Raum-Pad): raeumt Pythons Speicherbereinigung ein Widget im
Referenzzyklus ab, leert sie zuerst sein Instanz-Woerterbuch; Qt schickt beim
Zerstoeren des C++-Objekts danach noch ``hideEvent`` & Co. an die
Python-Overrides. Ein Zugriff auf ``self.<attribut>`` wirft dann
``AttributeError`` — und die Ausnahme landet im gerade laufenden Code, etwa im
``paintEvent`` eines anderen Widgets waehrend ``grab()`` (Maler bleibt offen,
nativer Absturz beim Aufraeumen; Kandidat fuer QA-24).

Die Tests hier:

1. Waechter (AST): jedes Override von hideEvent/closeEvent/changeEvent/
   leaveEvent/focusOutEvent in ``src/ui`` traegt ``@abbau_still`` (Ausnahmen
   mit Begruendung in ``AUSNAHMEN``).
2. ``src/ui/abbau.py`` selbst (Kriterium, Aufruf, Rueckgabe, Ausnahmen,
   virtueller Aufruf durch PySide).
3. Abbau-Zustand je Klasse: Instanz bauen, Woerterbuch leeren, jedes
   geschuetzte Ereignis aufrufen -> keine Ausnahme. Und: beim normalen Bauen,
   Zeigen und Verstecken wird nichts uebergangen (gesunde Widgets laufen
   unveraendert).
4. Nachstellung des echten Ablaufs: Widget im Zyklus wird waehrend des
   ``grab()`` eines anderen Widgets eingesammelt.
"""
from __future__ import annotations

import ast
import gc
import os
import pathlib

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QCoreApplication, QEvent  # noqa: E402
from PySide6.QtGui import (QCloseEvent, QFocusEvent, QHideEvent,  # noqa: E402
                           QPainter)
from PySide6.QtWidgets import QApplication, QWidget  # noqa: E402

from src.ui import abbau  # noqa: E402
from src.ui.abbau import abbau_still, abbau_still_filter, im_abbau  # noqa: E402

REPO = pathlib.Path(__file__).resolve().parent.parent
UI = REPO / "src" / "ui"

EREIGNISSE = ("hideEvent", "closeEvent", "changeEvent", "leaveEvent",
              "focusOutEvent")

#: (Datei relativ zu src/ui, Klasse, Methode) -> Begruendung
AUSNAHMEN = {
    ("views/virtual_console_view.py", "_PopoutWindow", "changeEvent"):
        "Klasse ohne __init__: ein GESUNDES Popout hat ein leeres "
        "Woerterbuch, solange _zeige_popout noch keinen Lage-Merker gesetzt "
        "hat (oder dabei scheiterte) — der Schutz wuerde dann das Andocken "
        "verhindern. Braucht ihn nicht: _lage_merker ist Klassenattribut "
        "(None), alles andere kommt aus der Closure (view).",
    ("views/virtual_console_view.py", "_PopoutWindow", "closeEvent"):
        "wie changeEvent (Andocken des Canvas muss immer laufen)",
}

#: eventFilter-Objekte, die ein fremdes Widget halten und nur RuntimeError
#: abfangen (Muster _HaltWaechter) — tragen @abbau_still_filter.
FILTER_GESCHUETZT = {
    ("virtualconsole/vc_handy_leiste.py", "HandyGruppeDialog"),
    ("widgets/mehrfach_knopf.py", "MehrfachKnopf"),
}


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _loeschungen_zustellen():
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    QCoreApplication.processEvents()


# ── 1. Waechter (AST) ────────────────────────────────────────────────────────

def _overrides():
    for p in sorted(UI.rglob("*.py")):
        rel = p.relative_to(UI).as_posix()
        baum = ast.parse(p.read_text(encoding="utf-8-sig"))
        for c in ast.walk(baum):
            if not isinstance(c, ast.ClassDef):
                continue
            for f in c.body:
                if isinstance(f, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    namen = {ast.unparse(d) for d in f.decorator_list}
                    yield rel, c.name, f.name, f.lineno, namen


def test_waechter_jedes_ereignis_override_ist_geschuetzt():
    fehlt, gesehen = [], 0
    for rel, klasse, name, zeile, deko in _overrides():
        if name not in EREIGNISSE:
            continue
        gesehen += 1
        if (rel, klasse, name) in AUSNAHMEN:
            assert "abbau_still" not in deko, (rel, klasse, name)
            continue
        if "abbau_still" not in deko:
            fehlt.append(f"src/ui/{rel}:{zeile} {klasse}.{name}")
    assert gesehen >= 40, gesehen        # Suche findet ueberhaupt etwas
    assert not fehlt, (
        "Ereignis-Override ohne @abbau_still (src/ui/abbau.py, STAB-42) — "
        "im Abbau sind die Attribute schon weg:\n" + "\n".join(fehlt))


def test_waechter_ausnahmen_gibt_es_noch():
    da = {(r, k, n) for r, k, n, _z, _d in _overrides()}
    for schluessel, grund in AUSNAHMEN.items():
        assert schluessel in da, f"Ausnahme veraltet: {schluessel}"
        assert grund


def test_waechter_filter_mit_fremdem_widget_geschuetzt():
    gefunden = set()
    for rel, klasse, name, _z, deko in _overrides():
        if name == "eventFilter" and (rel, klasse) in FILTER_GESCHUETZT:
            assert "abbau_still_filter" in deko, (rel, klasse)
            gefunden.add((rel, klasse))
    assert gefunden == FILTER_GESCHUETZT


# ── 2. Der Dekorator selbst ──────────────────────────────────────────────────

class _Probe:
    def __init__(self):
        self.wert = 1
        self.aufrufe = []

    @abbau_still
    def hideEvent(self, ereignis, *rest, **kw):          # noqa: N802
        self.aufrufe.append((ereignis, rest, kw))
        return ("ergebnis", self.wert)

    @abbau_still
    def closeEvent(self, ereignis):                      # noqa: N802
        raise ValueError(f"echter Fehler {self.wert}")

    @abbau_still_filter
    def eventFilter(self, obj, ev):                      # noqa: N802
        return self.wert == 1


def test_gesundes_objekt_ruft_override_unveraendert():
    p = _Probe()
    assert p.hideEvent("e", 2, x=3) == ("ergebnis", 1)
    assert p.aufrufe == [("e", (2,), {"x": 3})]
    assert p.eventFilter(None, None) is True
    assert not im_abbau(p)


def test_leeres_woerterbuch_override_wird_nicht_gerufen():
    p = _Probe()
    aufrufe = p.aufrufe
    vorher = abbau.uebergangen
    p.__dict__.clear()
    assert im_abbau(p)
    assert p.hideEvent("e") is None
    assert aufrufe == []
    assert p.closeEvent("e") is None     # wirft im Abbau nicht
    assert p.eventFilter(None, None) is False
    assert abbau.uebergangen == vorher + 3


def test_echter_fehler_im_gesunden_objekt_bleibt_laut():
    with pytest.raises(ValueError, match="echter Fehler 1"):
        _Probe().closeEvent("e")


def test_metadaten_bleiben_erhalten():
    assert _Probe.hideEvent.__name__ == "hideEvent"
    assert _Probe.hideEvent.__wrapped__.__name__ == "hideEvent"
    assert _Probe.hideEvent.__abbau_still__ is True


def test_ungueltiges_qt_objekt_gilt_als_abbau(app):
    import shiboken6
    w = QWidget()
    w._x = 1
    assert not im_abbau(w)
    shiboken6.delete(w)
    assert im_abbau(w)


def test_pyside_ruft_dekoriertes_override_virtuell(app):
    class W(QWidget):
        def __init__(self):
            super().__init__()
            self.log = []

        @abbau_still
        def hideEvent(self, e):                          # noqa: N802
            self.log.append("hide")
            super().hideEvent(e)

        @abbau_still
        def changeEvent(self, e):                        # noqa: N802
            if e.type() == QEvent.Type.WindowTitleChange:
                self.log.append("titel")
            super().changeEvent(e)

    w = W()
    w.show()
    app.processEvents()
    w.setWindowTitle("x")
    w.hide()
    assert w.log == ["titel", "hide"]
    w.deleteLater()
    _loeschungen_zustellen()


# ── 3. Abbau-Zustand je Klasse ───────────────────────────────────────────────

def _bauer(tmp_path):
    """name -> Funktion, die eine Instanz baut (alles ohne echte App-Daten)."""
    def spectrum():
        from src.ui.views.spectrum_bars import SpectrumBars
        return SpectrumBars(bands=8)

    def farbliste():
        from src.ui.virtualconsole.vc_color_list import VCColorList
        return VCColorList()

    def effektanzeige():
        from src.ui.virtualconsole.vc_effect_display import VCEffectDisplay
        return VCEffectDisplay()

    def knopf():
        from src.ui.virtualconsole.vc_button import VCButton
        return VCButton("X")

    def raumpad():
        from src.ui.virtualconsole.vc_raumpad import VCRaumPad
        return VCRaumPad()

    def bpm_anzeige():
        from src.ui.virtualconsole.vc_bpm_display import VCBpmDisplay
        return VCBpmDisplay()

    def executor():
        from src.core.app_state import get_state
        from src.ui.views.playback_view import ExecutorWidget
        return ExecutorWidget(1, get_state())

    def fernsteuerung():
        from src.ui.widgets.dmx_fernsteuerung_box import FernsteuerungBox
        return FernsteuerungBox(None, pfad=str(tmp_path / "fs.json"))

    def osc():
        from src.ui.widgets.osc_einstellungen_dialog import \
            OscEinstellungenDialog
        return OscEinstellungenDialog(None, pfad=str(tmp_path / "osc.json"),
                                      server_laeuft=True)

    def tempo_bus():
        from src.ui.views.tempo_bus_view import TempoBusView
        return TempoBusView()

    def mehrfach():
        from PySide6.QtWidgets import QListWidget
        from src.ui.widgets.mehrfach_knopf import MehrfachKnopf
        liste = QListWidget()
        k = MehrfachKnopf(liste)
        k._stab42_liste = liste           # Liste lebt so lange wie der Knopf
        return k

    def handy_gruppe():
        from src.ui.virtualconsole.vc_handy_leiste import HandyGruppeDialog
        return HandyGruppeDialog("Gruppe 1", [])

    def handy_qr():
        from src.ui.widgets.handy_qr import HandyQrFeld
        return HandyQrFeld(klein=True)

    return {
        "SpectrumBars": spectrum, "VCColorList": farbliste,
        "VCEffectDisplay": effektanzeige, "VCButton": knopf,
        "VCRaumPad": raumpad, "VCBpmDisplay": bpm_anzeige,
        "ExecutorWidget": executor, "FernsteuerungBox": fernsteuerung,
        "OscEinstellungenDialog": osc, "TempoBusView": tempo_bus,
        "MehrfachKnopf": mehrfach, "HandyGruppeDialog": handy_gruppe,
        "HandyQrFeld": handy_qr,
    }


KLASSEN = ["SpectrumBars", "VCColorList", "VCEffectDisplay", "VCButton",
           "VCRaumPad", "VCBpmDisplay", "ExecutorWidget", "FernsteuerungBox",
           "OscEinstellungenDialog", "TempoBusView", "MehrfachKnopf",
           "HandyGruppeDialog", "HandyQrFeld"]


def _geschuetzte(obj):
    """Alle geschuetzten Methoden der Klasse (ueber die ganze MRO)."""
    namen = set()
    for k in type(obj).__mro__:
        for n, v in vars(k).items():
            if getattr(v, "__abbau_still__", False):
                namen.add(n)
    return sorted(namen)


def _ereignisse(name, obj):
    if name == "hideEvent":
        return [QHideEvent()]
    if name == "closeEvent":
        return [QCloseEvent()]
    if name == "changeEvent":
        return [QEvent(t) for t in (QEvent.Type.ActivationChange,
                                    QEvent.Type.StyleChange,
                                    QEvent.Type.FontChange,
                                    QEvent.Type.WindowStateChange)]
    if name == "leaveEvent":
        return [QEvent(QEvent.Type.Leave)]
    if name == "focusOutEvent":
        return [QFocusEvent(QEvent.Type.FocusOut)]
    raise AssertionError(name)


def _aufraeumen(w):
    try:
        w.hide()
        w.deleteLater()
    except RuntimeError:
        pass
    _loeschungen_zustellen()


@pytest.mark.parametrize("name", KLASSEN)
def test_gesund_bauen_zeigen_verstecken_uebergeht_nichts(app, tmp_path, name):
    """Ein gesundes Widget hat ab dem Bauen Attribute: beim normalen Bauen,
    Zeigen, Titel/Schrift aendern und Verstecken greift der Schutz nie."""
    gc.disable()
    try:
        vorher = abbau.uebergangen
        w = _bauer(tmp_path)[name]()
        assert vars(w), "gesundes Widget ohne Attribute — Kriterium passt nicht"
        w.show()
        app.processEvents()
        w.setWindowTitle("STAB-42")
        w.setStyleSheet("QWidget { font-size: 13px; }")
        app.processEvents()
        w.hide()
        app.processEvents()
        assert abbau.uebergangen == vorher
    finally:
        gc.enable()
    _aufraeumen(w)


@pytest.mark.parametrize("name", KLASSEN)
def test_im_abbau_wirft_kein_geschuetztes_ereignis(app, tmp_path, name):
    w = _bauer(tmp_path)[name]()
    w.show()
    app.processEvents()
    namen = _geschuetzte(w)
    assert namen, f"{name}: kein geschuetztes Ereignis gefunden"
    gemerkt = dict(vars(w))
    vorher = abbau.uebergangen
    w.__dict__.clear()                    # so sieht es im Abbau aus
    try:
        n = 0
        for m in namen:
            meth = getattr(w, m)
            if m == "eventFilter":
                assert meth(w, QEvent(QEvent.Type.Resize)) is False
                n += 1
                continue
            for ev in _ereignisse(m, w):
                assert meth(ev) is None
                n += 1
        assert abbau.uebergangen == vorher + n
    finally:
        w.__dict__.update(gemerkt)
    _aufraeumen(w)


def test_ohne_schutz_wuerde_es_werfen(app, tmp_path):
    """Gegenprobe: dieselben Overrides OHNE den Schutz werfen im Abbau —
    der Schutz verdeckt also eine echte Luecke."""
    werfen = []
    for name in KLASSEN:
        w = _bauer(tmp_path)[name]()
        gemerkt = dict(vars(w))
        w.__dict__.clear()
        try:
            for m in _geschuetzte(w):
                if m == "eventFilter":
                    continue
                roh = getattr(type(w), m).__wrapped__
                for ev in _ereignisse(m, w):
                    try:
                        roh(w, ev)
                    except AttributeError:
                        werfen.append(f"{name}.{m}")
                        break
        finally:
            w.__dict__.update(gemerkt)
        _aufraeumen(w)
    assert len(set(werfen)) >= 5, werfen


# ── 4. Der echte Ablauf ──────────────────────────────────────────────────────

def test_einsammeln_waehrend_grab_eines_anderen_widgets(app, capfd):
    """Eltern + Kind (echte Klasse, VCEffectDisplay) im Referenzzyklus werden
    eingesammelt, waehrend ein ANDERES Widget in ``grab()`` malt. Qt schickt
    dem Kind beim Zerstoeren ein hideEvent — dessen Woerterbuch ist da schon
    leer. Ohne Schutz kam der AttributeError im paintEvent an."""
    from src.ui.virtualconsole.vc_effect_display import VCEffectDisplay

    def muell_bauen():
        eltern = QWidget()
        kind = VCEffectDisplay()
        kind.setParent(eltern)
        kind._stab42_eltern = eltern      # Zyklus Kind <-> Eltern
        eltern._stab42_kind = kind
        eltern.show()
        app.processEvents()
        assert kind.isVisible()

    befund = {}

    class Maler(QWidget):
        def __init__(self):
            super().__init__()
            self.resize(60, 40)

        def paintEvent(self, ev):                        # noqa: N802
            p = QPainter(self)
            try:
                vorher = abbau.uebergangen
                gc.collect()               # Speicherbereinigung mitten im Malen
                befund["uebergangen"] = abbau.uebergangen - vorher
            except BaseException as e:     # pragma: no cover - der Fehlerfall
                befund["fehler"] = repr(e)
            finally:
                p.end()
                befund["maler_offen"] = p.isActive()

    gc.collect()
    m = Maler()
    m.show()
    app.processEvents()
    capfd.readouterr()
    gc.disable()
    try:
        muell_bauen()
        bild = m.grab()
    finally:
        gc.enable()
    fehler = capfd.readouterr().err
    assert "fehler" not in befund, befund
    assert befund.get("maler_offen") is False
    assert befund.get("uebergangen", 0) >= 1, befund   # der Fall trat ein
    assert not bild.isNull()
    assert "Error calling Python override" not in fehler, fehler
    assert "AttributeError" not in fehler, fehler
    assert "Cannot destroy paint device" not in fehler, fehler
    m.deleteLater()
    _loeschungen_zustellen()
