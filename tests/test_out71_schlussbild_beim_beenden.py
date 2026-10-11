"""OUT-71: beim Beenden geht EIN sicheres Schlussbild hinaus.

Befund (Audit QA-96): ``OutputManager.stop()`` sendete nichts mehr, das
Hauptfenster rief beim Schliessen nur ``stop()``. Adapter mit eigenem Prozessor
(Enttec Pro, uDMX) und viele Art-Net-/sACN-Nodes halten das letzte Bild — wurde
LightOS mit laufendem Laser normal beendet, blieb er an.

Jetzt sendet ``stop(schlussbild=True)`` vor dem Schliessen je Ausgabe genau ein
Bild mit derselben Rechnung wie ein Blackout im laufenden Betrieb: alles
ausser der Erhalten-Maske auf 0, Laser auf ihre Aus-Werte, NOT-AUS obenauf.
Mit Zeitlimit: ein haengender Adapter haelt das Beenden nicht auf.

Es wird an kein Geraet gesendet — die Ausgaenge sind Attrappen.
"""
from __future__ import annotations

import os
import threading
import time
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from src.core.dmx.output_manager import OutputManager               # noqa: E402

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class _Ausgang:
    """Attrappe eines Enttec-artigen Ausgangs: merkt, was in welcher Reihenfolge kam."""
    process_isolated = False

    def __init__(self, protokoll=None, name="a"):
        self.name = name
        self.bilder = []
        self.protokoll = protokoll if protokoll is not None else []
        self.zu = False

    def send_dmx(self, daten):
        self.bilder.append(bytes(daten))
        self.protokoll.append((self.name, "senden"))

    def ausschreiben(self, frist_s=0.3):
        self.protokoll.append((self.name, "ausschreiben"))
        return True

    def close(self):
        self.zu = True
        self.protokoll.append((self.name, "schliessen"))


class _Netz:
    """Attrappe fuer Art-Net/sACN: send_dmx(universum, daten)."""

    def __init__(self):
        self.bilder = []
        self.zu = False

    def send_dmx(self, universum, daten):
        self.bilder.append((universum, bytes(daten)))

    def close(self):
        self.zu = True


class _Haenger(_Ausgang):
    """Ein Ausgang, dessen Schreiben nicht zurueckkommt (abgezogener Adapter)."""

    def __init__(self, sperre):
        super().__init__(name="haenger")
        self.sperre = sperre

    def send_dmx(self, daten):
        self.protokoll.append((self.name, "senden"))
        self.sperre.wait(30)


def _manager(werte=None):
    om = OutputManager()
    om.add_universe(1)
    om.grand_master = 1.0
    for adresse, wert in (werte or {1: 200, 2: 150, 10: 120, 11: 5, 20: 90}).items():
        om.universes[1].set_channel(adresse, wert)
    return om


