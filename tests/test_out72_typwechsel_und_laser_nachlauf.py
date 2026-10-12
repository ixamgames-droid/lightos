"""OUT-72: zwei Luecken, die OUT-71 offen liess.

**(a) Typ- oder Zielwechsel einer Ausgabe.** OUT-71 gab dem Adapter ein
Schlussbild, wenn sein Universum geloescht, auf „Disabled“ gestellt oder
abgewaehlt wurde — nicht aber, wenn ein ANDERER Adapter nachfolgt: ein Enttec,
dessen Universum auf Art-Net umgestellt wird, hielt sein letztes Bild. Ebenso
ein Adapter, dessen Universum auf einen anderen Anschluss oder eine andere
Adresse zieht. Der unveraenderte Neuaufbau („Uebernehmen“ ohne Aenderung) darf
dagegen weiter nicht dunkel blitzen.

**(b) Frei gewordene Laser-Adressen.** Wird ein Laser entpatcht, umadressiert
oder mit einem Show-Wechsel ersetzt, fiel seine Adresse auf 0. Bei einem Laser,
dessen Betriebsart bei DMX 0 „Auto run“ heisst, ist das AN — und er steht in
keiner Maske mehr. Jetzt bleibt sein Aus-Wert auf der Leitung, bis die Adresse
wieder gepatcht ist oder die Ausgabe endet.

Es wird an kein Geraet gesendet — alle Ausgaenge sind Attrappen.
"""
from __future__ import annotations

import io
import json
import os
import shutil
import tempfile
import threading
import types
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import src.core.app_state as A                                   # noqa: E402
from src.core.app_state import AppState                          # noqa: E402
from src.core.dmx import output_manager as om_mod                # noqa: E402
from src.core.dmx.output_manager import OutputManager            # noqa: E402

DUNKEL = bytes(512)


# ── Attrappen der Ausgaenge ─────────────────────────────────────────────────

class _Enttec:
    process_isolated = False

    def __init__(self, port):
        self.port = port
        self.bilder: list[bytes] = []
        self.zu = False

    def send_dmx(self, daten):
        self.bilder.append(bytes(daten))

    def ausschreiben(self, frist_s=0.3):
        return True

    def is_open(self):
        return not self.zu

    def close(self):
        self.zu = True


class _Udmx(_Enttec):
    """uDMX-Sender (OUT-68): ``port`` ist der Adapter-Schluessel; ein
    ``ausschreiben`` hat er nicht."""
    ausschreiben = None

    def __init__(self, schluessel="", streng=False):
        super().__init__(schluessel)
        self.streng = streng

    def setze_streng(self, an):
        self.streng = bool(an)


class _ArtNet:
    def __init__(self, target_ip="255.255.255.255"):
        self.target_ip = target_ip
        self.bilder: list[tuple[int, bytes]] = []
        self.zu = False

    def send_dmx(self, universum, daten):
        self.bilder.append((universum, bytes(daten)))

    def close(self):
        self.zu = True


class _SACN(_ArtNet):
    def __init__(self, target_ip=None):
        super().__init__(target_ip)
        self._target_ip = target_ip


def _manager(werte=None):
    om = OutputManager()
    om.add_universe(1)
    om.add_universe(2)
    om.grand_master = 1.0
    for adresse, wert in (werte or {1: 200, 2: 150, 10: 120}).items():
        om.universes[1].set_channel(adresse, wert)
    return om


class _MitAttrappen(unittest.TestCase):
    """Ersetzt die Geraete-Fabriken des Managers — ``add_*`` oeffnet nichts."""

    def setUp(self):
        self.gebaut: list = []
        orig = (om_mod.ArtNetSender, om_mod.SACNSender, om_mod._make_enttec_device,
                om_mod._make_udmx_device)

        def merke(klasse):
            def bauen(*a, **k):
                dev = klasse(*a, **k)
                self.gebaut.append(dev)
                return dev
            return bauen

        om_mod.ArtNetSender = merke(_ArtNet)
        om_mod.SACNSender = merke(_SACN)
        om_mod._make_enttec_device = merke(_Enttec)
        om_mod._make_udmx_device = merke(_Udmx)

        def zurueck():
            (om_mod.ArtNetSender, om_mod.SACNSender, om_mod._make_enttec_device,
             om_mod._make_udmx_device) = orig
        self.addCleanup(zurueck)


# ══════════════════════════════════════════════════════════════════════════════
# A) Typ- und Zielwechsel: wer wirklich geht, endet dunkel
# ══════════════════════════════════════════════════════════════════════════════

UDMX, UDMX2 = "16c0:05dc@1-4", "16c0:05dc@1-5"


