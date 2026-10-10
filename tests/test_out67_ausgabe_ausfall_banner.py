"""OUT-67 — ein Ausgabe-Ausfall wird laut gemeldet, der Probenmodus ist sichtbar.

Was die Statusleiste seit HW-5b/OUT-51/OUT-56 schon weiss (vier Zustaende je
Geraet, ``ausgabe_status()``, ``sende_probleme()``), steht unten links in kleiner
Schrift — und im Kiosk-/VC-Vollbild gar nicht, weil die Statusleiste dort
ausgeblendet ist. Das Banner zeigt DIESELBE Auskunft oben im Hauptfenster:

1. Ausfall  -> „Ausgabe gestört: <Weg> — <Grund>", sofort.
2. Erholung -> verschwindet von selbst, aber erst nach einer Haltezeit
   (ein Wackelkontakt soll nicht flackern).
3. kein einziger Ausgang -> dezent „Probenmodus — es wird kein DMX gesendet",
   per Klick fuer die Sitzung abschaltbar.
4. ein sendender Ausgang -> kein Hinweis.

Alles mit Attrappen: kein Port, kein Netz, kein Hauptfenster.
"""
from __future__ import annotations

import io
import os
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.core.dmx.output_manager import (  # noqa: E402
    OutputManager, SENDE_FEHLER_SCHWELLE)
from src.ui import ausgabe_banner as ab  # noqa: E402
from src.ui.ausgabe_banner import (  # noqa: E402
    ART_KEIN, ART_PROBE, ART_STOERUNG, HALTE_S, BannerDrossel,
    AusgabeBannerSteuerung, ausgabe_banner)


class _Adapter:
    """Attrappe eines Ausgabegeraets. ``fehler`` gesetzt = jedes Frame wirft."""

    def __init__(self, fehler=None, port="", verbunden=None):
        self.fehler = fehler
        self.gesendet = 0
        if port:
            self.port = port
        if verbunden is not None:
            self._verbunden = verbunden
            self.is_connected = lambda: self._verbunden

    def send_dmx(self, *args):
        if self.fehler is not None:
            raise self.fehler
        self.gesendet += 1


def _manager(weg=None, dev=None, universum=1) -> OutputManager:
    om = OutputManager()
    om.add_universe(universum)
    if weg:
        {"Enttec": om._enttec_outputs, "Art-Net": om._artnet_outputs,
         "sACN": om._sacn_outputs}[weg][universum] = dev
    return om


def _frames(om, n=SENDE_FEHLER_SCHWELLE + 2):
    with redirect_stderr(io.StringIO()):
        for _ in range(n):
            om._send_all()


def _weg(univ, weg="sACN", ziel="", verbunden=None, problem=""):
    return {"universum": univ, "weg": weg, "ziel": ziel,
            "verbunden": verbunden, "problem": problem}


class DieRegelTest(unittest.TestCase):
    """Reine Rechnung — ohne Qt, ohne OutputManager."""

    def test_ausfall_nennt_weg_und_grund(self):
        z = ausgabe_banner([_weg(2, "Art-Net", "10.0.0.5", False,
                                 "OSError: Network is unreachable")])
        self.assertEqual(z.art, ART_STOERUNG)
        self.assertTrue(z.text.startswith("Ausgabe gestört: "), z.text)
        self.assertIn("U2 Art-Net", z.text)
        self.assertIn("10.0.0.5", z.text)
        self.assertIn(" — ", z.text)
        self.assertIn("Network is unreachable", z.text)

    def test_toter_port_ohne_fehlertext_bekommt_trotzdem_einen_grund(self):
        """Ein abgezogener Enttec wirft nicht — der Worker meldet nur „nicht
        verbunden". Ein Banner ohne Grund waere nur ein roter Balken."""
        z = ausgabe_banner([_weg(1, "Enttec", "COM9", False)])
        self.assertEqual(z.art, ART_STOERUNG)
        self.assertIn("U1 Enttec", z.text)
        self.assertRegex(z.text, r" — \S")

    def test_mehrere_ausfaelle_werden_gezaehlt(self):
        z = ausgabe_banner([_weg(1, "Enttec", "", False),
                            _weg(2, "sACN", "", False, "OSError: x"),
                            _weg(3, "sACN")])
        self.assertIn("U1 Enttec", z.text)
        self.assertIn("+1", z.text)
        self.assertIn("U2 sACN", z.tooltip)

    def test_ungewiss_ist_kein_ausfall(self):
        """UDP weiss nicht, ob jemand zuhoert (``None``) — das ist weder ein
        Ausfall noch Probenmodus: es wird gesendet."""
        self.assertEqual(ausgabe_banner([_weg(1, "Art-Net")]).art, ART_KEIN)
        self.assertEqual(
            ausgabe_banner([_weg(1, "Enttec", verbunden=True)]).art, ART_KEIN)

    def test_ohne_ausgang_probenmodus(self):
        z = ausgabe_banner([])
        self.assertEqual(z.art, ART_PROBE)
        self.assertEqual(z.text, "Probenmodus — es wird kein DMX gesendet")

    def test_probenhinweis_abschaltbar_ausfall_nicht(self):
        self.assertEqual(ausgabe_banner([], probe_aus=True).art, ART_KEIN)
        z = ausgabe_banner([_weg(1, "Enttec", "", False)], probe_aus=True)
        self.assertEqual(z.art, ART_STOERUNG)

    def test_kiosk_probenhinweis_dezent_ausfall_voll(self):
        probe = ausgabe_banner([], kiosk=True)
        self.assertEqual(probe.art, ART_PROBE)
        self.assertTrue(probe.klein)
        self.assertFalse(ausgabe_banner([]).klein)
        stoer = ausgabe_banner([_weg(1, "Enttec", "", False)], kiosk=True)
        self.assertEqual(stoer.art, ART_STOERUNG)
        self.assertFalse(stoer.klein)


