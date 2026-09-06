"""NET-12: „Uebernehmen" schickte eine Stream-Termination fuer ein LAUFENDES Universum.

``SACNSender.close`` sendet eine E1.31-Stream-Termination (Options-Bit ``0x40``),
damit Empfaenger die Quelle sofort verwerfen statt 2,5 s auf den
Network-Data-Loss-Timeout zu warten (OUT-06). Genau deswegen fragt sie vorher
``SacnSource.release`` — gibt es einen Nachfolger, wird NICHT terminiert.

**Der Fehler war, dass es diesen Nachfolger im entscheidenden Moment nie gab.**
Zwei Aussagen sahen gleich aus und waren es nicht:

* *„steht in der Output-Registry"* — das stellt ``_swap_device`` sicher, und sein
  Kommentar behauptete damit die Uebergabe.
* *„ist in der Quelle BESITZER"* — und das passierte erst in ``next_seq``, also
  beim **ersten gesendeten Frame** des Neuen.

Dazwischen liegt das Schliessen des Alten. Review-Checkliste 17, eine Ebene
tiefer als der Kommentar hinsah.

**Gemessen vor dem Fix:** 5 von 5 „Uebernehmen"-Klicks mit UNVERAENDERTER
Konfiguration schickten eine Termination — 15 von 20 Paketen trugen das Bit.
Empfaenger duerfen daraufhin auf ihren Fallback gehen, mitten in der Show.

★ Der Dialog verschaerfte es zusaetzlich: er rief ``remove_output(univ)`` (das
per ``pop`` entfernt) UND danach ``add_sacn``. Damit war der Alte schon aus der
Registry, bevor der Neue ueberhaupt existierte.
"""
from __future__ import annotations

import os
import sys
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.core.dmx import sacn as sacn_modul  # noqa: E402
from src.core.dmx.output_manager import OutputManager  # noqa: E402

#: E1.31-Framing-Layer, Options-Byte. Bit 6 = Stream_Terminated.
_OPTIONS_BYTE = 112
_BIT_TERMINATED = 0x40


def _ist_termination(paket: bytes) -> bool:
    return len(paket) > _OPTIONS_BYTE and bool(paket[_OPTIONS_BYTE] & _BIT_TERMINATED)


class _FakeSocket:
    def __init__(self, mitschrift):
        self._mit = mitschrift

    def sendto(self, paket, _ziel):
        self._mit.append(paket)

    def close(self):
        pass

    def setsockopt(self, *_a):
        pass

    def bind(self, *_a):
        pass


class UebernehmenTerminiertNichtTest(unittest.TestCase):

    def setUp(self):
        self.pakete: list[bytes] = []
        p = mock.patch.object(sacn_modul.socket, "socket",
                              lambda *_a, **_k: _FakeSocket(self.pakete))
        p.start()
        self.addCleanup(p.stop)
        self.om = OutputManager()

    def _terminationen(self):
        return [p for p in self.pakete if _ist_termination(p)]

    def _laufendes_universum(self, univ=1):
        """Ein sACN-Universum, das nachweislich SENDET.

        ★★ Die Vorbedingung wird zugesichert, nicht angenommen. Eine Probe, die
        den Sendepfad gar nicht erreicht, meldet „keine Termination" und sieht
        aus wie eine Entwarnung — die haeufigste Falle bei genau dieser Art
        Messung (Lehre der zweiten Sitzung, QA-78).
        """
        self.om.add_sacn(univ, None)
        self.om._sacn_outputs[univ].send_dmx(univ, bytes(512))
        self.assertTrue(self.pakete,
                        "Vorbedingung verletzt: die Probe sendet gar nicht, "
                        "jedes Ergebnis waere wertlos")
        self.pakete.clear()

    def _uebernehmen(self, univ=1, ziel_ip=None):
        """Was der Dialog beim Klick auf „Uebernehmen" tut."""
        self.om.remove_output(univ, ausser="sacn")
        self.om.add_sacn(univ, ziel_ip)
        self.om._sacn_outputs[univ].send_dmx(univ, bytes(512))

    # ── Der Kern ────────────────────────────────────────────────────────────
    def test_uebernehmen_ohne_aenderung_terminiert_nicht(self):
        """★★ Fuenf Klicks auf „Uebernehmen", nichts geaendert — kein einziges
        Abschiedspaket. Vorher waren es fuenf Terminationen."""
        self._laufendes_universum()
        for _ in range(5):
            self._uebernehmen()
        self.assertEqual(self._terminationen(), [],
                         "ein weiterlaufendes Universum wurde terminiert")

    def test_die_ausgabe_laeuft_danach_weiter(self):
        """Die Gegenprobe zum Kern: der Fix darf nicht dadurch „gelingen", dass
        gar nichts mehr gesendet wird."""
        self._laufendes_universum()
        self._uebernehmen()
        self.assertTrue(self.pakete, "nach dem Uebernehmen kommt nichts mehr")

    def test_auch_ein_zielwechsel_terminiert_nicht(self):
        """Unicast-Ziel geaendert: das Universum LAEUFT weiter, nur woanders
        hin. Auch das ist kein Abschied."""
        self._laufendes_universum()
        self._uebernehmen(ziel_ip="10.0.0.7")
        self.assertEqual(self._terminationen(), [])

    # ── Die Gegenrichtung: echtes Aufhoeren MUSS terminieren ────────────────
    def test_echtes_aufhoeren_terminiert_weiterhin(self):
        """★★★ Die wichtigere Haelfte. OUT-06 gibt es, damit ein Empfaenger die
        Quelle SOFORT verwirft statt 2,5 s auf den Timeout zu warten. Wer die
        Termination pauschal abschaltet, hat NET-12 „behoben" und OUT-06
        kaputtgemacht.

        E1.31 verlangt drei Pakete."""
        self._laufendes_universum()
        self.om.remove_output(1)
        self.assertEqual(len(self._terminationen()), 3,
                         "echtes Aufhoeren muss 3 Termination-Pakete schicken")

    def test_typwechsel_entfernt_die_fremden_adapter_weiterhin(self):
        """★ Der Grund, aus dem `remove_output` hier ueberhaupt steht (MU-01):
        bei einem Typ-Wechsel muessen die FREMDEN Adapter weg, sonst sendet das
        Universum ueber zwei Wege gleichzeitig. `ausser="sacn"` darf das nicht
        aufweichen."""
        self.om.add_artnet(1, "255.255.255.255")
        self.om.add_sacn(1, None)
        self.assertIn(1, self.om._artnet_outputs, "Vorbedingung")
        self.om.remove_output(1, ausser="sacn")
        self.assertNotIn(1, self.om._artnet_outputs,
                         "der fremde Art-Net-Adapter blieb stehen")
        self.assertIn(1, self.om._sacn_outputs,
                      "der eigene sACN-Adapter wurde faelschlich entfernt")

    def test_unbekannter_typ_wird_abgelehnt(self):
        """Ein Tippfehler in `ausser` darf nicht heissen „entferne alles"."""
        with self.assertRaises(ValueError):
            self.om.remove_output(1, ausser="sacnn")


