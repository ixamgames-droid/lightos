"""HW-5b — ein Enttec-Port aus einer fremden Plattform darf nicht still scheitern.

Der reale Fall: nach dem Umzug von Windows auf Linux stand in
``data/universes.json`` fuer das Enttec-Universe weiter ``"COM_FAKE"``. Auf Linux
heisst dasselbe Geraet ``/dev/ttyUSB0``. ``EnttecPro("COM_FAKE")`` konnte also nur
werfen, die Exception landete im ``except`` von ``apply_output_config`` — und der
Statusbalken meldete trotzdem **gruen** „Enttec: /dev/ttyUSB0 OK", weil er nur
fragte, ob per VID/PID irgendein Enttec am Rechner haengt. Ergebnis: es ging gar
kein DMX raus, und nichts sagte es.

Zwei Haelften, beide hier abgesichert: die Diagnose (`diagnose_port`) und dass
`apply_output_config` sie festhaelt — ohne den Port stillschweigend umzubiegen.
Genau das waere die naheliegende, aber falsche Loesung: an einem Rechner koennen
mehrere FTDI-Geraete haengen, und der Aufbau haenge dann davon ab, was gerade
eingesteckt ist (bis in die Tests hinein).
"""
import os
import unittest
from unittest import mock

from src.core.dmx import enttec_pro


class _Port:
    def __init__(self, device, vid=None, pid=None):
        self.device, self.vid, self.pid = device, vid, pid


class FremdplattformErkennungTests(unittest.TestCase):
    def test_com_name_ist_auf_posix_fremd(self):
        with mock.patch.object(os, "name", "posix"):
            self.assertTrue(enttec_pro.port_is_foreign("COM3"))
            self.assertTrue(enttec_pro.port_is_foreign("COM_FAKE"))
            self.assertFalse(enttec_pro.port_is_foreign("/dev/ttyUSB0"))

    def test_dev_name_ist_auf_windows_fremd(self):
        with mock.patch.object(os, "name", "nt"):
            self.assertTrue(enttec_pro.port_is_foreign("/dev/ttyUSB0"))
            self.assertFalse(enttec_pro.port_is_foreign("COM3"))

    def test_leerer_port_ist_nicht_fremd_sondern_unkonfiguriert(self):
        self.assertFalse(enttec_pro.port_is_foreign(""))
        self.assertFalse(enttec_pro.port_is_foreign(None))