class NachfolgerAngesagtTest(_MitAttrappen):

    def test_typwechsel_enttec_auf_artnet_der_enttec_endet_dunkel(self):
        om = _manager()
        alt = _Enttec("COM3")
        om._enttec_outputs[1] = alt
        om.nachfolger_ansagen(1, "artnet", "2.0.0.1")
        om.remove_output(1)
        self.assertEqual(alt.bilder, [DUNKEL], "sonst haelt der Enttec sein letztes Bild")
        self.assertTrue(alt.zu)

    def test_typwechsel_artnet_auf_enttec_der_knoten_endet_dunkel(self):
        om = _manager()
        alt = _ArtNet("2.0.0.1")
        om._artnet_outputs[1] = alt
        om.nachfolger_ansagen(1, "enttec", "COM3")
        om.remove_output(1)
        self.assertEqual(alt.bilder, [(0, DUNKEL)])

    def test_derselbe_adapter_kommt_wieder_kein_dunkel_blitzer(self):
        om = _manager()
        alt = _Enttec("COM3")
        om._enttec_outputs[1] = alt
        om.nachfolger_ansagen(1, "enttec", "COM3")
        om.remove_output(1)
        self.assertEqual(alt.bilder, [], "„Uebernehmen“ ohne Aenderung darf nicht blitzen")
        self.assertTrue(alt.zu)

    def test_anderer_anschluss_der_alte_adapter_endet_dunkel(self):
        om = _manager()
        alt = _Enttec("COM3")
        om._enttec_outputs[1] = alt
        om.nachfolger_ansagen(1, "enttec", "COM4")
        om.remove_output(1)
        self.assertEqual(alt.bilder, [DUNKEL])

    def test_andere_adresse_der_alte_knoten_endet_dunkel(self):
        om = _manager()
        alt = _ArtNet("2.0.0.1")
        om._artnet_outputs[1] = alt
        om.nachfolger_ansagen(1, "artnet", "2.0.0.2")
        om.remove_output(1)
        self.assertEqual(alt.bilder, [(0, DUNKEL)])

    def test_gleiche_adresse_anderes_netz_universum_endet_dunkel(self):
        om = _manager()
        alt = _ArtNet("2.0.0.1")
        om._artnet_outputs[1] = alt
        om._out_universe[1] = 7
        om.nachfolger_ansagen(1, "artnet", "2.0.0.1", 9)
        om.remove_output(1)
        self.assertEqual(alt.bilder, [(7, DUNKEL)], "Universum 7 des Knotens bliebe stehen")

    def test_ausgeschriebene_vorgabe_ist_dasselbe_netz_universum(self):
        """Art-Net ohne Angabe sendet auf ``n-1`` — eine ausgeschriebene 0 fuer
        Universum 1 ist dasselbe Ziel, kein Wechsel."""
        om = _manager()
        alt = _ArtNet("2.0.0.1")
        om._artnet_outputs[1] = alt
        om.nachfolger_ansagen(1, "artnet", "2.0.0.1", 0)
        om.remove_output(1)
        self.assertEqual(alt.bilder, [])

    def test_sacn_von_multicast_auf_unicast_endet_dunkel(self):
        om = _manager()
        alt = _SACN(None)
        om._sacn_outputs[1] = alt
        om.nachfolger_ansagen(1, "sacn", "10.0.0.5")
        om.remove_output(1)
        self.assertEqual(alt.bilder, [(1, DUNKEL)])

    def test_mehrere_alte_wege_nur_der_bleibende_blitzt_nicht(self):
        om = _manager()
        enttec, artnet = _Enttec("COM3"), _ArtNet("2.0.0.1")
        om._enttec_outputs[1] = enttec
        om._artnet_outputs[1] = artnet
        om.nachfolger_ansagen(1, "artnet", "2.0.0.1")
        om.remove_output(1)
        self.assertEqual(enttec.bilder, [DUNKEL])
        self.assertEqual(artnet.bilder, [])

    def test_die_ansage_gilt_fuer_genau_ein_entfernen(self):
        om = _manager()
        om.nachfolger_ansagen(1, "artnet", "2.0.0.1")
        om.remove_output(1)                         # nichts da, Ansage verbraucht
        alt = _Enttec("COM3")
        om._enttec_outputs[1] = alt
        om.remove_output(1)
        self.assertEqual(alt.bilder, [], "eine alte Ansage darf nicht nachwirken")

    def test_die_ansage_gilt_nur_fuer_ihr_universum(self):
        om = _manager()
        alt = _Enttec("COM3")
        om._enttec_outputs[2] = alt
        om.nachfolger_ansagen(1, "artnet", "2.0.0.1")
        om.remove_output(2)
        self.assertEqual(alt.bilder, [])

    def test_ohne_ansage_bleibt_es_wie_bisher(self):
        om = _manager()
        alt = _Enttec("COM3")
        om._enttec_outputs[1] = alt
        om.remove_output(1)
        self.assertEqual(alt.bilder, [])

    def test_ausser_laesst_den_bleibenden_typ_in_ruhe(self):
        """sACN-„Uebernehmen“ laesst den Sender fuer die Uebergabe stehen
        (NET-12); die fremden Adapter gehen und enden dunkel."""
        om = _manager()
        enttec, sacn = _Enttec("COM3"), _SACN(None)
        om._enttec_outputs[1] = enttec
        om._sacn_outputs[1] = sacn
        om.nachfolger_ansagen(1, "sacn", "")
        om.remove_output(1, ausser="sacn")
        self.assertEqual(enttec.bilder, [DUNKEL])
        self.assertEqual(sacn.bilder, [])
        self.assertFalse(sacn.zu)

    def test_das_schlussbild_traegt_den_laser_aus_wert(self):
        om = _manager()
        om.set_gm_laser_aus_mask({1: {10: 50}})
        alt = _Enttec("COM3")
        om._enttec_outputs[1] = alt
        om.nachfolger_ansagen(1, "artnet", "2.0.0.1")
        om.remove_output(1)
        self.assertEqual(alt.bilder[0][9], 50)

    def test_unbekannter_typ_wird_abgewiesen(self):
        with self.assertRaises(ValueError):
            _manager().nachfolger_ansagen(1, "dmx512")

    # ── uDMX (OUT-68) ────────────────────────────────────────────────────────

    def test_typwechsel_enttec_auf_udmx_der_enttec_endet_dunkel(self):
        om = _manager()
        alt = _Enttec("COM3")
        om._enttec_outputs[1] = alt
        om.nachfolger_ansagen(1, "udmx", UDMX)
        om.remove_output(1)
        self.assertEqual(alt.bilder, [DUNKEL])

    def test_typwechsel_udmx_auf_artnet_der_udmx_endet_dunkel(self):
        om = _manager()
        om.set_gm_laser_aus_mask({1: {10: 50}})
        alt = _Udmx(UDMX)
        om._udmx_outputs[1] = alt
        om.nachfolger_ansagen(1, "artnet", "2.0.0.1")
        om.remove_output(1)
        self.assertEqual(len(alt.bilder), 1, "sonst haelt der uDMX-Adapter sein letztes Bild")
        self.assertEqual(alt.bilder[0][9], 50)
        self.assertEqual(sum(alt.bilder[0]), 50)
        self.assertTrue(alt.zu)

    def test_derselbe_udmx_kommt_wieder_kein_dunkel_blitzer(self):
        om = _manager()
        alt = _Udmx(UDMX)
        om._udmx_outputs[1] = alt
        om.nachfolger_ansagen(1, "udmx", UDMX)
        om.remove_output(1)
        self.assertEqual(alt.bilder, [])
        self.assertTrue(alt.zu)

    def test_anderer_udmx_adapter_der_alte_endet_dunkel(self):
        om = _manager()
        alt = _Udmx(UDMX)
        om._udmx_outputs[1] = alt
        om.nachfolger_ansagen(1, "udmx", UDMX2)
        om.remove_output(1)
        self.assertEqual(alt.bilder, [DUNKEL])

    def test_ein_enttec_mit_demselben_text_ist_kein_udmx(self):
        om = _manager()
        alt = _Enttec(UDMX)
        om._enttec_outputs[1] = alt
        om.nachfolger_ansagen(1, "udmx", UDMX)
        om.remove_output(1)
        self.assertEqual(alt.bilder, [DUNKEL])

    def test_die_engine_wird_dabei_nicht_getickt(self):
        om = _manager()
        ticks = []
        om.add_tick_callback(ticks.append)
        om._enttec_outputs[1] = _Enttec("COM3")
        om.nachfolger_ansagen(1, "artnet", "2.0.0.1")
        om.remove_output(1)
        self.assertEqual(ticks, [])


