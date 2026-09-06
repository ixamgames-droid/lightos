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


class NetzwerkLaserSchreibtNichtInsDmxTest(unittest.TestCase):
    """★★★ ENG-20b — die ZWEITE Art, wie eine gespeicherte Zahl veraltet.

    **Gefunden von der zweiten Sitzung (B, PR #744), von mir unabhaengig
    nachgemessen und hier uebernommen.** Ich hatte ENG-20 ohne Claim bearbeitet;
    wir haben es doppelt gemacht, und Bs Fassung deckte diesen Fall ab, meine
    nicht. Die Uebernahme geschieht auf Robins Anweisung.

    Netzwerk-Laser haben ``universe``/``address`` nur als **bedeutungslose
    Platzhalter**. ``app_state.fixture_uses_dmx`` sagt das seit LAS-04, und sein
    Kommentar verlangt woertlich: „JEDE Stelle, die
    ``fx.address + ch.channel_number`` rechnet, MUSS vorher hier fragen, sonst
    schreibt der Platzhalter in die Spans echter Geraete." ``scene.py`` fragte
    nicht.

    **Gemessen:** Laser mit ``protocol='etherdream'`` auf Platzhalter-Adresse 1,
    PAR auf Adresse 3. Eine Szene mit „Kanal 3" des Lasers schrieb ``{3: 200}``
    — und 3 gehoert dem PAR.

    ⚠️ **Die Kanalzahl-Pruefung faengt das NICHT:** Kanal 3 ist bei 32 Kanaelen
    voellig gueltig. Zwei verschiedene Arten des Veraltens, beide enden im
    Nachbargeraet — deshalb EINE gemeinsame Stelle fuer beide.

    ★ Und die allgemeine Lehre: **eine Regel, die nur im Docstring einer
    Funktion steht, ist nicht durchgesetzt, sondern eine Bitte.** Diese hier
    stand seit LAS-04 da und wurde an genau dieser Stelle uebersehen.
    """

    def _laser_und_par(self):
        from src.core.app_state import LASER_NETWORK_PROTOCOLS
        proto = sorted(LASER_NETWORK_PROTOCOLS)[0]
        laser = SimpleNamespace(fid=1, universe=1, address=1, channel_count=32,
                                label="Laser", protocol=proto)
        par = SimpleNamespace(fid=2, universe=1, address=3, channel_count=4,
                              label="PAR", protocol="dmx")
        return laser, par

    def _lauf(self, fixture_id, kanal, frames=1):
        laser, par = self._laser_und_par()
        sc = Scene(name="Alt")
        sc._values = [SceneValue(fixture_id=fixture_id, channel=kanal, value=200)]
        sc.fade_in = sc.fade_out = 0.0
        sc._running = True
        u = _Universe()
        puffer = io.StringIO()
        with redirect_stdout(puffer):
            for _ in range(frames):
                sc.write({1: u}, [laser, par], 0.05)
        return sc, u, puffer.getvalue()

    def test_ein_netzwerk_laser_schreibt_KEIN_dmx(self):
        """★★ Der Kern: die Platzhalter-Adresse 1 plus Kanal 3 ergaebe Adresse
        3 — und die gehoert einem echten PAR."""
        _sc, u, _ = self._lauf(fixture_id=1, kanal=3)
        self.assertEqual(u.ch, {}, "der Laser hat ins DMX geschrieben")

    def test_ein_echtes_dmx_geraet_ist_unberuehrt(self):
        """Die Gegenprobe — der Riegel darf nicht alles verwerfen."""
        _sc, u, _ = self._lauf(fixture_id=2, kanal=1)
        self.assertEqual(u.ch, {3: 200})

    def test_die_kanalzahl_pruefung_haette_das_NICHT_gefangen(self):
        """★ Der Beleg, dass es wirklich zwei verschiedene Faelle sind: Kanal 3
        liegt bei 32 Kanaelen weit innerhalb — die erste Haelfte des Fixes
        haette hier nichts gemeldet."""
        laser, _par = self._laser_und_par()
        self.assertLessEqual(3, laser.channel_count,
                             "Vorbedingung: der Kanal ist per Kanalzahl gueltig")

    def test_gemeldet_wird_einmal_und_nennt_den_grund(self):
        sc, _u, ausgabe = self._lauf(fixture_id=1, kanal=3, frames=5)
        self.assertEqual(ausgabe.count("[scene] WARN"), 1, "fuenf Frames, eine Meldung")
        for teil in ("Laser", "Platzhalter", "Adresse 3", "ENG-20"):
            with self.subTest(teil=teil):
                self.assertIn(teil, ausgabe)

    def test_ein_geraet_ohne_protocol_gilt_als_dmx(self):
        """★ Die bewusste Fehlrichtung, wie bei der Kanalzahl: ein Alt-Objekt
        oder eine Attrappe ohne ``protocol`` wird geschrieben wie bisher. Eine
        Szene, die stumm nichts mehr tut, ist auf der Buehne schlimmer als eine,
        die zu viel tut."""
        alt = SimpleNamespace(fid=9, universe=1, address=5, channel_count=4,
                              label="Alt")
        sc = Scene(name="Alt")
        sc._values = [SceneValue(fixture_id=9, channel=1, value=200)]
        sc.fade_in = sc.fade_out = 0.0
        sc._running = True
        u = _Universe()
        with redirect_stdout(io.StringIO()):
            sc.write({1: u}, [alt], 0.05)
        self.assertEqual(u.ch, {5: 200})

    def test_wirft_die_pruefung_selbst_wird_GESCHRIEBEN(self):
        """★★ Der Ausnahme-Zweig, und er hat eine RICHTUNG. Kann die Pruefung
        nicht beantwortet werden (Import kaputt, Attrappe, Alt-Objekt), wird
        geschrieben — nicht verworfen.

        Begruendung dieselbe wie bei der unbekannten Kanalzahl und wie in
        Robins FM-45/2-Entscheidung: eine Szene, die stumm NICHTS mehr tut, ist
        auf der Buehne schlimmer als eine, die zu viel tut. Ein dunkles Rig ohne
        Erklaerung sucht man im Dunkeln.

        (Dieser Test entstand, weil die Mutationsprobe den Zweig UEBERLEBT hat —
        er war von keinem Test abgedeckt.)
        """
        from unittest import mock
        import src.core.engine.scene as S

        def kaputt(*_a, **_k):
            raise RuntimeError("Pruefung nicht beantwortbar")

        par = SimpleNamespace(fid=2, universe=1, address=3, channel_count=4,
                              label="PAR", protocol="dmx")
        sc = Scene(name="Alt")
        sc._values = [SceneValue(fixture_id=2, channel=1, value=200)]
        sc.fade_in = sc.fade_out = 0.0
        sc._running = True
        u = _Universe()
        with mock.patch.object(S, "_fixture_uses_dmx", lambda: kaputt):
            with redirect_stdout(io.StringIO()):
                sc.write({1: u}, [par], 0.05)
        self.assertEqual(u.ch, {3: 200},
                         "im Zweifel schreiben — nicht stumm verstummen")

    def test_beide_haelften_sitzen_in_DERSELBEN_stelle(self):
        """★★ Zwei Arten des Veraltens, eine Pruefstelle. Getrennt waeren es
        zwei Orte, an denen dieselbe Frage („darf dieser gespeicherte Wert
        ueberhaupt auf den Draht?") beantwortet wird — Checkliste 17."""
        import inspect
        quelle = inspect.getsource(Scene._adresse_fuer)
        self.assertIn("_fixture_uses_dmx", quelle)
        self.assertIn("channel_count", quelle)


class _Nichts:
    def __enter__(self):
        return None

    def __exit__(self, *_a):
        return False


if __name__ == "__main__":
    unittest.main()
