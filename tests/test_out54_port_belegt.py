"""OUT-54: fremde Halter des DMX-Ports werden gemeldet — und nichts blockiert.

Am 26.08.2026 hingen fuenf Prozesse gleichzeitig an /dev/ttyUSB0. Das
Fehlerbild sah aus wie ein Softwarefehler in der Show: blinkendes Geraet,
nichts steuerbar — aber Blackout funktionierte. Diese Asymmetrie ist das
Erkennungszeichen: dunkel ist der einzige Zustand, ueber den sich mehrere
Sender einig sind.

OUT-53 beseitigt die haeufigste Quelle (verwaiste eigene Worker). Hier geht es
um den Rest: zweite Instanz, fremdes Programm, Waise aus einer alten Version.
"""
from __future__ import annotations

import io
import os
import tempfile
import unittest

from src.core.dmx.port_check import port_belegt_von, warne_wenn_belegt


class PortHalterTest(unittest.TestCase):
    def test_findet_einen_fremden_halter(self):
        """Gestelltes /proc: ein anderer Prozess haelt den Port."""
        with tempfile.TemporaryDirectory() as tmp:
            port = os.path.join(tmp, "ttyFAKE")
            open(port, "w").close()
            proc = os.path.join(tmp, "proc")
            fd = os.path.join(proc, "4242", "fd")
            os.makedirs(fd)
            os.symlink(port, os.path.join(fd, "7"))
            with open(os.path.join(proc, "4242", "cmdline"), "wb") as fh:
                fh.write(b"python\0main.py\0")
            treffer = port_belegt_von(port, eigene_pid=1, proc_root=proc)
            self.assertEqual([p for p, _ in treffer], [4242])
            self.assertIn("main.py", treffer[0][1])

    def test_eigener_prozess_wird_ausgelassen(self):
        """★ Sonst meldete jede Pruefung nach dem eigenen Oeffnen einen Treffer
        — der Waechter wuerde bei jedem Start Fehlalarm schlagen und damit
        umgangen."""
        with tempfile.TemporaryDirectory() as tmp:
            port = os.path.join(tmp, "ttyFAKE")
            open(port, "w").close()
            proc = os.path.join(tmp, "proc")
            fd = os.path.join(proc, "999", "fd")
            os.makedirs(fd)
            os.symlink(port, os.path.join(fd, "3"))
            self.assertEqual(port_belegt_von(port, eigene_pid=999, proc_root=proc), [])

    def test_freier_port_meldet_nichts(self):
        with tempfile.TemporaryDirectory() as tmp:
            proc = os.path.join(tmp, "proc"); os.makedirs(proc)
            self.assertEqual(port_belegt_von("/dev/ttyFREI", proc_root=proc), [])

    def test_unlesbares_proc_stuerzt_nicht_ab(self):
        """Ein Diagnose-Helfer darf den Start der Ausgabe niemals verhindern."""
        self.assertEqual(port_belegt_von("/dev/x", proc_root="/gibt/es/nicht"), [])

    def test_echter_offener_deskriptor_wird_gefunden(self):
        """Gegenprobe am laufenden System: was WIRKLICH offen ist, muss der
        Waechter finden. Ein Waechter, der nie anschlaegt, ist keiner."""
        with tempfile.NamedTemporaryFile(suffix=".port") as fh:
            # eigene_pid absichtlich falsch -> der eigene Prozess zaehlt als "fremd"
            treffer = port_belegt_von(fh.name, eigene_pid=-1)
            self.assertIn(os.getpid(), [p for p, _ in treffer])


class WarnungTest(unittest.TestCase):
    def test_warnung_nennt_pid_und_befehl(self):
        with tempfile.TemporaryDirectory() as tmp:
            port = os.path.join(tmp, "ttyFAKE"); open(port, "w").close()
            with tempfile.NamedTemporaryFile(suffix=".p") as fh:
                puffer = io.StringIO()
                from src.core.dmx import port_check
                orig = port_check.port_belegt_von
                port_check.port_belegt_von = lambda p, **k: [(4242, "python main.py")]
                try:
                    treffer = warne_wenn_belegt(port, ausgabe=puffer)
                finally:
                    port_check.port_belegt_von = orig
            text = puffer.getvalue()
            self.assertEqual(len(treffer), 1)
            self.assertIn("4242", text)
            self.assertIn("main.py", text)
            self.assertIn("Blackout", text,
                          "die Meldung sollte das Erkennungszeichen nennen")

    def test_freier_port_schweigt(self):
        """Kein Rauschen im Normalfall — sonst liest sie niemand mehr."""
        puffer = io.StringIO()
        with tempfile.TemporaryDirectory() as tmp:
            proc = os.path.join(tmp, "proc"); os.makedirs(proc)
            from src.core.dmx import port_check
            orig = port_check.port_belegt_von
            port_check.port_belegt_von = lambda p, **k: []
            try:
                warne_wenn_belegt("/dev/ttyFREI", ausgabe=puffer)
            finally:
                port_check.port_belegt_von = orig
        self.assertEqual(puffer.getvalue(), "")


class VerdrahtungTest(unittest.TestCase):
    def test_output_manager_prueft_vor_dem_oeffnen(self):
        """★ Die Pruefung muss VOR dem eigenen Oeffnen laufen — danach haelt man
        den Port selbst und die Aussage waere wertlos."""
        import inspect
        from src.core.dmx import output_manager
        quelle = inspect.getsource(output_manager._make_enttec_device)
        self.assertIn("warne_wenn_belegt", quelle)
        self.assertLess(quelle.index("warne_wenn_belegt"), quelle.index("EnttecPro(port)"))

    def test_diagnose_darf_die_ausgabe_nicht_verhindern(self):
        """Der Aufruf ist bewusst in try/except: eine kaputte Diagnose darf die
        Ausgabe nie blockieren."""
        import inspect
        from src.core.dmx import output_manager
        quelle = inspect.getsource(output_manager._make_enttec_device)
        vor = quelle.split("warne_wenn_belegt")[0]
        self.assertIn("try:", vor)


if __name__ == "__main__":
    unittest.main()