class TauschDirektTest(_MitAttrappen):
    """``add_*`` auf ein Universum, das den Typ schon hat (ohne vorheriges
    Entfernen): der Vorgaenger endet dunkel, wenn das Ziel ein anderes ist."""

    def test_artnet_andere_adresse(self):
        om = _manager()
        om.add_artnet(1, "2.0.0.1")
        alt = self.gebaut[-1]
        om.add_artnet(1, "2.0.0.2")
        self.assertEqual(alt.bilder, [(0, DUNKEL)])
        self.assertTrue(alt.zu)

    def test_artnet_gleiche_adresse_kein_bild(self):
        om = _manager()
        om.add_artnet(1, "2.0.0.1")
        alt = self.gebaut[-1]
        om.add_artnet(1, "2.0.0.1")
        self.assertEqual(alt.bilder, [])
        self.assertTrue(alt.zu)

    def test_artnet_anderes_netz_universum(self):
        om = _manager()
        om.add_artnet(1, "2.0.0.1", out_universe=4)
        alt = self.gebaut[-1]
        om.add_artnet(1, "2.0.0.1", out_universe=5)
        self.assertEqual(alt.bilder, [(4, DUNKEL)])

    def test_sacn_andere_adresse(self):
        om = _manager()
        om.add_sacn(1, "10.0.0.5")
        alt = self.gebaut[-1]
        om.add_sacn(1, "10.0.0.6")
        self.assertEqual(alt.bilder, [(1, DUNKEL)])

    def test_sacn_unveraendert_kein_bild(self):
        om = _manager()
        om.add_sacn(1, None)
        alt = self.gebaut[-1]
        om.add_sacn(1, None)
        self.assertEqual(alt.bilder, [])

    def test_enttec_anderer_anschluss_auf_demselben_universum(self):
        om = _manager()
        om.add_enttec(1, "COM3")
        alt = self.gebaut[-1]
        om.add_enttec(1, "COM4")
        self.assertEqual(alt.bilder, [DUNKEL])

    def test_enttec_zieht_auf_ein_anderes_universum_kein_bild(self):
        """Derselbe Adapter sendet gleich das andere Universum — er geht nicht."""
        om = _manager()
        om.add_enttec(2, "COM3")
        alt = self.gebaut[-1]
        om.add_enttec(1, "COM3")
        self.assertEqual(alt.bilder, [])
        self.assertTrue(alt.zu, "der Anschluss wird fuer das neue Universum neu geoeffnet")

    def test_udmx_anderer_adapter_auf_demselben_universum(self):
        om = _manager()
        om.add_udmx(1, UDMX)
        alt = self.gebaut[-1]
        om.add_udmx(1, UDMX2)
        self.assertEqual(alt.bilder, [DUNKEL])
        self.assertTrue(alt.zu)
        self.assertEqual(om._udmx_outputs[1].port, UDMX2)

    def test_udmx_unveraendert_kein_bild(self):
        om = _manager()
        om.add_udmx(1, UDMX)
        alt = self.gebaut[-1]
        om.add_udmx(1, UDMX)
        self.assertEqual(alt.bilder, [])
        self.assertTrue(alt.zu)

    def test_udmx_zieht_auf_ein_anderes_universum_kein_bild(self):
        om = _manager()
        om.add_udmx(2, UDMX)
        alt = self.gebaut[-1]
        om.add_udmx(1, UDMX)
        self.assertEqual(alt.bilder, [])
        self.assertNotIn(2, om._udmx_outputs)