class SchlussbildTest(unittest.TestCase):

    def test_stop_mit_schlussbild_sendet_ein_dunkles_bild_dann_schliessen(self):
        om = _manager()
        a = _Ausgang()
        om._enttec_outputs[1] = a
        om.stop(schlussbild=True)
        self.assertEqual(len(a.bilder), 1, "genau EIN Schlussbild")
        self.assertEqual(a.bilder[0], bytes(512))
        self.assertEqual([was for _n, was in a.protokoll], ["senden", "ausschreiben", "schliessen"])
        self.assertTrue(a.zu)

    def test_stop_ohne_schlussbild_sendet_nichts(self):
        """Der bisherige Weg (Tests, Werkzeuge) bleibt: nur schliessen."""
        om = _manager()
        a = _Ausgang()
        om._enttec_outputs[1] = a
        om.stop()
        self.assertEqual(a.bilder, [])
        self.assertTrue(a.zu)

    def test_alle_wege_bekommen_das_bild(self):
        om = _manager()
        a, artnet, sacn = _Ausgang(), _Netz(), _Netz()
        om._enttec_outputs[1] = a
        om._artnet_outputs[1] = artnet
        om._sacn_outputs[1] = sacn
        om.stop(schlussbild=True)
        self.assertEqual(a.bilder, [bytes(512)])
        self.assertEqual([d for _u, d in artnet.bilder], [bytes(512)])
        self.assertEqual([d for _u, d in sacn.bilder], [bytes(512)])
        self.assertTrue(a.zu and artnet.zu and sacn.zu)

    def test_laser_bekommen_ihren_aus_wert_nicht_null(self):
        """Dieselbe Rechnung wie beim Blackout: bei manchen Lasern heisst DMX 0
        an der Betriebsart „Auto“ — ein Schlussbild aus lauter Nullen schaltete
        sie EIN."""
        om = _manager()
        om.set_gm_laser_aus_mask({1: {10: 50}})          # Betriebsart: 50 = „Laser off“
        a = _Ausgang()
        om._enttec_outputs[1] = a
        om.stop(schlussbild=True)
        bild = a.bilder[0]
        self.assertEqual(bild[9], 50)
        self.assertEqual(bild[0], 0)
        self.assertEqual(bild[10], 0)

    def test_erhalten_maske_gilt_wie_beim_blackout(self):
        """Moving Heads fahren beim Beenden nicht in die Grundstellung."""
        om = _manager()
        om.set_blackout_keep_mask({1: frozenset({20})})  # Pan eines Geraets mit Dimmer
        a = _Ausgang()
        om._enttec_outputs[1] = a
        om.stop(schlussbild=True)
        self.assertEqual(a.bilder[0][19], 90)
        self.assertEqual(a.bilder[0][0], 0)

    def test_schlussbild_aendert_den_blackout_schalter_nicht(self):
        om = _manager()
        om._enttec_outputs[1] = _Ausgang()
        om.stop(schlussbild=True)
        self.assertFalse(om.blackout)

    def test_ohne_ausgang_geht_nichts_schief(self):
        om = _manager()
        om.stop(schlussbild=True)
        om.stop(schlussbild=True)                       # zweites Stoppen

    def test_zweites_stop_sendet_kein_zweites_bild(self):
        om = _manager()
        a = _Ausgang()
        om._enttec_outputs[1] = a
        om.stop(schlussbild=True)
        om.stop(schlussbild=True)
        self.assertEqual(len(a.bilder), 1)


class ZeitlimitTest(unittest.TestCase):

    def test_haengender_adapter_haelt_das_beenden_nicht_auf(self):
        sperre = threading.Event()
        self.addCleanup(sperre.set)
        om = _manager()
        om.SCHLUSSBILD_FRIST_S = 0.4
        h = _Haenger(sperre)
        om._enttec_outputs[1] = h
        t0 = time.monotonic()
        om.stop(schlussbild=True)
        dauer = time.monotonic() - t0
        self.assertLess(dauer, 2.0, f"stop() hing {dauer:.1f} s")
        # Neben einem noch laufenden Schreiben wird NICHT geschlossen
        # (Schutz vor einer Zugriffsverletzung unter Windows, wie bisher).
        self.assertFalse(h.zu)

    def test_haengender_adapter_laesst_prozess_ausgaenge_trotzdem_dunkel_enden(self):
        """Der haengende Adapter blockiert das gemeinsame Senden — ein
        prozessisolierter Ausgang (schreibt nur in gemeinsamen Speicher) bekommt
        sein Schlussbild trotzdem und wird beendet."""
        sperre = threading.Event()
        self.addCleanup(sperre.set)
        om = _manager()
        om.add_universe(2)
        om.universes[2].set_channel(1, 222)
        om.SCHLUSSBILD_FRIST_S = 0.4
        om._enttec_outputs[1] = _Haenger(sperre)
        p = _Ausgang(name="prozess")
        p.process_isolated = True
        om._enttec_outputs[2] = p
        om.stop(schlussbild=True)
        self.assertTrue(p.zu)
        self.assertTrue(p.bilder, "der Prozess-Ausgang bekam kein Schlussbild")
        self.assertEqual(p.bilder[-1], bytes(512))


    def test_haengender_adapter_netz_ausgaenge_enden_trotzdem_dunkel(self):
        """Ein toter USB-Adapter darf nicht verhindern, dass der Laser am
        Art-Net-Node beim Beenden ausgeht."""
        sperre = threading.Event()
        self.addCleanup(sperre.set)
        om = _manager()
        om.add_universe(2)
        om.universes[2].set_channel(5, 255)
        om.set_gm_laser_aus_mask({2: {5: 40}})
        om.SCHLUSSBILD_FRIST_S = 0.4
        om._enttec_outputs[1] = _Haenger(sperre)
        artnet, sacn = _Netz(), _Netz()
        om._artnet_outputs[2] = artnet
        om._sacn_outputs[2] = sacn
        om.stop(schlussbild=True)
        self.assertTrue(artnet.bilder and sacn.bilder)
        self.assertEqual(artnet.bilder[-1][0], 1)               # Art-Net zaehlt ab 0
        self.assertEqual(sacn.bilder[-1][0], 2)
        for _u, bild in (artnet.bilder[-1], sacn.bilder[-1]):
            self.assertEqual(bild[4], 40)                       # Laser auf Aus-Wert
            self.assertEqual(sum(bild) - 40, 0)
        self.assertFalse(artnet.zu or sacn.zu)                  # neben dem Haenger nichts schliessen