class DiagnoseTests(unittest.TestCase):
    def test_vorhandener_port_ist_unauffaellig(self):
        with mock.patch.object(enttec_pro, "list_serial_ports",
                               lambda: ["/dev/ttyUSB0"]), \
             mock.patch.object(enttec_pro, "find_enttec_port", lambda: "/dev/ttyUSB9"):
            self.assertIsNone(enttec_pro.diagnose_port("/dev/ttyUSB0"),
                              "ein funktionierender Port darf keinen Hinweis "
                              "erzeugen, auch wenn anderswo ein Enttec haengt")

    def test_der_echte_fall_com_fake_auf_linux(self):
        with mock.patch.object(os, "name", "posix"), \
             mock.patch.object(enttec_pro, "list_serial_ports",
                               lambda: ["/dev/ttyUSB0"]), \
             mock.patch.object(enttec_pro, "find_enttec_port",
                               lambda: "/dev/ttyUSB0"):
            hinweis = enttec_pro.diagnose_port("COM_FAKE")
        self.assertIn("anderen Plattform", hinweis)
        self.assertIn("kein DMX", hinweis)
        self.assertIn("/dev/ttyUSB0", hinweis, "der Vorschlag muss konkret sein")

    def test_fremder_port_ohne_sichtbaren_enttec_meldet_klartext(self):
        with mock.patch.object(os, "name", "posix"), \
             mock.patch.object(enttec_pro, "list_serial_ports", lambda: []), \
             mock.patch.object(enttec_pro, "find_enttec_port", lambda: None):
            hinweis = enttec_pro.diagnose_port("COM_FAKE")
        self.assertIn("kein DMX", hinweis)
        self.assertIn("kein Enttec per VID/PID sichtbar", hinweis)

    def test_verschwundener_port_wird_nicht_mit_geraet_verwechselt(self):
        """`/dev/ttyUSB7` gibt es nicht mehr — anderer Fall als ein
        Fremdplattform-Name, und muss auch anders klingen: nicht 'anderer
        Rechner', sondern 'existiert nicht'."""
        with mock.patch.object(os, "name", "posix"), \
             mock.patch.object(enttec_pro, "list_serial_ports",
                               lambda: ["/dev/ttyUSB0"]), \
             mock.patch.object(enttec_pro, "find_enttec_port",
                               lambda: "/dev/ttyUSB0"):
            hinweis = enttec_pro.diagnose_port("/dev/ttyUSB7")
        self.assertIn("existiert auf diesem System nicht", hinweis)
        self.assertNotIn("anderen Plattform", hinweis)

    def test_kein_port_konfiguriert_aber_geraet_da(self):
        with mock.patch.object(enttec_pro, "list_serial_ports",
                               lambda: ["/dev/ttyUSB0"]), \
             mock.patch.object(enttec_pro, "find_enttec_port",
                               lambda: "/dev/ttyUSB0"):
            hinweis = enttec_pro.diagnose_port("")
        self.assertIn("kein Enttec-Port konfiguriert", hinweis)
        self.assertIn("/dev/ttyUSB0", hinweis)

    def test_gar_nichts_da(self):
        with mock.patch.object(enttec_pro, "list_serial_ports", lambda: []), \
             mock.patch.object(enttec_pro, "find_enttec_port", lambda: None):
            self.assertIsNotNone(enttec_pro.diagnose_port(""))

    def test_diagnose_ueberlebt_kaputte_portabfrage(self):
        """Ein Fehler beim Port-Enumerieren darf den Start nicht kosten."""
        def boom():
            raise OSError("kaputt")
        with mock.patch.object(enttec_pro, "list_serial_ports", boom), \
             mock.patch.object(enttec_pro, "find_enttec_port", boom):
            self.assertIsNotNone(enttec_pro.diagnose_port("COM3"))


