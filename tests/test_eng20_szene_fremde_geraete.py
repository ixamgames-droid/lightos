"""ENG-20: eine alte Szene schreibt nicht mehr in fremde Geraete.

**Der Befund, selbst nachgemessen** (das Item trug ausdruecklich „NOCH NICHT
GEGENGEPRUEFT — vor dem Fix selbst nachmessen", und A's Lagebild vom 06.09.
zeigte, dass genau unter dieser Markierung die Fehltreffer sassen).

``Scene.write`` rechnet ``fixture.address + sv.channel - 1`` und prueft davon
NUR, ob das Ergebnis zwischen 1 und 512 liegt. Die Kanalnummer kommt aber aus
der GESPEICHERTEN Szene und beschreibt einen Zustand, den es womoeglich nicht
mehr gibt.

★ **Genau das unterscheidet diese Stelle von allen anderen**, die dieselbe
Rechnung anstellen (``app_state`` an sieben Stellen): dort stammt die Nummer aus
der LEBENDEN Kanalliste des Geraets und kann per Konstruktion nicht ueberlaufen.

**Zwei Wege in ein fremdes Geraet, beide gemessen:**

1. *Kanalzahl* — Hydra auf Adresse 7, nach einem Modus-Wechsel nur noch 6
   Kanaele; die alte Szene kennt Kanal 10. ``7 + 10 - 1 = 16`` — und 16 gehoert
   dem PAR nebenan. Gemessen landete dort eine 200.
2. *Netzwerk-Laser* — deren ``address`` ist ein bedeutungsloser Platzhalter.
   ``app_state.fixture_uses_dmx`` sagt das seit LAS-04, und sein Kommentar
   verlangt ausdruecklich, dass **jede** Stelle mit dieser Rechnung vorher
   fragt. ``scene.py`` fragte nicht. Gemessen schrieb ein Laser auf Adresse 1
   seinen „Kanal 3" auf Adresse 3, also in einen echten PAR.

⚠️ **Die sichere Richtung ist hier NICHT „im Zweifel verwerfen".** Fehlt die
Kanalzahl (Alt-Objekte, Mocks), wird geschrieben wie bisher. Eine Szene, die
stumm nichts mehr tut, ist auf der Buehne schlimmer als eine, die zu viel tut —
dieselbe Abwaegung, die Robin am 06.09. bei FM-45/2 getroffen hat: ein Geraet,
das schweigt, sieht aus wie ein Defekt.
"""
from __future__ import annotations

import io
import os
import unittest
from contextlib import redirect_stdout

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from src.core.dmx.universe import Universe
from src.core.engine.scene import Scene


class _Fx:
    """Gepatchtes Geraet — gelesen werden fid/universe/address/channel_count."""

    def __init__(self, fid, address, channel_count, protocol="dmx"):
        self.fid = fid
        self.universe = 1
        self.address = address
        self.channel_count = channel_count
        self.protocol = protocol


class _AltesFx:
    """Alt-Objekt ohne ``channel_count`` — Mocks und alte Shows sehen so aus."""

    def __init__(self, fid=1, address=7):
        self.fid = fid
        self.universe = 1
        self.address = address


def _fahre(fixtures, werte, frames=1):
    """Szene mit ``werte`` = [(fid, kanal, wert)] fahren; liefert (Universe, Ausgabe)."""
    uni = Universe(1)
    sz = Scene(name="Testszene")
    sz.fade_in = 0.0
    for fid, kanal, wert in werte:
        sz.set_value(fid, kanal, wert)
    sz.start()
    puffer = io.StringIO()
    with redirect_stdout(puffer):
        for _ in range(frames):
            sz.write({1: uni}, fixtures, 0.05)
    return uni, puffer.getvalue()


#: Hydra auf 7 mit heute 6 Kanaelen (belegt 7..12), PAR auf 13 (belegt 13..16).
def _rig():
    return [_Fx(1, 7, 6), _Fx(2, 13, 4)]


class KanalzahlTest(unittest.TestCase):
    """★★ Der Kern: ein Kanal, den es nicht mehr gibt, trifft den Nachbarn."""

    def test_der_nachbar_bleibt_unberuehrt(self):
        uni, _ = _fahre(_rig(), [(1, 10, 200)])
        self.assertEqual(0, uni.get_channel(16),
                         "Kanal 10 der 6-Kanal-Hydra landet auf Adresse 16 — "
                         "die gehoert dem PAR")

    def test_der_verworfene_wert_wird_GEMELDET(self):
        """Verwerfen ohne Meldung waere die naechste stille Klasse.

        Der Nutzer sieht sonst nur, dass ein Teil der Szene fehlt, und hat
        keinen Anhaltspunkt, warum.
        """
        _, ausgabe = _fahre(_rig(), [(1, 10, 200)])
        self.assertIn("ENG-20", ausgabe, "die Meldung nennt ihr Item nicht")
        self.assertIn("Kanal 10", ausgabe, "die Meldung nennt den Kanal nicht")
        self.assertIn("6", ausgabe, "die Meldung nennt die heutige Kanalzahl nicht")

    def test_die_grenze_liegt_auf_der_kanalzahl(self):
        """★ Kanal 6 ist der letzte gueltige, Kanal 7 der erste ungueltige.

        Ein Off-by-one waere hier nicht auffaellig: beide Faelle schreiben in
        gueltige Adressen, nur einer davon in ein fremdes Geraet.
        """
        uni, _ = _fahre(_rig(), [(1, 6, 111)])
        self.assertEqual(111, uni.get_channel(12), "Kanal 6 ist gueltig")
        uni, _ = _fahre(_rig(), [(1, 7, 111)])
        self.assertEqual(0, uni.get_channel(13),
                         "Kanal 7 gibt es nicht mehr und Adresse 13 ist der PAR")

    def test_kanal_null_oder_negativ_faellt_ebenfalls_weg(self):
        for kanal in (0, -3):
            with self.subTest(kanal=kanal):
                uni, _ = _fahre(_rig(), [(1, kanal, 200)])
                self.assertEqual([0] * 16, [uni.get_channel(a) for a in range(1, 17)])


