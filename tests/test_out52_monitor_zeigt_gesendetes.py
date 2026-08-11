"""OUT-52 — der Monitor sagt jetzt, ob das gezeigte Bild wirklich rausgeht.

★ **Der Befund.** ``_send_all`` setzt den Anzeige-Snapshot, **bevor** es
nachsieht, ob das Universum ueberhaupt einen Adapter hat. Der Monitor zeigte
damit, was LightOS **rechnet** — nicht, was das Rig bekommt. Ein Universum ohne
jeden Ausgang sah exakt so aus wie eines, das sendet.

**Genau diese Verwechslung hat am 2026-08-05 die Fehlersuche verlaengert:** der
Viewer sah richtig aus, waehrend ein leeres Universum gesendet wurde.

Dazu zwei Befunde aus demselben Audit:

* Ein im Universe-Manager **geloeschtes** Universum sendete unveraendert
  weiter — ``apply_output_config`` iteriert nur ueber die Zeilen, die es noch
  gibt, und raeumte den Adapter der geloeschten deshalb nie ab.
* Der Monitor bot **16** Universen an, obwohl Patch und Ausgabe **32** koennen
  (im Output-Tab war das schon korrigiert, hier nicht).
"""
import types
import unittest

from src.core.dmx.output_manager import OutputManager


class SendetWirklichTest(unittest.TestCase):

    def test_universum_ohne_adapter(self):
        om = OutputManager()
        om.add_universe(3)
        self.assertFalse(om.sendet_wirklich(3))

    def test_universum_mit_adapter(self):
        for weg in ("_enttec_outputs", "_artnet_outputs", "_sacn_outputs"):
            with self.subTest(weg=weg):
                om = OutputManager()
                om.add_universe(3)
                getattr(om, weg)[3] = types.SimpleNamespace(port="x")
                self.assertTrue(om.sendet_wirklich(3))

    def test_anderes_universum_zaehlt_nicht(self):
        """Sonst waere die Auskunft „irgendwo sendet irgendwas" — genau der
        Fehler, den OUT-51 an der Statusleiste behoben hat."""
        om = OutputManager()
        om.add_universe(1)
        om.add_universe(2)
        om._enttec_outputs[1] = types.SimpleNamespace(port="x")
        self.assertFalse(om.sendet_wirklich(2))


class _Label:
    def __init__(self):
        self.text, self.style, self.tip = "", "", ""

    def setText(self, t):
        self.text = t

    def setStyleSheet(self, s):
        self.style = s

    def setToolTip(self, t):
        self.tip = t


def _monitor_label(om, univ=1, gesendet=True):
    from src.ui.views import dmx_monitor_view as mv
    stub = types.SimpleNamespace(_lbl_ausgang=_Label())
    mv.DmxMonitorView._update_ausgang_label(stub, om, univ, gesendet)
    return stub._lbl_ausgang


class MonitorKennzeichnetTest(unittest.TestCase):
    """★★ „Der Monitor kennzeichnet, ob ein Universum tatsaechlich gesendet
    wird" — die Fertig-Bedingung des Items."""

    def test_ohne_ausgang_wird_gewarnt(self):
        om = OutputManager()
        om.add_universe(1)
        lbl = _monitor_label(om)
        self.assertIn("keinen Ausgang", lbl.text)
        self.assertIn("gerechnet", lbl.text,
                      "der Nutzer muss erfahren, was er da eigentlich sieht")
        self.assertNotIn("9DFF52", lbl.style, "das darf nicht gruen sein")

    def test_mit_ausgang_ist_gruen(self):
        om = OutputManager()
        om.add_universe(1)
        om._enttec_outputs[1] = types.SimpleNamespace(port="/dev/ttyUSB0")
        lbl = _monitor_label(om)
        self.assertIn("geht raus", lbl.text)
        self.assertIn("9DFF52", lbl.style)

    def test_adapter_da_aber_sendet_nicht(self):
        """★ Der dritte Zustand: registriert, aber eine laufende Fehlerserie
        (OUT-51). Ihn mit „geht raus" zu beschriften waere die alte Luege in
        neuem Gewand."""
        import io
        from contextlib import redirect_stderr
        from src.core.dmx.output_manager import SENDE_FEHLER_SCHWELLE

        class _Kaputt:
            port = "/dev/ttyUSB0"

            def send_dmx(self, *_a):
                raise OSError("weg")

        om = OutputManager()
        om.add_universe(1)
        om._enttec_outputs[1] = _Kaputt()
        with redirect_stderr(io.StringIO()):
            for _ in range(SENDE_FEHLER_SCHWELLE):
                om._send_all()
        lbl = _monitor_label(om)
        self.assertIn("sendet NICHT", lbl.text)
        self.assertIn("ff4444", lbl.style)

    def test_ohne_output_manager_bleibt_das_label_leer(self):
        """Waehrend des Hochfahrens gibt es ihn noch nicht — eine Warnung waere
        dann ein Fehlalarm."""
        self.assertEqual("", _monitor_label(None).text)

    def test_noch_kein_frame_ist_kein_fehler(self):
        """Adapter da, Output-Thread aus: Rohwerte sind korrekt, aber es ist
        eben nicht der gesendete Stand."""
        om = OutputManager()
        om.add_universe(1)
        om._artnet_outputs[1] = types.SimpleNamespace(target_ip="10.0.0.1")
        lbl = _monitor_label(om, gesendet=False)
        self.assertIn("Rohwerte", lbl.text)
        self.assertNotIn("9DFF52", lbl.style)


