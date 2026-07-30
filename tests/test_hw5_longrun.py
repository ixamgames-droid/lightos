"""HW-5-Langzeitlauf: Frame-Bau und Zustandserkennung (tools/hw5_longrun.py).

Warum es diese Tests gibt: das Ergebnis eines 12-Stunden-Laufs ist nicht der Lauf,
sondern sein BERICHT. Erkennt ``Run.observe`` einen Aussetzer nicht, ist die Nacht
verloren und man merkt es nicht — der Bericht sagt dann faelschlich "durchgehend
gelaufen". Die Zustandsuebergaenge werden hier deshalb gegen ein Fake-Geraet
gefahren, ohne echten Enttec.
"""
import importlib.util
import os
import unittest

_TOOL = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     "tools", "hw5_longrun.py")
_spec = importlib.util.spec_from_file_location("hw5_longrun", _TOOL)
hw5 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(hw5)


class FakeSerial:
    def __init__(self):
        self.is_open = True
        self.out_waiting = 0


class FakeDev:
    """Nachbau der von ``Run.observe`` gelesenen EnttecPro-Oberflaeche."""

    def __init__(self, port="/dev/ttyUSB0"):
        self.port = port
        self._fail_count = 0
        self._disabled = False
        self._ser = FakeSerial()

    def is_disabled(self):
        return self._disabled

    def is_open(self):
        return self._ser.is_open


def _run(tmpdir="/tmp"):
    dev = FakeDev()
    return dev, hw5.Run(dev, os.path.join(tmpdir, "hw5_test.log"),
                        os.path.join(tmpdir, "hw5_test.json"))


class FrameBuildTests(unittest.TestCase):
    def test_blackout_ist_512_nullen(self):
        f = hw5._frame_blackout()
        self.assertEqual(len(f), 512)
        self.assertEqual(set(f), {0})

    def test_heartbeat_beruehrt_genau_einen_kanal(self):
        f = hw5._frame_heartbeat(channel=1, level=64, phase=0.5)
        self.assertEqual(len(f), 512)
        self.assertEqual([i for i, v in enumerate(f) if v], [0])

    def test_heartbeat_kanalindex_ist_1_basiert(self):
        f = hw5._frame_heartbeat(channel=7, level=200, phase=0.5)
        self.assertEqual([i for i, v in enumerate(f) if v], [6])

    def test_heartbeat_ist_dreieck_und_haelt_den_deckel(self):
        """Spitze bei Phase 0.5, Null an den Raendern — sonst waere es ein Standbild
        und als Lebenszeichen wertlos (DMX haelt den letzten Wert)."""
        ch, lvl = 1, 100
        self.assertEqual(hw5._frame_heartbeat(ch, lvl, 0.0)[0], 0)
        self.assertEqual(hw5._frame_heartbeat(ch, lvl, 0.5)[0], lvl)
        self.assertEqual(hw5._frame_heartbeat(ch, lvl, 1.0)[0], 0)
        mitte = hw5._frame_heartbeat(ch, lvl, 0.25)[0]
        self.assertTrue(0 < mitte < lvl, mitte)
        for phase in (0.0, 0.2, 0.5, 0.75, 0.99):
            self.assertLessEqual(max(hw5._frame_heartbeat(ch, 255, phase)), 255)

    def test_heartbeat_klemmt_kanal_in_den_gueltigen_bereich(self):
        self.assertEqual([i for i, v in enumerate(
            hw5._frame_heartbeat(0, 64, 0.5)) if v], [0])
        self.assertEqual([i for i, v in enumerate(
            hw5._frame_heartbeat(9999, 64, 0.5)) if v], [511])


class ZustandserkennungTests(unittest.TestCase):
    def test_sauberer_lauf_meldet_keine_ereignisse(self):
        dev, run = _run()
        for _ in range(5):
            run.frames_ok += 1
            run.observe()
        self.assertEqual(run.events, [])
        self.assertEqual(run.write_errors, 0)
        self.assertIn("durchgehend", run.report())

    def test_schreibfehler_werden_gezaehlt_und_einmal_gemeldet(self):
        """Ein Fehler-Burst soll EINEN Ereignis-Eintrag erzeugen, nicht zwanzig —
        sonst ersaeuft der Bericht in Wiederholungen."""
        dev, run = _run()
        run.observe()
        for _ in range(3):
            dev._fail_count += 1
            run.observe()
        self.assertEqual(run.write_errors, 3)
        self.assertEqual(len([e for e in run.events if "SCHREIBFEHLER" in e]), 1)

    def test_auto_disable_und_selbstheilung_werden_beide_erkannt(self):
        """Genau die zwei Fragen aus HW-5: bricht es weg — und kommt es zurueck?"""
        dev, run = _run()
        run.observe()
        dev._fail_count = hw5.EnttecPro.FAIL_LIMIT
        dev._disabled = True
        run.observe()
        self.assertTrue(any("AUSGANG TOT" in e for e in run.events))

        dev._disabled = False
        dev._fail_count = 0
        run.observe()
        self.assertTrue(any("VON SELBST ZURUECK" in e for e in run.events))
        self.assertIn("Aussetzer", run.report())

    def test_erholung_ohne_disable_wird_als_erholung_gemeldet(self):
        dev, run = _run()
        run.observe()
        dev._fail_count = 3
        run.observe()
        dev._fail_count = 0
        run.observe()
        self.assertTrue(any("erholt" in e for e in run.events))

    def test_portwechsel_nach_replug_wird_protokolliert(self):
        """SERIAL-02: nach einem USB-Replug haengt der Enttec an einer neuen Nummer.
        Ohne diese Meldung liest sich der Bericht, als waere nichts passiert."""
        dev, run = _run()
        run.observe()
        dev.port = "/dev/ttyUSB1"
        run.observe()
        self.assertTrue(any("PORTWECHSEL" in e for e in run.events))

    def test_sendepuffer_hochwasser_wird_mitgefuehrt(self):
        dev, run = _run()
        dev._ser.out_waiting = 4096
        run.observe()
        dev._ser.out_waiting = 12
        run.observe()
        self.assertEqual(run.snapshot()["max_sendepuffer_bytes"], 4096)

    def test_observe_ueberlebt_ein_geschlossenes_geraet(self):
        """Am Ende des Laufs ist der Port zu — observe darf dann nicht werfen."""
        dev, run = _run()
        dev._ser.is_open = False
        run.observe()


class BerichtTests(unittest.TestCase):
    def test_bericht_nennt_die_grenze_der_messung(self):
        """Der stille Tod ist von hier aus unsichtbar. Wer das im Bericht weglaesst,
        verkauft eine Teilmessung als Freigabe."""
        _dev, run = _run()
        text = run.report()
        self.assertIn("STILLER", text)
        self.assertIn("--probe", text)

    def test_snapshot_ist_json_serialisierbar(self):
        import json
        _dev, run = _run()
        json.loads(json.dumps(run.snapshot()))


if __name__ == "__main__":
    unittest.main()