class DrosselTest(unittest.TestCase):
    """Kein Flackern: laut wird es sofort, leise erst nach der Haltezeit."""

    def setUp(self):
        self.stoer = ausgabe_banner([_weg(1, "Enttec", "", False)])
        self.gut = ausgabe_banner([_weg(1, "Enttec", verbunden=True)])
        self.probe = ausgabe_banner([])

    def test_ausfall_sofort(self):
        d = BannerDrossel()
        self.assertEqual(d.schritt(self.gut, 0.0).art, ART_KEIN)
        self.assertEqual(d.schritt(self.stoer, 0.1).art, ART_STOERUNG)

    def test_erholung_erst_nach_haltezeit(self):
        d = BannerDrossel()
        d.schritt(self.stoer, 0.0)
        self.assertEqual(d.schritt(self.gut, 1.0).art, ART_STOERUNG)
        self.assertEqual(d.schritt(self.gut, 1.0 + HALTE_S / 2).art,
                         ART_STOERUNG)
        self.assertEqual(d.schritt(self.gut, 1.0 + HALTE_S).art, ART_KEIN)

    def test_wackelkontakt_flackert_nicht(self):
        d = BannerDrossel()
        d.schritt(self.stoer, 0.0)
        t, gesehen = 0.0, []
        for i in range(20):                     # gut/kaputt im Wechsel
            t += HALTE_S / 3
            gesehen.append(d.schritt(self.gut if i % 2 else self.stoer, t).art)
        self.assertEqual(set(gesehen), {ART_STOERUNG})

    def test_probenhinweis_erst_wenn_stabil(self):
        """Beim Show-Laden werden Ausgaenge kurz ab- und wieder angemeldet."""
        d = BannerDrossel()
        d.schritt(self.gut, 0.0)
        self.assertEqual(d.schritt(self.probe, 1.0).art, ART_KEIN)
        self.assertEqual(d.schritt(self.gut, 1.5).art, ART_KEIN)
        self.assertEqual(d.schritt(self.probe, 2.0).art, ART_KEIN)
        self.assertEqual(d.schritt(self.probe, 2.0 + HALTE_S).art, ART_PROBE)


