"""CDX-65 (2) — JS-Konsolen-Drossel: die Meldungstabelle waechst bei einer
Fehlerflut mit wechselnden Texten nicht mehr unbegrenzt.

Vorher legte ``melde`` fuer JEDE neue Meldung einen Eintrag an, auch wenn sie
wegen des Gesamtdeckels ohnehin unterdrueckt wurde; ``_MAX_SCHLUESSEL`` griff
erst zu Beginn des naechsten Fensters. 10000 verschiedene Fehler in einem
Fenster hinterliessen 10000 Eintraege. Jetzt gilt die Grenze vor dem Einfuegen,
weitere unterdrueckte Meldungen zaehlen nur im Sammelzaehler.
"""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from src.ui.visualizer import js_konsole as JK   # noqa: E402


class _Uhr:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def _drossel(**kw):
    zeilen: list[str] = []
    uhr = _Uhr()
    w = JK.JsKonsolenWeiterleitung(uhr=uhr, ausgabe=zeilen.append, **kw)
    return w, zeilen, uhr


def test_flut_wechselnder_texte_haelt_die_tabelle_klein():
    w, zeilen, uhr = _drossel()
    for i in range(10000):
        w.melde("FEHLER", f"kaputt {i}", 1, "s.js")
    assert len(w._je_meldung) <= JK.MAX_GESAMT, len(w._je_meldung)
    assert sum(z.startswith("[viz-js:viz]") for z in zeilen) == JK.MAX_GESAMT
    uhr.t += JK.FENSTER_S + 1
    w.melde("FEHLER", "danach", 1, "s.js")
    assert any(f"{10000 - JK.MAX_GESAMT} weitere JS-Meldungen" in z for z in zeilen), zeilen[-3:]
    assert zeilen[-1].endswith("— danach")


def test_harte_grenze_auch_ohne_gesamtdeckel():
    w, zeilen, _ = _drossel(max_gesamt=10 ** 9)
    for i in range(JK._MAX_SCHLUESSEL + 300):
        w.melde("FEHLER", f"x{i}", 1, "s.js")
    assert len(w._je_meldung) <= JK._MAX_SCHLUESSEL
    assert sum("zu viele JS-Meldungen" in z for z in zeilen) == 1


def test_bekannte_meldung_zaehlt_weiter_als_gleiche():
    w, zeilen, uhr = _drossel(max_gleich=2)
    for _ in range(5):
        w.melde("FEHLER", "boom", 3, "s.js")
    uhr.t += JK.FENSTER_S + 1
    w.melde("FEHLER", "boom", 3, "s.js")
    assert zeilen[-1].endswith("(+3 gleiche unterdrueckt)"), zeilen


def test_volle_tabelle_alter_reste_sperrt_neue_meldungen_nicht_dauerhaft():
    """Review CDX-65: Eintraege mit offenem Unterdrueckt-Zaehler wandern ins
    naechste Fenster. Stehen dort genau ``_MAX_SCHLUESSEL`` solche Reste (die
    nie wiederkommen), darf die Tabelle nicht fuer immer voll bleiben — sonst
    kaeme keine einzige neue Meldung mehr ins Log."""
    w, zeilen, uhr = _drossel(max_gleich=1, max_gesamt=10 ** 9)
    for i in range(JK._MAX_SCHLUESSEL):
        w.melde("FEHLER", f"rest {i}", 1, "s.js")
        w.melde("FEHLER", f"rest {i}", 1, "s.js")   # 2. Mal: unterdrueckt
    assert len(w._je_meldung) == JK._MAX_SCHLUESSEL
    for fenster in range(3):
        uhr.t += JK.FENSTER_S + 1
        w.melde("FEHLER", f"neu {fenster}", 1, "s.js")
        assert zeilen[-1].endswith(f"— neu {fenster}"), (fenster, zeilen[-2:])
