"""Der Schweif eines Lauflichts muss HINTER dem Läufer herziehen — auch rückwärts.

David 2026-08-01: „wenn ich im Live-Edit-Fenster in der VC die Richtung ändere,
dann stimmt der Schweif nicht, der ändert die Richtung nicht richtig mit."

Gemessen am Render (12×1, ein Läufer, 40 % Schweif):

    forward   Kopf 2 → 3 → 4   Schweif links   ✔ zieht nach
    reverse   Kopf 8 → 7 → 6   Schweif links   ✘ zieht VORAUS

Die Richtung wird durch Negieren der Phase umgesetzt — der Kopf läuft dann
rückwärts. Der Schweif-Abstand wurde aber weiter *vorwärts* gemessen
(``(head - pos) % length``), blieb also auf derselben Seite.

★ Warum das lange unbemerkt blieb: **jede Einzelaussage stimmte weiter.** Der
Läufer lief korrekt rückwärts, der Schweif war korrekt lang und korrekt
abgestuft. Falsch war nur ihr Verhältnis zueinander — und genau das prüft kein
Test, der Kopfposition und Schweiflänge getrennt betrachtet. Dieser hier misst
deshalb die RELATION: auf welcher Seite des Kopfes liegt der Schweif, und
stimmt diese Seite mit der Laufrichtung überein?
"""
from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from src.core.engine.rgb_matrix import RgbAlgorithm, RgbMatrixInstance  # noqa: E402

_COLS = 12


def _zeile(direction: str, phase: float, **params) -> list[float]:
    m = RgbMatrixInstance(cols=_COLS, rows=1, algorithm=RgbAlgorithm.CHASE,
                          direction=direction)
    m.params.update({"axis": "H", "movement": "normal", "runner_width": 1,
                     "runner_count": 1, "after_fade": 40.0})
    m.params.update(params)
    return [max(c) / 255.0 for c in m._render(phase)]


def _kopf(z: list[float]) -> int:
    return max(range(len(z)), key=lambda i: z[i])


def _schweif_seite(z: list[float], kopf: int) -> str:
    """„links"/„rechts" — auf welcher Seite des Kopfes liegt das Nachglühen?"""
    links = sum(z[(kopf - i) % len(z)] for i in range(1, 4))
    rechts = sum(z[(kopf + i) % len(z)] for i in range(1, 4))
    if abs(links - rechts) < 1e-6:
        return "—"
    return "links" if links > rechts else "rechts"


class SchweifRichtungTest(unittest.TestCase):

    def _laufrichtung(self, direction: str) -> str:
        """In welche Richtung wandert der Kopf über die Zeit?"""
        a, b = _kopf(_zeile(direction, 3.0)), _kopf(_zeile(direction, 4.0))
        # ohne Umlauf-Sprung messen (Phasen 3→4 liegen mittig)
        return "rechts" if b > a else "links"

    def test_vorwaerts_zieht_der_schweif_nach(self):
        z = _zeile("forward", 4.0)
        kopf = _kopf(z)
        self.assertEqual(self._laufrichtung("forward"), "rechts")
        self.assertEqual(_schweif_seite(z, kopf), "links",
                         f"Schweif muss hinter dem Laeufer liegen: {z}")

    def test_rueckwaerts_zieht_der_schweif_ebenfalls_nach(self):
        """★ Der gemeldete Fehler. Vor dem Fix lag der Schweif auch hier links
        — also VOR dem Laeufer."""
        z = _zeile("reverse", 4.0)
        kopf = _kopf(z)
        self.assertEqual(self._laufrichtung("reverse"), "links")
        self.assertEqual(_schweif_seite(z, kopf), "rechts",
                         f"Schweif zieht dem Laeufer voraus statt nach: {z}")

    def test_der_schweif_folgt_der_richtung_generisch(self):
        """Dieselbe Aussage ohne feste Seiten: der Schweif liegt IMMER auf der
        Seite, aus der der Laeufer kommt."""
        for d in ("forward", "reverse"):
            lauf = self._laufrichtung(d)
            z = _zeile(d, 4.0)
            erwartet = "links" if lauf == "rechts" else "rechts"
            self.assertEqual(_schweif_seite(z, _kopf(z)), erwartet,
                             f"{d}: Lauf nach {lauf}, Schweif muesste {erwartet} liegen")

    def test_ohne_schweif_bleibt_beides_gleich(self):
        """after_fade = 0 -> harte Kante. Beide Richtungen duerfen dann keinen
        Nachglüh-Unterschied zeigen (Gegenprobe, dass der Fix nur den Schweif
        betrifft und nicht den Laeufer verschiebt)."""
        for d in ("forward", "reverse"):
            z = _zeile(d, 4.0, after_fade=0.0)
            hell = [i for i, v in enumerate(z) if v > 0.01]
            self.assertLessEqual(len(hell), 2, f"{d}: kein Schweif erwartet: {z}")

    def test_mehrere_laeufer_behalten_die_richtung(self):
        for d in ("forward", "reverse"):
            lauf = self._laufrichtung(d)
            z = _zeile(d, 4.0, runner_count=2)
            kopf = _kopf(z)
            erwartet = "links" if lauf == "rechts" else "rechts"
            self.assertEqual(_schweif_seite(z, kopf), erwartet, f"{d}: {z}")

    def test_vertikale_achse_ebenso(self):
        """Die Achse darf nichts daran aendern — die Rechnung ist dieselbe."""
        m_vor = RgbMatrixInstance(cols=1, rows=_COLS, algorithm=RgbAlgorithm.CHASE,
                                  direction="forward")
        m_zur = RgbMatrixInstance(cols=1, rows=_COLS, algorithm=RgbAlgorithm.CHASE,
                                  direction="reverse")
        for m in (m_vor, m_zur):
            m.params.update({"axis": "V", "movement": "normal", "runner_width": 1,
                             "runner_count": 1, "after_fade": 40.0})
        zv = [max(c) / 255.0 for c in m_vor._render(4.0)]
        zr = [max(c) / 255.0 for c in m_zur._render(4.0)]
        self.assertNotEqual(_schweif_seite(zv, _kopf(zv)),
                            _schweif_seite(zr, _kopf(zr)),
                            "auch vertikal muss sich der Schweif mitdrehen")


if __name__ == "__main__":
    unittest.main()