class AusgabeEntfernenTest(unittest.TestCase):

    def test_entfernter_ausgang_bekommt_vorher_ein_dunkles_bild(self):
        """Der Ausgang geht wirklich (Universum geloescht, „Disabled“,
        abgewaehlt): der Adapter hielte sonst das letzte Bild."""
        om = _manager()
        a = _Ausgang()
        om._enttec_outputs[1] = a
        om.remove_output(1, schlussbild=True)
        self.assertEqual(a.bilder, [bytes(512)])
        self.assertEqual([was for _n, was in a.protokoll], ["senden", "ausschreiben", "schliessen"])

    def test_ohne_auftrag_kein_dunkles_bild(self):
        """Kommt gleich ein Nachfolger fuer dasselbe Universum („Uebernehmen“
        mit unveraenderter Einstellung), darf die Buehne nicht dunkel blitzen."""
        om = _manager()
        a = _Ausgang()
        om._enttec_outputs[1] = a
        om.remove_output(1)
        self.assertEqual(a.bilder, [])
        self.assertTrue(a.zu)

    def test_netz_ausgaenge_bekommen_das_bild_an_ihre_universe_nummer(self):
        om = _manager()
        artnet, sacn = _Netz(), _Netz()
        om._artnet_outputs[1] = artnet
        om._sacn_outputs[1] = sacn
        om._out_universe[1] = 7                         # konfigurierte externe Nummer
        om.remove_output(1, schlussbild=True)
        self.assertEqual(artnet.bilder, [(7, bytes(512))])
        self.assertEqual(sacn.bilder, [(7, bytes(512))])

    def test_netz_ausgaenge_ohne_externe_nummer(self):
        om = _manager()
        artnet, sacn = _Netz(), _Netz()
        om._artnet_outputs[1] = artnet
        om._sacn_outputs[1] = sacn
        om.remove_output(1, schlussbild=True)
        self.assertEqual(artnet.bilder, [(0, bytes(512))])      # Art-Net zaehlt ab 0
        self.assertEqual(sacn.bilder, [(1, bytes(512))])

    def test_ausser_laesst_den_bleibenden_weg_in_ruhe(self):
        """NET-12: bleibt ein Adaptertyp stehen (Uebergabe), laeuft das Universum
        weiter — der bleibende Weg bekommt KEIN dunkles Bild."""
        om = _manager()
        a, sacn = _Ausgang(), _Netz()
        om._enttec_outputs[1] = a
        om._sacn_outputs[1] = sacn
        om.remove_output(1, ausser="sacn", schlussbild=True)
        self.assertEqual(sacn.bilder, [])
        self.assertFalse(sacn.zu)
        self.assertEqual(a.bilder, [bytes(512)])        # der entfernte Weg endet dunkel

    def test_laser_aus_wert_auch_beim_entfernen(self):
        om = _manager()
        om.set_gm_laser_aus_mask({1: {10: 50}})
        a = _Ausgang()
        om._enttec_outputs[1] = a
        om.remove_output(1, schlussbild=True)
        self.assertEqual(a.bilder[0][9], 50)

    def test_aufrufer_setzen_das_bild_nur_wenn_der_ausgang_wirklich_geht(self):
        with open(os.path.join(_REPO, "src", "core", "app_state.py"), encoding="utf-8") as f:
            zustand = f.read()
        # geloeschtes Universum und „Disabled“: ja. Typwechsel/Neuaufbau: nein.
        self.assertEqual(zustand.count("schlussbild=True)"), 2)
        self.assertIn('if output == "Disabled":\n'
                      '                    self.output_manager.remove_output(num, schlussbild=True)\n'
                      '                else:\n'
                      '                    self.output_manager.remove_output(num)\n', zustand)
        with open(os.path.join(_REPO, "src", "ui", "widgets", "output_config.py"),
                  encoding="utf-8") as f:
            dialog = f.read()
        # Abwaehlen von Art-Net und sACN: ja. Die drei Ersetzen-Wege: nein.
        self.assertEqual(dialog.count("schlussbild=True)"), 2)
        self.assertEqual(dialog.count("remove_output("), 5)


