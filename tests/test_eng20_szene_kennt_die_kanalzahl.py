"""ENG-20: eine Szene schrieb nach einem Modus-Wechsel ins NACHBARGERAET.

Eine Szene speichert **Kanalnummern**, kein Wissen darueber, wie viele Kanaele
das Geraet hat. Wechselt es spaeter in einen kleineren Modus, zeigt eine
gespeicherte Nummer ueber sein Ende hinaus — und die einzige Pruefung war
``1 <= dmx_addr <= 512``.

**Gemessen vor dem Fix:** Geraet 1 auf Adresse 7 mit 6 Kanaelen (belegt 7..12),
Geraet 2 auf Adresse 13. Eine Szene mit den Kanaelen 1, 4 und 10 schrieb
``{7: 200, 10: 200, 16: 200}`` — und **16 gehoert Geraet 2**.

★ Der Backlog-Eintrag trug „⚠️ NOCH NICHT GEGENGEPRUEFT"; die Messung oben ist
die eigene Nachpruefung. Anders als bei ENG-15 am selben Tag stimmte hier der
beschriebene Mechanismus.
"""
from __future__ import annotations

import io
import os
import sys
import unittest
from contextlib import redirect_stdout
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.core.engine.scene import Scene, SceneValue  # noqa: E402


class _Universe:
    def __init__(self):
        self.ch: dict[int, int] = {}

    def set_channel(self, addr, val):
        self.ch[addr] = val

    def get_channel(self, addr):
        return self.ch.get(addr, 0)


def _geraet(fid, address, channel_count, label):
    return SimpleNamespace(fid=fid, universe=1, address=address,
                           channel_count=channel_count, label=label)


class SzeneSchreibtNichtInsNachbargeraetTest(unittest.TestCase):

    def _lauf(self, kanaele, frames=1, geraete=None, still=True):
        g1 = _geraet(1, 7, 6, "Hydra")
        g2 = _geraet(2, 13, 6, "PAR")
        patch = geraete if geraete is not None else [g1, g2]
        sc = Scene(name="Alt")
        sc._values = [SceneValue(fixture_id=1, channel=k, value=200)
                      for k in kanaele]
        sc.fade_in = sc.fade_out = 0.0
        sc._running = True
        u = _Universe()
        puffer = io.StringIO()
        with redirect_stdout(puffer) if still else _Nichts():
            for _ in range(frames):
                sc.write({1: u}, patch, 0.05)
        return sc, u, puffer.getvalue()

    def test_ein_kanal_jenseits_der_kanalzahl_landet_NICHT_im_nachbarn(self):
        """★★ Der Kern. Kanal 10 eines 6-Kanal-Geraets auf Adresse 7 laege auf
        Adresse 16 — und die gehoert dem Geraet daneben."""
        _sc, u, _ = self._lauf([1, 4, 10])
        self.assertEqual(sorted(u.ch), [7, 10],
                         "nur die eigenen Kanaele des Geraets")
        self.assertNotIn(16, u.ch, "16 gehoert dem Nachbargeraet")

    def test_die_gueltigen_werte_kommen_weiterhin_an(self):
        """Die Gegenprobe: der Fix darf nicht einfach alles verwerfen."""
        _sc, u, _ = self._lauf([1, 4])
        self.assertEqual(u.ch, {7: 200, 10: 200})

    def test_der_erste_und_der_letzte_kanal_gelten(self):
        """Randfaelle der Grenze — 1 und die Kanalzahl selbst sind gueltig."""
        _sc, u, _ = self._lauf([1, 6])
        self.assertEqual(sorted(u.ch), [7, 12])

    def test_kanal_null_und_negativ_werden_verworfen(self):
        _sc, u, _ = self._lauf([0, -3, 2])
        self.assertEqual(sorted(u.ch), [8], "nur Kanal 2 ist gueltig")

    def test_gemeldet_wird_EINMAL_und_nicht_je_frame(self):
        """★★ `write()` laeuft jeden Frame. Eine Meldung je Frame waere eine
        Flut — und damit dasselbe wie keine Meldung."""
        sc, _u, ausgabe = self._lauf([10], frames=5)
        self.assertEqual(len(sc._verworfen_gemeldet), 1)
        self.assertEqual(ausgabe.count("[scene] WARN"), 1,
                         "fuenf Frames, eine Meldung")

    def test_die_meldung_sagt_was_passiert_waere(self):
        """Eine Warnung, die nur „Wert verworfen" sagt, hilft nicht beim
        Beheben. Sie nennt Geraet, Kanalzahl und die Adresse, auf der der Wert
        sonst gelandet waere."""
        _sc, _u, ausgabe = self._lauf([10])
        for teil in ("Kanal 10", "Hydra", "6 Kanaele", "Adresse 16", "ENG-20"):
            with self.subTest(teil=teil):
                self.assertIn(teil, ausgabe)

    def test_zwei_verschiedene_kanaele_werden_BEIDE_genannt(self):
        """Der Merker haengt an (fid, kanal), nicht an einem Flag — sonst
        verschwiegen zwei Probleme sich gegenseitig."""
        _sc, _u, ausgabe = self._lauf([10, 11], frames=3)
        self.assertEqual(ausgabe.count("[scene] WARN"), 2)

    def test_ohne_bekannte_kanalzahl_bleibt_alles_wie_bisher(self):
        """★ Die bewusste Fehlrichtung: ist die Kanalzahl UNBEKANNT (0 oder
        fehlend), wird nichts verworfen. Lieber ein Wert zu viel auf dem
        eigenen Geraet als ein stiller Ausfall, weil eine Attrappe oder ein
        Altbestand das Feld nicht fuehrt."""
        ohne = SimpleNamespace(fid=1, universe=1, address=7, label="Alt")
        _sc, u, _ = self._lauf([1, 10], geraete=[ohne])
        self.assertEqual(sorted(u.ch), [7, 16],
                         "unveraendertes Altverhalten bei unbekannter Kanalzahl")

    def test_schnappschuss_und_schreiben_fragen_DIESELBE_stelle(self):
        """★★ Zwei Schleifen berechnen die Adresse — Schnappschuss und
        Schreiben. Liefe die Pruefung nur in einer, laese der Schnappschuss
        einen Startwert aus einem FREMDEN Geraet, den das Schreiben gar nicht
        mehr setzt. Deshalb eine gemeinsame Stelle."""
        import inspect
        quelle = inspect.getsource(Scene.write)
        self.assertEqual(quelle.count("_adresse_fuer"), 2,
                         "beide Schleifen muessen die gemeinsame Stelle fragen")
        self.assertNotIn("address + sv.channel", quelle,
                         "zweite, eigene Adressrechnung im write()")


class _Nichts:
    def __enter__(self):
        return None

    def __exit__(self, *_a):
        return False


if __name__ == "__main__":
    unittest.main()