#: E1.31: Options-Byte (Bit 6 = Stream_Terminated), Universum, DMX-Daten.
_OPTIONEN, _UNIVERSUM, _DATEN = 112, 113, 126


class _Mitschrift:
    """Ersatz fuer den UDP-Socket des echten sACN-Senders: schreibt mit, sendet nichts."""

    def __init__(self, pakete):
        self._pakete = pakete

    def sendto(self, paket, ziel):
        self._pakete.append((bytes(paket), ziel[0]))

    def setsockopt(self, *_a):
        pass

    def bind(self, *_a):
        pass

    def close(self):
        pass


class SacnUebergabeBleibtHeilTest(unittest.TestCase):
    """Der ECHTE sACN-Sender: bei ihm heisst Senden auch „Besitz des Universums
    uebernehmen“ (NET-12). Das Schlussbild des alten Senders darf deshalb keine
    Stream-Termination fuer ein Universum nach sich ziehen, das der neue
    weiterfuehrt."""

    def setUp(self):
        from unittest import mock
        from src.core.dmx import sacn as sacn_modul
        self.pakete: list[tuple[bytes, str]] = []
        p = mock.patch.object(sacn_modul.socket, "socket",
                              lambda *_a, **_k: _Mitschrift(self.pakete))
        p.start()
        self.addCleanup(p.stop)
        self.om = OutputManager()
        self.om.add_universe(1)
        self.om.universes[1].set_channel(1, 200)
        self.addCleanup(self.om.stop)

    def _laeuft(self, ziel, nummer, **kw):
        self.om.add_sacn(1, ziel, **kw)
        self.om._sacn_outputs[1].send_dmx(nummer, bytes([200]) + bytes(511))
        self.assertTrue(self.pakete, "Vorbedingung: der Sender sendet")
        self.pakete.clear()

    def _an(self, ziel):
        daten = [p for p, z in self.pakete if z == ziel and not p[_OPTIONEN] & 0x40]
        ende = [p for p, z in self.pakete if z == ziel and p[_OPTIONEN] & 0x40]
        return daten, ende

    def test_andere_adresse_dunkles_bild_aber_keine_termination(self):
        self._laeuft("127.0.0.1", 1)
        self.om.add_sacn(1, "127.0.0.2")
        daten, ende = self._an("127.0.0.1")
        self.assertEqual(len(daten), 1, "genau ein Schlussbild an das alte Ziel")
        self.assertEqual(daten[0][_DATEN:_DATEN + 512], bytes(512))
        self.assertEqual(ende, [], "das Universum laeuft fuer die Quelle weiter")

    def test_unveraendert_weder_bild_noch_termination(self):
        self._laeuft("127.0.0.1", 1)
        self.om.add_sacn(1, "127.0.0.1")
        self.assertEqual(self.pakete, [])

    def test_andere_netz_nummer_die_alte_endet_wirklich(self):
        self._laeuft("127.0.0.1", 7, out_universe=7)
        self.om.add_sacn(1, "127.0.0.1", out_universe=9)
        daten, ende = self._an("127.0.0.1")
        self.assertEqual(len(daten), 1)
        self.assertEqual(int.from_bytes(daten[0][_UNIVERSUM:_UNIVERSUM + 2], "big"), 7)
        self.assertEqual(daten[0][_DATEN:_DATEN + 512], bytes(512))
        self.assertTrue(ende, "Universum 7 sendet niemand mehr — Termination ist richtig")
        self.assertEqual({int.from_bytes(p[_UNIVERSUM:_UNIVERSUM + 2], "big") for p in ende},
                         {7})


