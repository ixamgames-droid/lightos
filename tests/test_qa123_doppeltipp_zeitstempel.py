"""QA-123: Warum der UI-114-Doppeltipp-Test in der CI wackelte — und der Beweis,
dass ``tests/_doppeltipp.DruckUhr`` es behebt.

Ursache: Qt erkennt einen Doppelklick nur, wenn der zweite Druck einen *echt
groesseren* Zeitstempel (ganze Millisekunden der Ereignisuhr) traegt als der
erste. ``QTest.touchEvent(...).commit()`` wartet unter PySide nicht; landen
erster Tipp und zweiter Druck in derselben Millisekunde (schneller Rechner),
gibt es keinen Doppelklick. Die Proben hier legen den ersten Tipp gezielt an
den Anfang einer Millisekunde (Hilfsfenster antippen, bis die Uhr springt) —
der schlimmste Fall, den die CI zufaellig traf.
"""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest                                                        # noqa: E402
from PySide6.QtCore import QPoint                                    # noqa: E402
from PySide6.QtTest import QTest                                     # noqa: E402
from PySide6.QtWidgets import QApplication, QListWidget, QWidget     # noqa: E402

from _doppeltipp import DruckUhr                                     # noqa: E402
from _qt_lifecycle import destroy_all_top_level_widgets              # noqa: E402

_app = QApplication.instance() or QApplication([])
_GERAET = QTest.createTouchDevice()


@pytest.fixture(autouse=True)
def _aufraeumen():
    yield
    destroy_all_top_level_widgets(QApplication.instance())


@pytest.fixture
def aufbau():
    hints = QApplication.styleHints()
    alt = hints.mouseDoubleClickInterval()
    uhr = DruckUhr()
    hilfe = QWidget()
    hilfe.resize(60, 60)
    hilfe.move(400, 0)
    hilfe.show()
    liste = QListWidget()
    liste.addItems([f"E {i}" for i in range(10)])
    liste.resize(200, 200)
    liste.show()
    QTest.qWaitForWindowExposed(hilfe)
    QTest.qWaitForWindowExposed(liste)
    doppelt = []
    liste.itemDoubleClicked.connect(lambda it: doppelt.append(it.text()))
    yield uhr, hilfe, liste, doppelt
    hints.setMouseDoubleClickInterval(alt)
    uhr.entfernen()


def _tipp(w, p: QPoint) -> None:
    QTest.touchEvent(w, _GERAET).press(0, p, w).commit()
    QTest.touchEvent(w, _GERAET).release(0, p, w).commit()


def _an_den_ms_anfang(uhr: DruckUhr, hilfe: QWidget) -> None:
    """Hilfsfenster antippen, bis Qts Ereignisuhr auf die naechste ms springt.
    Danach bleibt fast die ganze Millisekunde fuer die eigentlichen Tipps."""
    _tipp(hilfe, QPoint(30, 30))
    start = uhr.zeitstempel[-1]
    while uhr.zeitstempel[-1] == start:
        _tipp(hilfe, QPoint(30, 30))


def _doppeltipp_alt(liste, p: QPoint) -> None:
    """Die alte Form (UI-114/117/121 bis QA-123): Tipp, sofort zweiter Tipp."""
    vp = liste.viewport()
    hints = QApplication.styleHints()
    hints.setMouseDoubleClickInterval(1)
    _tipp(vp, p)
    hints.setMouseDoubleClickInterval(3000)
    _tipp(vp, p)
    QApplication.processEvents()


def test_gleicher_zeitstempel_ist_kein_doppelklick(aufbau):
    """Die Ursache, gezielt erzwungen: zwei Tipps in derselben Millisekunde
    ergeben keinen Doppelklick — auch mit 3 s Doppelklick-Fenster."""
    _probe_gleiche_ms(aufbau, _doppeltipp_alt)


