"""ENG-14: eine Sammlung, die sich selbst enthält, darf STOP ALL nicht lahmlegen.

Zwei Sammlungen, die einander enthalten (A→B→A) — oder eine, die sich selbst
enthält (A→A) — ließen ``write()`` und ``stop()`` endlos rekursieren.

Gemessen vor dem Fix:

* ``write``: ``RecursionError`` in **jedem Frame** (44-mal je Sekunde)
* ``stop``: ``RecursionError`` — **STOP ALL kam nicht durch**, Chaser und Cues
  liefen weiter

Der zweite Punkt ist der schwerere: STOP ALL ist eine Panik-Taste. Dass sie an
einer *Datenstruktur* scheitert, die der Nutzer versehentlich gebaut hat, ist
genau der Zustand, den man vor Publikum nicht gebrauchen kann.

★ Warum ``Function.stop()`` überhaupt rekursiert: es ist **nicht idempotent** —
es ruft ``_on_stop()`` auch dann, wenn längst gestoppt wurde. A stoppt B, B
stoppt A, A stoppt B … Die Sperre sitzt deshalb in ``Collection``, nicht in der
Basisklasse: ein ``stop()`` auf einer bereits gestoppten Funktion soll weiterhin
zum Zurücksetzen taugen.
"""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from src.core.engine.collection import Collection


def _zyklus_ab():
    """A → B → A."""
    a = Collection("A", fid=1)
    b = Collection("B", fid=2)
    a.function_ids = [2]
    b.function_ids = [1]
    return a, b, {1: a, 2: b}


class ZyklusLegtNichtsLahmTest(unittest.TestCase):

    def test_write_laeuft_durch(self):
        a, _b, reg = _zyklus_ab()
        a.start()
        a.write({}, [], 0.1, reg)          # vorher: RecursionError

    def test_stop_laeuft_durch_und_stoppt_die_kinder(self):
        """Der eigentliche Punkt: STOP ALL muss ankommen — und wirken.

        „Kein Absturz" allein genügt nicht: eine Sperre, die den Kreis abbricht
        BEVOR die Kinder gestoppt sind, wäre still genauso schlimm.
        """
        a, b, reg = _zyklus_ab()
        a.start()
        b.start()
        a.write({}, [], 0.1, reg)
        a.stop()                            # vorher: RecursionError

        self.assertFalse(a.is_running, "A läuft nach stop() weiter")
        self.assertFalse(b.is_running, "Das Kind wurde nicht gestoppt")

    def test_selbstbezug(self):
        """A → A, der kürzestmögliche Kreis."""
        c = Collection("C", fid=3)
        c.function_ids = [3]
        reg = {3: c}
        c.start()
        c.write({}, [], 0.1, reg)
        c.stop()
        self.assertFalse(c.is_running)

    def test_der_kreis_wird_genannt(self):
        """Ein stiller Abbruch wäre die halbe Lösung.

        Wer den Kreis versehentlich gebaut hat, merkt sonst nur, dass „irgendwas
        nicht läuft". Die Meldung nennt Name, ID und Mitglieder — und kommt
        genau EINMAL, nicht 44-mal je Sekunde.
        """
        import contextlib
        import io

        a, _b, reg = _zyklus_ab()
        a.start()
        puffer = io.StringIO()
        with contextlib.redirect_stdout(puffer):
            for _ in range(10):
                a.write({}, [], 0.1, reg)
        aus = puffer.getvalue()

        self.assertIn("enthaelt sich selbst", aus, "Der Kreis wird verschwiegen")
        self.assertIn("'A'", aus)
        self.assertEqual(aus.count("enthaelt sich selbst"), 1,
                         f"Die Meldung wiederholt sich je Frame:\n{aus}")

    def test_tiefer_kreis(self):
        """A → B → C → A: die Sperre darf nicht nur den direkten Fall fangen."""
        a = Collection("A", fid=1)
        b = Collection("B", fid=2)
        c = Collection("C", fid=3)
        a.function_ids, b.function_ids, c.function_ids = [2], [3], [1]
        reg = {1: a, 2: b, 3: c}
        a.start()
        a.write({}, [], 0.1, reg)
        a.stop()
        self.assertFalse(any(x.is_running for x in (a, b, c)))


class OhneZyklusUnveraendertTest(unittest.TestCase):
    """Positivkontrollen — die Sperre darf den Normalfall nicht antasten."""

    class _Kind(Collection):
        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            self.writes = 0

        def write(self, universes, patch_cache, dt, function_registry=None):
            self.writes += 1

    def test_kind_wird_jeden_frame_geschrieben(self):
        a = Collection("A", fid=1)
        kind = self._Kind("K", fid=2)
        a.function_ids = [2]
        reg = {1: a, 2: kind}
        a.start()
        for _ in range(5):
            a.write({}, [], 0.1, reg)
        self.assertEqual(kind.writes, 5,
                         "Die Sperre blockt den normalen Ablauf")

    def test_zwei_sammlungen_nebeneinander(self):
        """Verschachtelt, aber ohne Kreis: A → B → K. Muss durchlaufen."""
        a = Collection("A", fid=1)
        b = Collection("B", fid=2)
        kind = self._Kind("K", fid=3)
        a.function_ids, b.function_ids = [2], [3]
        reg = {1: a, 2: b, 3: kind}
        a.start()
        a.write({}, [], 0.1, reg)
        self.assertEqual(kind.writes, 1, "Verschachtelung ohne Kreis kommt nicht durch")

    def test_stop_stoppt_weiterhin_die_kinder(self):
        a = Collection("A", fid=1)
        b = Collection("B", fid=2)
        a.function_ids = [2]
        reg = {1: a, 2: b}
        a.start()
        b.start()
        a.write({}, [], 0.1, reg)
        a.stop()
        self.assertFalse(b.is_running, "Bestandsverhalten verloren: Kind läuft weiter")


if __name__ == "__main__":
    unittest.main()