class KonfigurationAnwendenTest(_MitAttrappen):
    """``apply_output_config`` mit dem echten Manager."""

    def setUp(self):
        super().setUp()
        self._dir = tempfile.mkdtemp(prefix="lightos_out72_")
        self.addCleanup(shutil.rmtree, self._dir, True)
        self.pfad = os.path.join(self._dir, "universes.json")
        self.om = _manager()
        self.stub = types.SimpleNamespace(output_manager=self.om,
                                          universes=self.om.universes)
        self.addCleanup(self.om.stop)

    def _anwenden(self, zeilen):
        with io.open(self.pfad, "w", encoding="utf-8") as f:
            f.write(json.dumps(zeilen))
        AppState.apply_output_config(self.stub, path=self.pfad)

    def test_typwechsel_in_der_tabelle_der_alte_adapter_endet_dunkel(self):
        self._anwenden([{"num": 1, "output": "Enttec", "patch": "COM3"}])
        enttec = self.om._enttec_outputs[1]
        self._anwenden([{"num": 1, "output": "ArtNet", "patch": "2.0.0.1"}])
        self.assertEqual(enttec.bilder, [DUNKEL])
        self.assertTrue(enttec.zu)
        self.assertEqual(self.om._artnet_outputs[1].target_ip, "2.0.0.1")

    def test_unveraendert_uebernehmen_blitzt_nicht(self):
        zeilen = [{"num": 1, "output": "Enttec", "patch": "COM3"},
                  {"num": 2, "output": "ArtNet", "patch": "2.0.0.1", "out_universe": 4}]
        self._anwenden(zeilen)
        erste = list(self.gebaut)
        self._anwenden(zeilen)
        self._anwenden(zeilen)
        self.assertEqual([d.bilder for d in erste], [[], []])

    def test_anderer_anschluss_in_der_tabelle(self):
        self._anwenden([{"num": 1, "output": "Enttec", "patch": "COM3"}])
        alt = self.om._enttec_outputs[1]
        self._anwenden([{"num": 1, "output": "Enttec", "patch": "COM4"}])
        self.assertEqual(alt.bilder, [DUNKEL])

    def test_enttec_zeile_ohne_anschluss_der_alte_endet_dunkel(self):
        self._anwenden([{"num": 1, "output": "Enttec", "patch": "COM3"}])
        alt = self.om._enttec_outputs[1]
        self._anwenden([{"num": 1, "output": "Enttec", "patch": ""}])
        self.assertEqual(alt.bilder, [DUNKEL])
        self.assertNotIn(1, self.om._enttec_outputs)

    def test_typwechsel_enttec_auf_udmx_in_der_tabelle(self):
        self._anwenden([{"num": 1, "output": "Enttec", "patch": "COM3"}])
        enttec = self.om._enttec_outputs[1]
        self._anwenden([{"num": 1, "output": "uDMX", "patch": UDMX}])
        self.assertEqual(enttec.bilder, [DUNKEL])
        self.assertEqual(self.om._udmx_outputs[1].port, UDMX)

    def test_typwechsel_udmx_auf_sacn_in_der_tabelle(self):
        self._anwenden([{"num": 1, "output": "uDMX", "patch": UDMX}])
        udmx = self.om._udmx_outputs[1]
        self._anwenden([{"num": 1, "output": "sACN", "patch": ""}])
        self.assertEqual(udmx.bilder, [DUNKEL])
        self.assertTrue(udmx.zu)

    def test_udmx_unveraendert_uebernehmen_blitzt_nicht(self):
        zeilen = [{"num": 1, "output": "uDMX", "patch": UDMX}]
        self._anwenden(zeilen)
        erster = self.om._udmx_outputs[1]
        self._anwenden(zeilen)
        self._anwenden(zeilen)
        self.assertEqual(erster.bilder, [])

    def test_anderer_udmx_adapter_in_der_tabelle(self):
        self._anwenden([{"num": 1, "output": "uDMX", "patch": UDMX}])
        alt = self.om._udmx_outputs[1]
        self._anwenden([{"num": 1, "output": "uDMX", "patch": UDMX2}])
        self.assertEqual(alt.bilder, [DUNKEL])

    def test_disabled_bleibt_wie_seit_out71(self):
        self._anwenden([{"num": 1, "output": "ArtNet", "patch": "2.0.0.1"}])
        alt = self.om._artnet_outputs[1]
        self._anwenden([{"num": 1, "output": "Disabled", "patch": ""}])
        self.assertEqual(alt.bilder, [(0, DUNKEL)])

    def test_attrappe_ohne_ansage_methode_laeuft_wie_bisher(self):
        """Bestandstests reichen Manager-Attrappen, die nur ``remove_output(u)``
        kennen — die Ansage ist deshalb kein Parameter."""
        rufe = []
        fake = types.SimpleNamespace(
            ausgabe_status=lambda: [],
            add_universe=lambda u: object(),
            remove_output=lambda u: rufe.append(("weg", u)),
            add_artnet=lambda u, ip, out_universe=None: rufe.append(("artnet", u, ip)))
        stub = types.SimpleNamespace(output_manager=fake, universes={})
        with io.open(self.pfad, "w", encoding="utf-8") as f:
            f.write(json.dumps([{"num": 1, "output": "ArtNet", "patch": "2.0.0.1"}]))
        AppState.apply_output_config(stub, path=self.pfad)
        self.assertEqual(rufe, [("weg", 1), ("artnet", 1, "2.0.0.1")])


