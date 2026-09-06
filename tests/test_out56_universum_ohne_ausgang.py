"""OUT-56: ein gepatchtes Universum OHNE Ausgang stand in keiner Statusleiste.

**Der Backlog-Eintrag behauptete drei Dinge; zwei davon stimmen nicht mehr.**
Nachgemessen am laufenden Code am 2026-09-06:

* ⚠️ „wird in der laufenden App **nirgends** gemeldet" — falsch seit OUT-52
  (`f963f762`, 2026-08-11), also **20 Tage bevor der Fund aufgenommen wurde**.
  `dmx_monitor_view.py` traegt woertlich ``⚠ Universe {n} hat keinen Ausgang —
  nur gerechnet``. Nur sieht man es erst, wenn man den DMX-Monitor oeffnet
  **und** dort genau dieses Universum waehlt (Vorgabe ist U1).
* ⚠️ „`enttec_port_notes` gehoert in dieselbe Anzeige gehoben" (mein eigenes
  korrigiertes Kriterium) — bereits erledigt: `_lbl_enttec` ist ein permanentes
  Statusleisten-Widget und zeigt „Enttec: falsch konfiguriert" samt Befund
  (HW-5b, `main_window.py`). Und ein registrierter Adapter, der nicht sendet,
  kommt ueber `ausgabe_status()['verbunden'] is False` an (OUT-51).

★★★ **Uebrig blieb genau eine Luecke — und die ist echt.** Die IMMER sichtbare
Ausgabe-Anzeige schweigt zu einem Universum, in dem Geraete gepatcht sind, das
aber gar keinen Adapter hat. Und zwar nicht aus Nachlaessigkeit: die beiden
Quellen, aus denen sie ihren Text baut, kennen es ueberhaupt nicht. Gemessen
mit sACN auf U1 und Geraeten in U1 **und** U3::

    sendet_wirklich   {1: True, 3: False}
    ausgabe_status()  [(1, 'sACN')]        <- U3 fehlt
    sende_probleme()  []                   <- U3 fehlt

Die Anzeige konnte es nicht verschweigen — sie konnte es nicht wissen.

★ **Und eine Lehre vom selben Tag, gleich angewandt:** die Entscheidung sass in
einer `MainWindow`-Methode und war nur pruefbar, indem man ein ganzes Fenster
baut. Bei ENG-23 hat genau das den Renderer mitgerissen. Sie steht jetzt als
reine Funktion in `src/ui/ausgabe_label.py` — *eine Anzeige-Regel gehoert
dorthin, wo man sie befragen kann, ohne sie zu malen.*
"""
from __future__ import annotations

import os
import sys
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.ui.ausgabe_label import (  # noqa: E402
    FARBE_FEHLT, FARBE_KAPUTT, FARBE_NORMAL, MAX_IM_TEXT, ausgabe_label)


def _weg(univ, weg="sACN", ziel="", verbunden=None, problem=None):
    return {"universum": univ, "weg": weg, "ziel": ziel,
            "verbunden": verbunden, "problem": problem}


class DieAnzeigeMeldetDasFehlendeTest(unittest.TestCase):

    def test_ein_universum_ohne_ausgang_erscheint(self):
        """★★★ Der Kern: U3 hat Geraete, aber keinen Adapter."""
        text, farbe, tip = ausgabe_label([_weg(1)], [], [3])
        self.assertIn("U3", text)
        self.assertIn("ohne Ausgang", text)
        self.assertTrue(text.startswith("⚠"))
        self.assertEqual(farbe, FARBE_FEHLT)
        self.assertIn("nur gerechnet", tip)

    def test_der_tooltip_sagt_was_zu_tun_ist(self):
        """Ein Hinweis, der nicht sagt, wohin man klicken soll, kostet dieselbe
        Stunde Fehlersuche noch einmal (vgl. OUT-53/54)."""
        _t, _f, tip = ausgabe_label([_weg(1)], [], [3])
        self.assertIn("Output-Einstellungen", tip)

    def test_das_fehlende_steht_VORNE(self):
        """★★ Der Text zeigt nur die ersten drei Eintraege. Bei einem
        groesseren Rig waere das stumme Universum sonst genau das, was man nicht
        sieht, waehrend drei funktionierende Platz wegnehmen."""
        wege = [_weg(u) for u in (1, 2, 4, 5)]
        text, _f, _t = ausgabe_label(wege, [], [9])
        self.assertLess(text.index("U9"), text.index("U1"))
        self.assertIn(f"+{1 + len(wege) - MAX_IM_TEXT}", text)

    def test_kaputt_steht_vor_gesund(self):
        """Die bestehende OUT-51-Reihenfolge bleibt erhalten."""
        wege = [_weg(1), _weg(7, "Enttec", verbunden=False, problem="Port weg")]
        text, farbe, _t = ausgabe_label(wege, [], [])
        self.assertLess(text.index("U7"), text.index("U1"))
        self.assertEqual(farbe, FARBE_KAPUTT)

    def test_kaputt_und_fehlend_zusammen(self):
        """★ Rot schlaegt Orange — „ist kaputt" ist dringender als „fehlt".
        Genannt werden trotzdem beide."""
        wege = [_weg(1), _weg(7, "Enttec", verbunden=False, problem="Port weg")]
        text, farbe, tip = ausgabe_label(wege, [], [3])
        self.assertEqual(farbe, FARBE_KAPUTT)
        self.assertIn("U3", tip)
        self.assertIn("U7", tip)
        self.assertIn("U3", text)

    def test_alle_universen_ohne_ausgang_werden_genannt(self):
        _t, _f, tip = ausgabe_label([], [], [1, 3, 5])
        for u in (1, 3, 5):
            self.assertIn(f"U{u}:", tip)