class WorkerTest(unittest.TestCase):
    """Der Sende-Prozess des Enttec schickt beim geordneten Stopp das zuletzt
    veroeffentlichte Bild noch einmal und schreibt es aus, bevor er schliesst."""

    def test_geordneter_stopp_sendet_das_letzte_bild_und_schreibt_aus(self):
        from src.core.dmx import serial_process as sp
        protokoll = []
        geraet = _Ausgang(protokoll, "worker")
        geraet.is_disabled = lambda: False
        puffer = bytearray(512)
        stopp = type("F", (), {"value": 0})()
        status = type("S", (), {"value": 0})()
        runden = {"n": 0}

        def schlafen(_s):
            runden["n"] += 1
            if runden["n"] == 2:
                puffer[0] = 77                      # „Schlussbild“ veroeffentlicht …
                stopp.value = 1                     # … und sofort Stopp
        sp._serial_worker_loop(lambda: geraet, puffer, stopp, status,
                               frame_interval=0.0, sleep=schlafen)
        self.assertEqual(geraet.bilder[-1][0], 77, "das zuletzt veroeffentlichte Bild ging nicht mehr hinaus")
        self.assertEqual([was for _n, was in protokoll][-3:], ["senden", "ausschreiben", "schliessen"])

    def test_tod_des_elternprozesses_sendet_nichts_mehr(self):
        """OUT-53 bleibt: ist der Elternprozess weg, wird nur noch geschlossen."""
        from src.core.dmx import serial_process as sp
        protokoll = []
        geraet = _Ausgang(protokoll, "worker")
        geraet.is_disabled = lambda: False
        stopp = type("F", (), {"value": 0})()
        status = type("S", (), {"value": 0})()
        leben = iter([True, False])
        sp._serial_worker_loop(lambda: geraet, bytearray(512), stopp, status,
                               frame_interval=0.0, sleep=lambda _s: None,
                               parent_alive=lambda: next(leben))
        self.assertEqual([was for _n, was in protokoll], ["senden", "schliessen"])


class EnttecAusschreibenTest(unittest.TestCase):

    def _geraet(self, wartend):
        from src.core.dmx.enttec_pro import EnttecPro
        dev = EnttecPro.__new__(EnttecPro)
        dev._disabled = False
        folge = iter(wartend)
        dev._ser = type("Ser", (), {"is_open": True,
                                    "out_waiting": property(lambda _s: next(folge, 0))})()
        return dev

    def test_wartet_bis_der_puffer_leer_ist(self):
        dev = self._geraet([518, 200, 0])
        self.assertTrue(dev.ausschreiben(frist_s=1.0))

    def test_gibt_nach_der_frist_auf(self):
        dev = self._geraet([518] * 100000)
        t0 = time.monotonic()
        self.assertFalse(dev.ausschreiben(frist_s=0.15))
        self.assertLess(time.monotonic() - t0, 1.0)


class HauptfensterTest(unittest.TestCase):

    def test_beenden_ruft_stop_mit_schlussbild(self):
        with open(os.path.join(_REPO, "src", "ui", "main_window.py"), encoding="utf-8") as f:
            quelle = f.read()
        self.assertIn("output_manager.stop(schlussbild=True)", quelle)
        self.assertNotIn("output_manager.stop()", quelle)


if __name__ == "__main__":
    unittest.main()