class DialogSagtAnTest(unittest.TestCase):
    """Die vier „Verbinden“/„Uebernehmen“ der Einzel-Reiter sagen ihren
    Nachfolger an, BEVOR sie entfernen."""

    def test_reihenfolge_im_quelltext(self):
        import inspect
        from src.ui.widgets import output_config as oc
        for methode, name in ((oc.OutputConfigDialog._connect_enttec, "enttec"),
                              (oc.OutputConfigDialog._connect_udmx, "udmx"),
                              (oc.OutputConfigDialog._apply_artnet, "artnet"),
                              (oc.OutputConfigDialog._apply_sacn, "sacn")):
            quelle = inspect.getsource(methode)
            ansage = quelle.index(f'_nachfolger_ansagen(')
            self.assertIn(f'"{name}"', quelle[ansage:ansage + 120], methode.__name__)
            entfernen = quelle.index("remove_output(univ", ansage)
            self.assertLess(ansage, entfernen, methode.__name__)

    def test_helfer_ruft_die_methode_und_ueberlebt_attrappen(self):
        from src.ui.widgets import output_config as oc
        rufe = []
        om = types.SimpleNamespace(nachfolger_ansagen=lambda *a: rufe.append(a))
        oc._nachfolger_ansagen(om, 3, "artnet", "2.0.0.1", 5)
        self.assertEqual(rufe, [(3, "artnet", "2.0.0.1", 5)])
        oc._nachfolger_ansagen(types.SimpleNamespace(), 3, "artnet")    # wirft nicht


# ══════════════════════════════════════════════════════════════════════════════
# B) Frei gewordene Laser-Adressen behalten ihren Aus-Wert
# ══════════════════════════════════════════════════════════════════════════════

class VerwaisteAusWerteImSendePfadTest(unittest.TestCase):

    def _bild(self, om, **kw):
        bilder: dict = {}
        om._send_all(_nur_rechnen=bilder, **kw)
        return bilder[1]

    def test_der_wert_steht_bei_jedem_frame(self):
        om = _manager({1: 200})
        om.set_laser_aus_verwaist({1: {10: 50}})
        bild = self._bild(om)
        self.assertEqual(bild[9], 50)
        self.assertEqual(bild[0], 200, "andere Adressen bleiben unberuehrt")

    def test_auch_im_blackout_und_bei_grand_master_null(self):
        om = _manager()
        om.set_laser_aus_verwaist({1: {10: 50}})
        om.set_blackout(True)
        self.assertEqual(self._bild(om)[9], 50, "der Blackout nullt sonst auf „Auto run“")
        om.set_blackout(False)
        om.grand_master = 0.0
        self.assertEqual(self._bild(om)[9], 50)

    def test_auch_im_schlussbild(self):
        om = _manager()
        om.set_laser_aus_verwaist({1: {10: 50}})
        dev = _Enttec("COM3")
        om._enttec_outputs[1] = dev
        om.stop(schlussbild=True)
        self.assertEqual(dev.bilder[-1][9], 50)
        self.assertEqual(dev.bilder[-1][0], 0)

    def test_ein_wert_auf_der_adresse_kommt_nicht_durch(self):
        """Die Adresse gehoert keinem Geraet — was dort im Universum steht
        (Rest, Roh-Wert), darf den Laser nicht oeffnen."""
        om = _manager({10: 0})
        om.set_laser_aus_verwaist({1: {10: 50}})
        om.universes[1].set_channel(10, 180)
        self.assertEqual(self._bild(om)[9], 50)

    def test_im_lade_fenster_steht_das_eingefrorene_bild(self):
        """Beim Show-Laden ist der Plan kurz leer — alle Laser der alten Show
        waeren „verwaist“ und gingen fuer die Dauer des Ladens aus (OUT-60)."""
        om = _manager({10: 120})
        with om.lade_sperre():
            om.set_laser_aus_verwaist({1: {10: 50}})
            self.assertEqual(self._bild(om)[9], 120)
            self.assertEqual(self._bild(om, schlussbild=True)[9], 50,
                             "das Schlussbild traegt die Werte immer")
        self.assertEqual(self._bild(om)[9], 50)

    def test_leeren_gibt_die_adresse_frei(self):
        om = _manager({10: 120})
        om.set_laser_aus_verwaist({1: {10: 50}})
        om.set_laser_aus_verwaist({})
        self.assertEqual(self._bild(om)[9], 120)
        self.assertEqual(om.laser_aus_verwaist(), {})

    def test_notaus_liegt_weiter_obenauf(self):
        om = _manager({10: 120, 11: 90})
        om.set_laser_aus_verwaist({1: {10: 50}})
        om.set_laser_estop_mask({1: frozenset({11})})
        bild = self._bild(om)
        self.assertEqual((bild[9], bild[10]), (50, 0))

    def test_manager_ohne_init_ueberlebt(self):
        om = OutputManager.__new__(OutputManager)
        self.assertEqual(om.laser_aus_verwaist(), {})