class WasSichNichtAendernDarfTest(unittest.TestCase):
    """Die Zaeune um den Zusatz herum — OUT-51 und OUT-52 bleiben, wie sie sind."""

    def test_der_gute_fall_bleibt_unauffaellig(self):
        """★★ Die wichtigste Gegenprobe. Eine Anzeige, die immer warnt, warnt
        nicht mehr — dann sieht niemand mehr hin, wenn es ernst wird."""
        text, farbe, tip = ausgabe_label(
            [_weg(1, "sACN", "239.255.0.1", verbunden=True)], [], [])
        self.assertEqual(farbe, FARBE_NORMAL)
        self.assertFalse(text.startswith("⚠"))
        self.assertIn("239.255.0.1", tip)

    def test_ein_universum_MIT_ausgang_wird_nicht_gemeldet(self):
        """Die Gegenrichtung zum Kern: was rausgeht, ist kein Befund."""
        text, farbe, _t = ausgabe_label([_weg(3)], [], [])
        self.assertEqual(farbe, FARBE_NORMAL)
        self.assertNotIn("ohne Ausgang", text)

    def test_gar_nichts_konfiguriert_meldet_wie_bisher(self):
        text, farbe, tip = ausgabe_label([], [], [])
        self.assertEqual(text, "Ausgabe: —")
        self.assertEqual(farbe, FARBE_FEHLT)
        self.assertIn("Kein Universum", tip)

    def test_tick_und_modifier_stoerungen_bleiben_sichtbar(self):
        """OUT-51: die haengen an keinem Ausgang und wuerden in `wege` fehlen."""
        probleme = [{"weg": "Tick", "universum": 0, "fehler": 12, "text": "boom"}]
        text, farbe, tip = ausgabe_label([_weg(1)], probleme, [])
        self.assertEqual(farbe, FARBE_KAPUTT)
        self.assertIn("Tick", tip)
        self.assertTrue(text.startswith("⚠"))

    def test_ein_adapter_ohne_auskunft_gilt_nicht_als_kaputt(self):
        """``verbunden is None`` heisst „kann keine Auskunft geben" (UDP). Wer
        daraus rot macht, meldet Ausfaelle, die es nicht gibt — und wer daraus
        gruen macht, meldet Erfolg, weil er nichts weiss. Hier: nicht kaputt."""
        text, farbe, _t = ausgabe_label([_weg(1, verbunden=None)], [], [])
        self.assertEqual(farbe, FARBE_NORMAL)
        self.assertFalse(text.startswith("⚠"))