def test_probe_gleiche_ms_haelt_auch_unter_last(aufbau):
    """Nachpruefung QA-123: unter Last liegt ein Paar oft in zwei Millisekunden
    — dann IST es ein Doppelklick und wird uebersprungen. Das darf die Probe
    nicht rot machen (frueher: ``assert doppelt == []`` am Ende, unter Last
    rot). Hier ist das erste Paar gezielt langsam."""
    uhr, _hilfe, _liste, _doppelt = aufbau
    runden = []

    def mal_langsam(liste, p):
        if not runden:          # erste Runde: zweiter Tipp in neuer ms
            vp = liste.viewport()
            hints = QApplication.styleHints()
            hints.setMouseDoubleClickInterval(1)
            _tipp(vp, p)
            hints.setMouseDoubleClickInterval(3000)
            uhr.naechster_zeitstempel()
            _tipp(vp, p)
            QApplication.processEvents()
        else:
            _doppeltipp_alt(liste, p)
        runden.append(1)

    _probe_gleiche_ms(aufbau, mal_langsam)


def test_wartet_nicht_auf_grobe_monotonic_uhr(aufbau, monkeypatch):
    """Nachpruefung QA-123: unter Windows mit Python < 3.13 zaehlt
    ``time.monotonic`` in 15,6-ms-Schritten. Springt sie direkt nach dem Druck,
    darf ``naechster_zeitstempel`` trotzdem nicht zu frueh fertig sein — die
    Hilfe muss eine feine Uhr nutzen. Grobe Uhr hier nachgebaut: erster Wert
    beim Druck, danach sofort ein ganzer Schritt weiter."""
    import time as _time
    uhr, hilfe, liste, doppelt = aufbau
    werte = iter([0.0])
    monkeypatch.setattr(_time, "monotonic", lambda: next(werte, 1.0))
    p = liste.visualItemRect(liste.item(2)).center()
    vp = liste.viewport()
    hints = QApplication.styleHints()
    for runde in range(5):
        _an_den_ms_anfang(uhr, hilfe)
        werte = iter([0.0])
        vorher = len(uhr.zeitstempel)
        hints.setMouseDoubleClickInterval(1)
        _tipp(vp, p)
        hints.setMouseDoubleClickInterval(3000)
        uhr.naechster_zeitstempel()
        _tipp(vp, p)
        QApplication.processEvents()
        erster, zweiter = uhr.zeitstempel[vorher:vorher + 2]
        assert zweiter > erster, f"Runde {runde}: gleicher Zeitstempel {erster}"
        assert len(doppelt) == runde + 1


def _probe_gleiche_ms(aufbau, doppeltipp) -> None:
    uhr, hilfe, liste, doppelt = aufbau
    p = liste.visualItemRect(liste.item(2)).center()
    gleich = 0
    for _ in range(200):
        _an_den_ms_anfang(uhr, hilfe)
        vorher, n, d = len(uhr.zeitstempel), uhr.doppelklicks, len(doppelt)
        doppeltipp(liste, p)
        erster, zweiter = uhr.zeitstempel[vorher:vorher + 2]
        if erster != zweiter:
            continue            # Rechner war zu langsam fuer dieselbe ms
        gleich += 1
        assert uhr.doppelklicks == n, "gleicher Zeitstempel: Qt meldet keinen Doppelklick"
        assert len(doppelt) == d, "gleicher Zeitstempel: kein itemDoubleClicked"
        if gleich >= 3:
            break
    assert gleich >= 3, "die Probe hat den Fall (gleiche ms) nicht erzeugt"


def test_doppeltipp_mit_naechstem_zeitstempel_ist_immer_ein_doppelklick(aufbau):
    """Der Fix: vor dem zweiten Tipp auf den naechsten Zeitstempel warten.
    Ohne das Warten (alte Form) ist diese Probe rot — der erste Tipp liegt
    jedes Mal am Anfang einer Millisekunde."""
    uhr, hilfe, liste, doppelt = aufbau
    p = liste.visualItemRect(liste.item(2)).center()
    vp = liste.viewport()
    hints = QApplication.styleHints()
    for runde in range(20):
        _an_den_ms_anfang(uhr, hilfe)
        vorher = len(uhr.zeitstempel)
        hints.setMouseDoubleClickInterval(1)
        _tipp(vp, p)
        hints.setMouseDoubleClickInterval(3000)
        uhr.naechster_zeitstempel()
        _tipp(vp, p)
        QApplication.processEvents()
        erster, zweiter = uhr.zeitstempel[vorher:vorher + 2]
        assert len(doppelt) == runde + 1, (
            f"Runde {runde}: Doppeltipp erkannt (Zeitstempel {erster} -> {zweiter})")
        assert zweiter > erster