class ConfigAnwendungTests(unittest.TestCase):
    """`apply_output_config` muss den aufgeloesten Port benutzen — und bei
    unbrauchbarem Port gar nicht erst oeffnen, statt eine Exception zu erzeugen,
    die im `except` verschwindet."""

    def _state_mit_config(self, tmpdir, patch_value):
        import json
        from src.core.app_state import get_state
        p = os.path.join(tmpdir, "universes.json")
        with open(p, "w", encoding="utf-8") as fh:
            json.dump([{"num": 3, "name": "Enttec", "output": "Enttec",
                        "patch": patch_value}], fh)
        return get_state(), p

    def _apply(self, patch_value, ports, gefunden):
        import tempfile
        calls = []
        with tempfile.TemporaryDirectory() as td:
            st, cfg = self._state_mit_config(td, patch_value)
            with mock.patch.object(os, "name", "posix"), \
                 mock.patch.object(enttec_pro, "list_serial_ports", lambda: ports), \
                 mock.patch.object(enttec_pro, "find_enttec_port", lambda: gefunden), \
                 mock.patch.object(st.output_manager, "add_enttec",
                                   lambda u, p: calls.append((u, p))), \
                 mock.patch.object(st.output_manager, "remove_output",
                                   lambda u: None):
                st.apply_output_config(cfg)
        return st, calls

    def test_der_befund_wird_festgehalten_der_port_aber_NICHT_umgebogen(self):
        """★ Die naheliegende Loesung waere, hier auf /dev/ttyUSB0 umzustellen.
        Bewusst nicht: an einem Rechner koennen mehrere FTDI-Geraete haengen, und
        DMX auf ein nie konfiguriertes Geraet zu schicken ist schlimmer als der
        ehrliche Hinweis. Der Oeffnungsversuch bleibt exakt wie vorher."""
        st, calls = self._apply("COM_FAKE", ["/dev/ttyUSB0"], "/dev/ttyUSB0")
        self.assertEqual(calls, [(3, "COM_FAKE")])
        hinweis = st.enttec_port_notes.get(3) or ""
        self.assertIn("anderen Plattform", hinweis)
        self.assertIn("/dev/ttyUSB0", hinweis, "aber der Vorschlag muss dastehen")

    def test_grund_wird_auch_ohne_sichtbares_geraet_festgehalten(self):
        st, calls = self._apply("COM_FAKE", [], None)
        self.assertEqual(calls, [(3, "COM_FAKE")])
        self.assertIn("kein DMX", st.enttec_port_notes.get(3) or "")

    def test_sauberer_port_hinterlaesst_keinen_hinweis(self):
        st, calls = self._apply("/dev/ttyUSB0", ["/dev/ttyUSB0"], "/dev/ttyUSB0")
        self.assertEqual(calls, [(3, "/dev/ttyUSB0")])
        self.assertIsNone(st.enttec_port_notes.get(3))

    def test_stub_ohne_das_neue_feld_ueberlebt(self):
        """Bestandstests rufen ``apply_output_config`` auf einem SimpleNamespace
        mit NUR ``output_manager``/``universes`` auf (so dokumentiert). Ein neues
        Pflichtfeld haette dort mit AttributeError zugeschlagen — und der Fehler
        waere im ``except`` des Aufrufers verschwunden, also genau in der
        Fehlerklasse gelandet, die dieses Item behebt."""
        import json
        import tempfile
        import types
        from src.core.app_state import AppState
        from src.core.dmx.output_manager import OutputManager
        stub = types.SimpleNamespace()
        stub.output_manager = OutputManager()
        stub.universes = stub.output_manager.universes
        calls = []
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "u.json")
            with open(p, "w", encoding="utf-8") as fh:
                json.dump([{"num": 1, "output": "Enttec", "patch": "COM_FAKE"}], fh)
            with mock.patch.object(stub.output_manager, "add_enttec",
                                   lambda u, prt: calls.append((u, prt))), \
                 mock.patch.object(stub.output_manager, "remove_output",
                                   lambda u: None):
                AppState.apply_output_config(stub, path=p)
        stub.output_manager.stop()
        self.assertEqual(calls, [(1, "COM_FAKE")])
        self.assertIn(1, stub.enttec_port_notes)


class _Label:
    """Minimal-Ersatz fuer das QLabel im Statusbalken."""

    def __init__(self):
        self.text, self.style, self.tip = "", "", ""

    def setText(self, t):
        self.text = t

    def setStyleSheet(self, s):
        self.style = s

    def setToolTip(self, t):
        self.tip = t


class _Dev:
    def __init__(self, port):
        self.port = port