class GeloeschteZeileRaeumtDenAusgangTest(unittest.TestCase):
    """★★ Ein im Universe-Manager geloeschtes Universum sendete weiter.

    `apply_output_config` laeuft nur ueber die Zeilen, die es NOCH GIBT — die
    geloeschte kam darin nicht mehr vor, ihr Adapter wurde also nie
    geschlossen. Das Loeschen sah aus wie erledigt, und das Rig bekam
    unveraendert weiter DMX.
    """

    def _state_mit_ausgang(self, tmpdir, rows):
        import json
        import os
        from src.core.app_state import AppState
        pfad = os.path.join(tmpdir, "universes.json")
        with open(pfad, "w", encoding="utf-8") as f:
            json.dump(rows, f)
        st = AppState.__new__(AppState)
        st.universes = {}
        st.output_manager = OutputManager()
        st.universes[1] = st.output_manager.add_universe(1)
        st.universes[2] = st.output_manager.add_universe(2)
        st.output_manager._artnet_outputs[1] = types.SimpleNamespace(
            target_ip="10.0.0.1", close=lambda: None)
        st.output_manager._artnet_outputs[2] = types.SimpleNamespace(
            target_ip="10.0.0.2", close=lambda: None)
        return st, pfad

    def test_entfernte_zeile_verliert_ihren_adapter(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            # Universum 2 wurde im Dialog geloescht -> steht nicht mehr drin.
            st, pfad = self._state_mit_ausgang(
                tmp, [{"num": 1, "output": "ArtNet", "patch": "10.0.0.1"}])
            st.apply_output_config(pfad)
            self.assertTrue(st.output_manager.sendet_wirklich(1))
            self.assertFalse(st.output_manager.sendet_wirklich(2),
                             "der Adapter des geloeschten Universums sendet weiter")

    def test_vorhandene_zeilen_bleiben(self):
        """Positivkontrolle: nach dem Anwenden stehen die konfigurierten
        Ausgaenge.

        ⚠️ **Grenze dieses Tests, gemessen und bewusst so belassen.** Eine
        Mutation, die den Vorab-Raeumschritt auf ALLE Universen ausweitet
        (``if True:`` statt ``not in konfiguriert``), macht ihn NICHT rot —
        und das ist korrekt: die Schleife darunter ruft fuer jede
        konfigurierte Zeile ohnehin ``remove_output(num)``
        (``app_state.py:1763``) und baut sie neu auf. Der breitere Schnitt hat
        damit kein beobachtbares Verhalten; es ist eine aequivalente Mutante,
        kein Loch im Test. Einen Test dafuer zu bauen hiesse, die Anzahl der
        ``remove_output``-Aufrufe festzunageln — eine belanglose Eigenschaft,
        die nur kuenftige Umbauten behindert.
        """
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            st, pfad = self._state_mit_ausgang(tmp, [
                {"num": 1, "output": "ArtNet", "patch": "10.0.0.1"},
                {"num": 2, "output": "ArtNet", "patch": "10.0.0.2"},
            ])
            st.apply_output_config(pfad)
            self.assertTrue(st.output_manager.sendet_wirklich(1))
            self.assertTrue(st.output_manager.sendet_wirklich(2))


class MonitorBietetAlleUniversenTest(unittest.TestCase):

    def test_universumsauswahl_geht_bis_32(self):
        """Patch und Ausgabe koennen 1–32; ein 1–16-Limit machte gepatchte
        Geraete auf U17–U32 im Monitor unsichtbar."""
        import pathlib
        quelle = (pathlib.Path(__file__).resolve().parent.parent
                  / "src" / "ui" / "views" / "dmx_monitor_view.py"
                  ).read_text(encoding="utf-8")
        self.assertIn("range(1, 33)", quelle)
        self.assertNotIn("range(1, 17)", quelle)


if __name__ == "__main__":
    unittest.main()