# ── Geraete fuer den Plan ───────────────────────────────────────────────────

class _Rg:
    def __init__(self, von, bis, name, kind=""):
        self.range_from, self.range_to, self.name, self.kind = von, bis, name, kind


class _Ch:
    def __init__(self, attr, num, ranges=(), default=0):
        self.attribute = attr
        self.channel_number = num
        self.default_value = default
        self.ranges = list(ranges)
        self.name = attr


class _Fx:
    fixture_profile_id = 1
    mode_name = "m"
    protocol = ""
    dimmer_curve = "linear"

    def __init__(self, fid, universe, address, ftype, kanaele):
        self.fid, self.universe, self.address = fid, universe, address
        self.fixture_type = ftype
        self.fixture_name = f"fx{fid}"
        self.manufacturer_name = ""
        self.label = f"Geraet {fid}"
        self.kanaele = kanaele
        self.channel_count = len(kanaele)


class _FM:
    def tick(self, universes, patch_cache, dt):
        pass


AUS = 50


def _laser(fid=7, universe=1, adresse=10):
    """Betriebsart 0–49 „Auto run“ (DMX 0 = AN!), 50–99 „Laser off“."""
    return _Fx(fid, universe, adresse, "laser", [
        _Ch("shutter", 1, [_Rg(0, 49, "Auto run", "open"),
                           _Rg(50, 99, "Laser off", "closed"),
                           _Rg(100, 255, "Manual", "open")]),
        _Ch("laser_bank", 2), _Ch("laser_x", 3)])


def _laser_aus_null(fid=8, universe=1, adresse=40):
    """Ein Laser, dessen „aus“ 0 ist."""
    return _Fx(fid, universe, adresse, "laser", [
        _Ch("shutter", 1, [_Rg(0, 9, "Laser off", "closed"),
                           _Rg(10, 255, "Manual", "open")]),
        _Ch("laser_x", 2)])


def _par(fid=20, universe=1, adresse=10):
    return _Fx(fid, universe, adresse, "par", [
        _Ch("intensity", 1), _Ch("color_r", 2), _Ch("color_g", 3), _Ch("color_b", 4)])


class _MitZustand(unittest.TestCase):

    def setUp(self):
        orig = A.get_channels_for_patched
        A.get_channels_for_patched = lambda fx: fx.kanaele

        def zurueck():
            A.get_channels_for_patched = orig
        self.addCleanup(zurueck)
        self.om = OutputManager()
        self.om.add_universe(1)
        self.om.add_universe(2)
        self.om.grand_master = 1.0
        self.addCleanup(self.om.stop)
        st = AppState.__new__(AppState)
        st.universes = self.om.universes
        st.programmer = {}
        st.playback_engine = None
        st.function_manager = _FM()
        st._patch_cache = []
        st._prog_lock = threading.RLock()
        st.output_manager = self.om
        st.laser_estop_active = False
        st._laser_estop_addrs = {}
        st._laser_fids = frozenset()
        st.base_levels = {}
        st._engine_extra_prev = {}
        st._suppress_emits = True
        st._emit = lambda *a, **k: None
        self.st = st

    def _patch(self, *geraete, programmer=None):
        self.st._patch_cache = list(geraete)
        self.st.programmer = dict(programmer or {})
        self.st._rebuild_render_plan()

    def _gesendet(self, universum=1, **kw):
        self.st._render_frame(0.025)
        bilder: dict = {}
        self.om._send_all(_nur_rechnen=bilder, **kw)
        return bilder[universum]