class DasFensterFragtDasRichtigeTest(unittest.TestCase):
    """★★ Die Verdrahtung — ohne ein Hauptfenster zu bauen.

    Ein Test, der nur die reine Funktion prueft, sagt nichts darueber, ob das
    Fenster sie mit den richtigen Daten fuettert. Genau diese Luecke hat bei
    ENG-23 vier blinde Tests erzeugt: eine Probe, die ihren Gegenstand nicht
    erreicht, meldet „alles gut".
    """

    def _fenster(self, gepatchte_universen, mit_ausgang):
        from src.ui.main_window import MainWindow

        class _Label:
            def __init__(self):
                self.text = self.style = self.tip = None
            def setText(self, t): self.text = t
            def setStyleSheet(self, s): self.style = s
            def setToolTip(self, t): self.tip = t

        class _OM:
            def ausgabe_status(self):
                return [_weg(u) for u in sorted(mit_ausgang)]
            def sende_probleme(self):
                return []
            def sendet_wirklich(self, u):
                return u in mit_ausgang

        class _Fixture:
            def __init__(self, u): self.universe = u

        class _State:
            output_manager = _OM()
            universes = {u: object() for u in list(gepatchte_universen) + [99]}
            def get_patched_fixtures(self):
                return [_Fixture(u) for u in gepatchte_universen]

        class _Fenster:
            _lbl_universe = _Label()
            _state = _State()
            _universen_mit_geraeten = MainWindow._universen_mit_geraeten

        f = _Fenster()
        MainWindow._update_ausgabe_label(f)
        return f._lbl_universe

    def test_das_fenster_meldet_das_stumme_universum(self):
        lbl = self._fenster(gepatchte_universen=[1, 3], mit_ausgang={1})
        self.assertIn("U3 ohne Ausgang", lbl.text)
        self.assertEqual(lbl.style, FARBE_FEHLT)

    def test_ohne_luecke_bleibt_es_still(self):
        lbl = self._fenster(gepatchte_universen=[1], mit_ausgang={1})
        self.assertFalse(lbl.text.startswith("⚠"))
        self.assertEqual(lbl.style, FARBE_NORMAL)

    def test_die_quelle_ist_der_PATCH_nicht_state_universes(self):
        """★★★ Die Aussage lautet „es werden Kanaele fuer GERAETE gerechnet,
        die nirgends hingehen". ``state.universes`` enthaelt aber auch, was nur
        in der Output-Konfiguration steht (`app_state.py:1786`) — davor zu
        warnen waere falsch, es rechnet ja fuer niemanden. Das Doppel oben legt
        deshalb ein zusaetzliches U99 nur in ``state.universes``."""
        lbl = self._fenster(gepatchte_universen=[1], mit_ausgang={1})
        self.assertNotIn("U99", lbl.text or "")
        self.assertNotIn("U99", lbl.tip or "")

    def test_ein_fehler_in_der_ZUSATZ_info_loescht_die_bestehende_nicht(self):
        """★★★ Der Fehler, den ich beim Bauen gemacht habe — und den die
        BESTANDSTESTS aus OUT-51 sofort gefunden haben.

        Im ersten Wurf stand die neue Abfrage im selben ``try`` wie
        ``ausgabe_status()``; dessen ``return`` heisst „gar keine Anzeige".
        Ein Fehler in der ZUSATZ-Information hat damit die BESTEHENDE geloescht
        — statt „U1 Enttec" stand dort nichts mehr. Eine leere Anzeige ist
        schlimmer als eine unvollstaendige: sie sieht aus, als gaebe es nichts
        zu sagen. Dieselbe Klasse wie NET-12 (ein breites ``except`` um einen
        Aufruf macht dessen Ausfall unsichtbar), nur eine Ebene sichtbarer."""
        from src.ui.main_window import MainWindow

        class _Label:
            text = style = tip = None
            def setText(self, t): self.text = t
            def setStyleSheet(self, s): self.style = s
            def setToolTip(self, t): self.tip = t

        class _OM:
            def ausgabe_status(self):
                return [_weg(1, "Enttec", "/dev/ttyUSB0", verbunden=True)]
            def sende_probleme(self):
                return []
            def sendet_wirklich(self, u):
                raise RuntimeError("Ausgabe kaputt")

        class _Fenster:
            _lbl_universe = _Label()
            _state = type("S", (), {"output_manager": _OM()})()
            def _universen_mit_geraeten(self):
                return [1, 3]

        f = _Fenster()
        MainWindow._update_ausgabe_label(f)
        self.assertIn("U1 Enttec", f._lbl_universe.text or "",
                      "die bestehende Auskunft ist verschwunden")

    def test_ohne_label_passiert_nichts(self):
        """Der Statusbalken darf nie der Grund sein, warum das Fenster nicht
        aufgeht — waehrend des Hochfahrens gibt es ihn noch nicht."""
        from src.ui.main_window import MainWindow

        class _Fenster:
            _lbl_universe = None
        MainWindow._update_ausgabe_label(_Fenster())   # darf nicht werfen


class DieFrageWirdNUREINMALBEANTWORTETTest(unittest.TestCase):
    """★★ Review-Checkliste 17. „Hat dieses Universum einen Ausgang?" ist genau
    die Frage, die der DMX-Monitor seit OUT-52 stellt. Es darf keine zweite
    Antwort geben."""

    def test_beide_anzeigen_fragen_sendet_wirklich(self):
        import inspect
        from src.ui import main_window
        from src.ui.views import dmx_monitor_view
        for modul in (main_window, dmx_monitor_view):
            with self.subTest(modul=modul.__name__):
                self.assertIn("sendet_wirklich", inspect.getsource(modul),
                              "diese Anzeige beantwortet die Frage selbst")

    def test_die_reine_regel_haengt_an_keinem_qt(self):
        """Der Grund, aus dem dieses Modul existiert: pruefbar ohne zu malen."""
        import inspect
        from src.ui import ausgabe_label as modul
        quelle = inspect.getsource(modul)
        for verbot in ("PySide6", "QWidget", "QLabel", "QPainter"):
            self.assertNotIn(verbot, quelle)


if __name__ == "__main__":
    unittest.main()