class NetzwerkLaserTest(unittest.TestCase):
    """★★ Die zweite Haelfte: der Platzhalter-Adressraum.

    ``fixture_uses_dmx`` gibt es seit LAS-04, und sein Kommentar verlangt, dass
    jede Stelle mit ``address + channel`` vorher fragt. ``scene.py`` war die
    Stelle, die es nicht tat — Review-Checkliste 17.
    """

    def test_ein_laser_platzhalter_schreibt_nicht_in_echte_geraete(self):
        rig = [_Fx(1, 1, 34, protocol="etherdream"), _Fx(2, 3, 4)]
        uni, ausgabe = _fahre(rig, [(1, 3, 222)])
        self.assertEqual(0, uni.get_channel(3),
                         "der Platzhalter des Netzwerk-Lasers schreibt in den "
                         "PAR auf Adresse 3")
        self.assertIn("Platzhalter", ausgabe)

    def test_ein_DMX_laser_faehrt_weiterhin(self):
        """★ Die Gegenprobe: nur NETZWERK-Laser haben Platzhalter-Adressen."""
        uni, _ = _fahre([_Fx(1, 3, 8, protocol="dmx")], [(1, 3, 222)])
        self.assertEqual(222, uni.get_channel(5))


class BestandTest(unittest.TestCase):
    """Ohne diese Arme koennte die Wache alles verwerfen und waere gruen."""

    def test_gueltige_werte_fahren_unveraendert(self):
        uni, ausgabe = _fahre(_rig(), [(1, 1, 100), (1, 6, 150), (2, 4, 90)])
        self.assertEqual(100, uni.get_channel(7))
        self.assertEqual(150, uni.get_channel(12))
        self.assertEqual(90, uni.get_channel(16))
        self.assertEqual("", ausgabe, "ein sauberer Lauf meldet nichts")

    def test_ohne_kanalzahl_wird_NICHT_verworfen(self):
        """⚠️ Die sichere Richtung ist hier „schreiben", nicht „verwerfen".

        Alt-Objekte und Mocks tragen kein ``channel_count``. Wuerde die Wache
        sie verwerfen, faellt eine Szene stumm aus — und ein Geraet, das
        schweigt, sieht am Rig aus wie ein Defekt (Robins Begruendung zu
        FM-45/2, 2026-09-06).
        """
        uni, ausgabe = _fahre([_AltesFx()], [(1, 3, 77)])
        self.assertEqual(77, uni.get_channel(9))
        self.assertEqual("", ausgabe)


class MeldungEinmalTest(unittest.TestCase):
    """★★ ``write`` laeuft mit der Bildrate — eine Meldung je Frame waere Rauschen.

    Und Rauschen ist hier nicht bloss haesslich: die eine Zeile, die den Nutzer
    auf die veraltete Szene hinweist, ginge darin unter. Der Hinweis selbst
    waere dann wirkungslos.
    """

    def test_dreissig_frames_melden_einmal(self):
        _, ausgabe = _fahre(_rig(), [(1, 10, 200)], frames=30)
        self.assertEqual(1, ausgabe.count("ENG-20"),
                         f"erwartet EINE Meldung, bekommen:\n{ausgabe[:600]}")

    def test_zwei_verschiedene_werte_melden_zweimal(self):
        """★ Die Gegenprobe: sonst schluckte das Gedaechtnis den zweiten Fund."""
        _, ausgabe = _fahre(_rig(), [(1, 10, 200), (1, 11, 200)], frames=5)
        self.assertEqual(2, ausgabe.count("ENG-20"),
                         "zwei verschiedene Kanaele muessen beide gemeldet werden")

    def test_ein_neuer_lauf_meldet_wieder(self):
        """Nach Stop und Start ist es ein neuer Lauf — der Nutzer soll den
        Hinweis auch dann sehen, wenn er die Szene erneut startet."""
        uni = Universe(1)
        sz = Scene(name="Testszene")
        sz.fade_in = 0.0
        sz.set_value(1, 10, 200)
        gesamt = ""
        for _ in range(2):
            sz.start()
            puffer = io.StringIO()
            with redirect_stdout(puffer):
                sz.write({1: uni}, _rig(), 0.05)
            gesamt += puffer.getvalue()
            sz.stop()
        self.assertEqual(2, gesamt.count("ENG-20"))


if __name__ == "__main__":
    unittest.main()