class LaserEntpatchtTest(_MitZustand):

    def test_der_fall_aus_dem_befund(self):
        """Laser laeuft auf „Manual“ (120), wird aus dem Patch genommen: die
        Adresse darf nicht auf 0 („Auto run“) fallen."""
        self._patch(_laser(), programmer={7: {"shutter": 120}})
        self.assertEqual(self._gesendet()[9], 120)
        self._patch()
        self.assertEqual(self._gesendet()[9], AUS)
        self.assertEqual(self.st._laser_aus_verwaist, {1: {10: AUS}})

    def test_er_bleibt_ueber_weitere_plan_aufbauten_stehen(self):
        self._patch(_laser())
        self._patch()
        self._patch()
        self._patch(_par(adresse=100))
        self.assertEqual(self._gesendet()[9], AUS)

    def test_neu_gepatchte_adresse_gehoert_dem_neuen_geraet(self):
        self._patch(_laser())
        self._patch()
        self._patch(_par(adresse=10), programmer={20: {"intensity": 77}})
        self.assertEqual(self._gesendet()[9], 77)
        self.assertEqual(self.st._laser_aus_verwaist, {})
        self.assertEqual(self.om.laser_aus_verwaist(), {})

    def test_danach_wieder_frei_faellt_sie_auf_null(self):
        """Das neue Geraet hat die Adresse uebernommen; geht auch es, gilt fuer
        die Adresse wieder die gewoehnliche Regel."""
        self._patch(_laser())
        self._patch(_par(adresse=10))
        self._patch()
        self.assertEqual(self._gesendet()[9], 0)

    def test_umadressiert_die_alte_adresse_behaelt_den_aus_wert(self):
        self._patch(_laser(adresse=10), programmer={7: {"shutter": 120}})
        self._patch(_laser(adresse=101), programmer={7: {"shutter": 120}})
        bild = self._gesendet()
        self.assertEqual(bild[9], AUS, "das Geraet hoert noch auf seine alte Adresse")
        self.assertEqual(bild[100], 120, "an der neuen Adresse laeuft es normal")
        self.assertEqual(self.st._laser_aus_verwaist, {1: {10: AUS}})

    def test_um_einen_kanal_verschoben_nichts_bleibt_haengen(self):
        """Alte und neue Lage ueberlappen: jede Adresse, die das Geraet weiter
        belegt, gehoert ihm."""
        self._patch(_laser(adresse=10))
        self._patch(_laser(adresse=11), programmer={7: {"shutter": 120}})
        bild = self._gesendet()
        self.assertEqual(bild[10], 120)
        self.assertEqual(bild[9], AUS)

    def test_show_wechsel_ohne_dieses_geraet(self):
        self._patch(_laser(), _par(adresse=200))
        self._patch(_par(fid=31, adresse=300), _par(fid=32, adresse=310))
        self.assertEqual(self._gesendet()[9], AUS)

    def test_show_wechsel_mit_anderem_geraet_auf_der_adresse(self):
        self._patch(_laser())
        self._patch(_par(fid=31, adresse=8))            # belegt 8..11
        self.assertEqual(self._gesendet()[9], 0)
        self.assertEqual(self.st._laser_aus_verwaist, {})

    def test_aus_wert_null_wird_nicht_gemerkt(self):
        self._patch(_laser_aus_null())
        self._patch()
        self.assertEqual(self.st._laser_aus_verwaist, {})

    def test_blackout_nach_dem_entpatchen(self):
        self._patch(_laser())
        self._patch()
        self.om.set_blackout(True)
        self.assertEqual(self._gesendet()[9], AUS)

    def test_schlussbild_nach_dem_entpatchen(self):
        self._patch(_laser())
        self._patch()
        dev = _Enttec("COM3")
        self.om._enttec_outputs[1] = dev
        self.om.stop(schlussbild=True)
        self.assertEqual(dev.bilder[-1][9], AUS)

    def test_zwei_universen_getrennt(self):
        self._patch(_laser(fid=7, universe=1), _laser(fid=9, universe=2, adresse=30))
        self._patch(_laser(fid=7, universe=1))
        self.assertEqual(self.st._laser_aus_verwaist, {2: {30: AUS}})
        self.assertEqual(self._gesendet(2)[29], AUS)

    def test_gepatchter_laser_ist_nie_verwaist(self):
        self._patch(_laser())
        self._patch(_laser())
        self.assertEqual(self.st._laser_aus_verwaist, {})

    def test_gescheiterte_maske_verliert_die_bekannten_werte_nicht(self):
        self._patch(_laser())
        echt = self.st._build_gm_laser_aus_mask

        def kaputt(_fix_index):
            raise RuntimeError("Maske nicht baubar")

        self.st._build_gm_laser_aus_mask = kaputt
        try:
            self._patch()
        finally:
            self.st._build_gm_laser_aus_mask = echt
        self.assertEqual(self.st._laser_aus_verwaist, {1: {10: AUS}})

    def test_zustand_ohne_ausgabe_manager_ueberlebt(self):
        self._patch(_laser())
        self.st.output_manager = types.SimpleNamespace(
            set_gm_address_mask=lambda m: None)
        self._patch()
        self.assertEqual(self.st._laser_aus_verwaist, {1: {10: AUS}})


if __name__ == "__main__":
    unittest.main()