class BannerImFensterTest(unittest.TestCase):
    """Widget + Steuerung gegen einen echten OutputManager mit Attrappen."""

    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.t = 100.0
        self.log = io.StringIO()

    def _steuerung(self, kiosk=False):
        s = AusgabeBannerSteuerung(kiosk=kiosk, uhr=lambda: self.t)
        self.addCleanup(s.widget.deleteLater)
        return s

    def _akt(self, s, om, dt=0.0):
        self.t += dt
        with redirect_stdout(self.log):
            s.aktualisiere(om)

    def test_fehler_zeigt_banner_mit_text(self):
        dev = _Adapter(fehler=OSError("Network is unreachable"))
        om = _manager("sACN", dev)
        s = self._steuerung()
        self._akt(s, om)
        self.assertTrue(s.widget.isHidden(), "vor dem Ausfall kein Banner")
        _frames(om)
        self._akt(s, om, 2.0)
        self.assertFalse(s.widget.isHidden())
        text = s.widget.text()
        self.assertIn("Ausgabe gestört: U1 sACN", text)
        self.assertIn("Network is unreachable", text)

    def test_erholung_raeumt_das_banner_von_selbst_weg(self):
        dev = _Adapter(fehler=OSError("weg"))
        om = _manager("Art-Net", dev)
        s = self._steuerung()
        _frames(om)
        self._akt(s, om)
        self.assertFalse(s.widget.isHidden())
        dev.fehler = None
        _frames(om, 3)
        self._akt(s, om, 0.5)
        self.assertFalse(s.widget.isHidden(), "Haltezeit: noch sichtbar")
        self._akt(s, om, HALTE_S)
        self.assertTrue(s.widget.isHidden())
        self.assertEqual(s.widget.text(), "")

    def test_toter_enttec_port(self):
        dev = _Adapter(port="COM9", verbunden=False)
        om = _manager("Enttec", dev)
        s = self._steuerung(kiosk=True)        # auch im Kiosk laut
        self._akt(s, om)
        self.assertFalse(s.widget.isHidden())
        self.assertIn("Ausgabe gestört: U1 Enttec (COM9) — ", s.widget.text())
        dev._verbunden = True
        self._akt(s, om, HALTE_S + 0.1)
        self._akt(s, om, HALTE_S + 0.1)
        self.assertTrue(s.widget.isHidden())

    def test_keine_ausgaenge_probenhinweis(self):
        om = _manager()
        s = self._steuerung()
        self._akt(s, om)
        self._akt(s, om, HALTE_S + 0.1)
        self.assertFalse(s.widget.isHidden())
        self.assertEqual(s.widget.text(),
                         "Probenmodus — es wird kein DMX gesendet")

    def test_sendender_ausgang_kein_hinweis(self):
        dev = _Adapter()
        om = _manager("sACN", dev)
        s = self._steuerung()
        _frames(om, 5)
        self.assertEqual(dev.gesendet, 5)
        self._akt(s, om)
        self._akt(s, om, HALTE_S + 0.1)
        self.assertTrue(s.widget.isHidden())

    def test_klick_schaltet_probenhinweis_fuer_die_sitzung_ab(self):
        om = _manager()
        s = self._steuerung()
        self._akt(s, om)
        self._akt(s, om, HALTE_S + 0.1)
        self.assertFalse(s.widget.isHidden())
        with redirect_stdout(self.log):
            s.widget.geklickt.emit()
        self.assertTrue(s.widget.isHidden())
        self._akt(s, om, 60.0)
        self.assertTrue(s.widget.isHidden(), "bleibt fuer die Sitzung aus")
        # ... aber ein Ausfall kommt trotzdem durch.
        om._sacn_outputs[1] = _Adapter(fehler=OSError("x"))
        _frames(om)
        self._akt(s, om, 2.0)
        self.assertFalse(s.widget.isHidden())
        self.assertIn("Ausgabe gestört", s.widget.text())

    def test_klick_auf_stoerung_blendet_nicht_aus(self):
        om = _manager("Enttec", _Adapter(verbunden=False))
        s = self._steuerung()
        gerufen = []
        s.bei_stoerung_klick = lambda: gerufen.append(1)
        self._akt(s, om)
        with redirect_stdout(self.log):
            s.widget.geklickt.emit()
        self.assertFalse(s.widget.isHidden())
        self.assertEqual(gerufen, [1])

    def test_sitzungslog_einmal_je_wechsel(self):
        from src.core import diagnose_log
        dev = _Adapter(fehler=OSError("Kabel ab"))
        om = _manager("sACN", dev)
        s = self._steuerung()
        _frames(om)
        for _ in range(5):                      # fuenf Abfragen, EIN Eintrag
            self._akt(s, om, 2.0)
        log = self.log.getvalue()
        self.assertEqual(log.count("Ausgabe gestört"), 1, log)
        self.assertIn("Kabel ab", log)
        self.assertIn("gestört", diagnose_log.laufzeit_infos().get(
            ab.LOG_SCHLUESSEL, ""))
        dev.fehler = None
        _frames(om, 3)
        self._akt(s, om, 1.0)
        self._akt(s, om, HALTE_S + 0.1)
        self.assertIn("läuft wieder", self.log.getvalue())

    def test_kaputter_manager_reisst_nichts_mit(self):
        class _Kaputt:
            def ausgabe_status(self):
                raise RuntimeError("mitten im Umbau")
        s = self._steuerung()
        self._akt(s, _Kaputt())                 # darf nicht werfen
        self.assertTrue(s.widget.isHidden())


class HauptfensterFuettertDasBannerTest(unittest.TestCase):
    """Die Verdrahtung am Stub; das echte (Kiosk-)Fenster prueft
    ``test_out67_banner_im_kiosk_fenster.py``."""

    def test_statusbalken_aktualisiert_auch_das_banner(self):
        """Derselbe 2-s-Takt wie die Statusleiste (OUT-51) — kein zweiter Timer."""
        import types
        from src.ui import main_window as mw

        class _Lbl:
            def setText(self, t): pass
            def setStyleSheet(self, s): pass
            def setToolTip(self, t): pass

        om = _manager()
        gerufen = []
        stub = types.SimpleNamespace(
            _lbl_universe=_Lbl(),
            _state=types.SimpleNamespace(output_manager=om,
                                         get_patched_fixtures=lambda: []),
            _ausgabe_banner=types.SimpleNamespace(
                aktualisiere=lambda m, wege=None: gerufen.append(m)))
        stub._universen_mit_geraeten = lambda: []
        mw.MainWindow._update_ausgabe_label(stub)
        self.assertEqual(gerufen, [om])


if __name__ == "__main__":
    unittest.main()