class BesitzWechseltVorDemSchliessenTest(unittest.TestCase):
    """★★ Die Ursache eine Ebene tiefer, ohne Netzwerk.

    „Steht in der Registry" und „ist in der Quelle Besitzer" sind zwei
    verschiedene Aussagen. Der Kommentar an ``_swap_device`` behauptete die
    Uebergabe; stattgefunden hat sie nicht.
    """

    def test_besitz_wechselt_ohne_zu_senden(self):
        from src.core.dmx.sacn_source import SacnSource
        quelle = SacnSource(bytes(16))
        alt, neu = quelle.new_token(), quelle.new_token()
        quelle.next_seq(7, alt)                 # der Alte sendet -> Besitzer
        quelle.uebernehmen(7, neu)              # Uebergabe OHNE Frame
        self.assertIsNone(quelle.release(7, alt),
                          "der Alte darf nach der Uebergabe nicht terminieren")

    def test_ohne_uebergabe_terminiert_der_alte_weiterhin(self):
        """Die Gegenprobe: ohne Nachfolger bleibt der Abschied noetig."""
        from src.core.dmx.sacn_source import SacnSource
        quelle = SacnSource(bytes(16))
        alt = quelle.new_token()
        quelle.next_seq(7, alt)
        self.assertIsNotNone(quelle.release(7, alt))

    def test_der_echte_sender_kann_die_uebergabe(self):
        """★★ `add_sacn` ruft `uebernimm` OPTIONAL auf — Art-Net kennt keinen
        Besitz, und die Attrappen anderer Tests ersetzen beide Sender-Klassen
        durch dieselbe. Fehlt die Methode, faellt es still auf das alte
        Verhalten zurueck. Dieser Test sorgt dafuer, dass das keine Luecke wird:
        der ECHTE Sender muss sie haben."""
        from src.core.dmx.sacn import SACNSender
        self.assertTrue(callable(getattr(SACNSender, "uebernimm", None)),
                        "SACNSender hat die Uebergabe verloren — add_sacn faellt "
                        "dann still auf das Verhalten VOR NET-12 zurueck")

    def test_die_uebergabe_verbraucht_keine_sequenznummer(self):
        """★ Die Sequenznummer gehoert dem UNIVERSUM, nicht dem Sender — die CID
        ist prozessweit. Ein Vorruecken bei der Uebergabe waere eine Luecke im
        Zaehler, die ein Empfaenger als Sprung liest."""
        from src.core.dmx.sacn_source import SacnSource
        quelle = SacnSource(bytes(16))
        alt, neu = quelle.new_token(), quelle.new_token()
        vorher = quelle.next_seq(7, alt)
        quelle.uebernehmen(7, neu)
        nachher = quelle.next_seq(7, neu)
        self.assertEqual(nachher, (vorher + 1) & 0xFF,
                         "die Uebergabe hat den Zaehler verschoben")


if __name__ == "__main__":
    unittest.main()