class StatusbalkenTests(unittest.TestCase):
    """★ Der Statusbalken war die eigentliche Bosheit an HW-5b: er fragte nur
    ``find_enttec_port()`` — also ob per VID/PID IRGENDEIN Enttec am Rechner
    haengt. Ob ein Universe ihn auch benutzt, interessierte ihn nicht. Also stand
    dort gruen „Enttec: /dev/ttyUSB0 OK", waehrend gar kein DMX rausging.
    Ein Fehler, der sich als Erfolg meldet, ist schlimmer als ein lauter Fehler.
    """

    def _run(self, *, gefunden, offene, notes):
        import types
        from src.ui import main_window as mw
        lbl = _Label()
        stub = types.SimpleNamespace()
        stub._lbl_enttec = lbl
        stub._state = types.SimpleNamespace(
            output_manager=types.SimpleNamespace(_enttec_outputs=offene),
            enttec_port_notes=notes)
        with mock.patch.object(mw, "find_enttec_port", lambda: gefunden):
            mw.MainWindow._check_hardware(stub)
        return lbl

    def test_aktiver_ausgang_ist_gruen(self):
        lbl = self._run(gefunden="/dev/ttyUSB0",
                        offene={3: _Dev("/dev/ttyUSB0")}, notes={})
        self.assertIn("/dev/ttyUSB0", lbl.text)
        self.assertIn("aktiv", lbl.text)
        self.assertIn("9DFF52", lbl.style)

    def test_der_alte_luegen_fall_ist_nicht_mehr_gruen(self):
        """Adapter steckt (VID/PID findet ihn), aber das Universe zeigt auf
        COM_FAKE — frueher gruen „OK", jetzt Warnung mit Grund im Tooltip."""
        lbl = self._run(gefunden="/dev/ttyUSB0", offene={},
                        notes={3: "Der konfigurierte Port 'COM_FAKE' ist ein "
                                  "Portname von einer anderen Plattform."})
        self.assertNotIn("9DFF52", lbl.style, "das darf NICHT gruen sein")
        self.assertIn("falsch konfiguriert", lbl.text)
        self.assertIn("COM_FAKE", lbl.tip)

    def test_registriertes_geraet_auf_unmoeglichem_port_ist_NICHT_gruen(self):
        """★ Genau der Fall, den die Testsuite zuerst verfehlt hat.

        `add_enttec` legt auch fuer einen unsinnigen Port ein Geraet an — der
        Subprozess-Proxy scheitert nicht sofort. `_enttec_outputs` ist also
        GEFUELLT, obwohl nichts rausgeht. Der erste Wurf fragte `if offene:`
        zuerst und meldete im echten Betrieb gruen „Enttec: COM_FAKE aktiv
        (1 Universe)" — die Luege, die HW-5b beseitigen soll, nur mit neuem
        Text. Headless nicht aufgefallen, weil die Tests fuer den Problemfall
        `offene={}` annahmen; gefunden erst am Screenshot der laufenden App.
        """
        lbl = self._run(gefunden="/dev/ttyUSB0",
                        offene={3: _Dev("COM_FAKE")},
                        notes={3: "Der konfigurierte Port 'COM_FAKE' ist ein "
                                  "Portname von einer anderen Plattform."})
        self.assertNotIn("9DFF52", lbl.style,
                         "ein registrierter Adapter auf einem unmoeglichen Port "
                         "darf NICHT gruen sein")
        self.assertIn("falsch konfiguriert", lbl.text)
        self.assertIn("COM_FAKE", lbl.tip)

    def test_adapter_da_aber_keinem_universe_zugewiesen(self):
        lbl = self._run(gefunden="/dev/ttyUSB0", offene={}, notes={})
        self.assertNotIn("9DFF52", lbl.style)
        self.assertIn("kein Universe", lbl.text)

    def test_gar_kein_adapter(self):
        lbl = self._run(gefunden=None, offene={}, notes={})
        self.assertIn("nicht gefunden", lbl.text)
        self.assertIn("ff4444", lbl.style)

    def test_ueberlebt_einen_state_ohne_die_neuen_felder(self):
        """Der Statusbalken laeuft auch waehrend des Hochfahrens — bevor
        ``apply_output_config`` ueberhaupt lief."""
        import types
        from src.ui import main_window as mw
        lbl = _Label()
        stub = types.SimpleNamespace(_lbl_enttec=lbl,
                                     _state=types.SimpleNamespace())
        with mock.patch.object(mw, "find_enttec_port", lambda: None):
            mw.MainWindow._check_hardware(stub)
        self.assertIn("nicht gefunden", lbl.text)


if __name__ == "__main__":
    unittest.main()
