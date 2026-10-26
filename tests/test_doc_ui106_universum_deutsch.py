"""UI-106: die deutschen Anleitungen sagen „Universum“, nicht „Universe“.

Das Changelog-Fragment verspricht „Universum“ auch im deutschen Fliesstext der
Anleitungen (Ausgabe einrichten, Zwei Universen, Enttec + Art-Net, Patch &
Gruppen, Erste Schritte, Externe Pulte) und in der Uebersicht
``docs/ANLEITUNGEN.md``. Die englischen Fassungen (``*.en.md``) bleiben bei
„universe“ und werden hier nicht geprueft.

Erlaubt bleibt nur der Spalten-Alias des Tabellen-Imports („Universe, Univ.“):
das ist ein Wert, den LightOS beim Einlesen als Spaltenkopf akzeptiert.
"""
from __future__ import annotations

import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]

VERBOTEN = re.compile(r"\bUniverse\b")

DEUTSCHE_ANLEITUNGEN = (
    "docs/ANLEITUNGEN.md",
    "docs/anleitung_ausgabe_einrichten/ANLEITUNG.md",
    "docs/anleitung_zwei_universen/ANLEITUNG.md",
    "docs/anleitung_enttec_artnet/ANLEITUNG_ENTTEC_ARTNET.md",
    "docs/anleitung_patch_gruppen/ANLEITUNG_PATCH_GRUPPEN.md",
    "docs/anleitung_erste_schritte/ANLEITUNG.md",
    "docs/anleitung_externe_pulte/ANLEITUNG_EXTERNE_PULTE.md",
)

#: Spalten-Alias im Tabellen-Import — eingelesener Wert, kein Fliesstext.
ALIAS = "Universe, Univ."


def funde(text: str) -> list[tuple[int, str]]:
    rest = []
    for nr, zeile in enumerate(text.splitlines(), 1):
        if VERBOTEN.search(zeile.replace(ALIAS, "")):
            rest.append((nr, zeile.strip()))
    return rest


class DeutscheAnleitungenTest(unittest.TestCase):

    def test_pruefer_gegenprobe(self):
        alt = ("Modus, Universe (`Univ.`) `1`, Adresse `1`\n"
               "| Universe 1 über ENTTEC USB Pro, Universe 2 über Art-Net |\n"
               "| **Universum** | nein | 1 bis 32 | Universe, Univ. |\n"
               "Zwei Universen, Universum 1, Art-Net-Universum 3\n")
        self.assertEqual([n for n, _ in funde(alt)], [1, 2])

    def test_kein_universe_im_deutschen_text(self):
        rest = []
        for rel in DEUTSCHE_ANLEITUNGEN:
            pfad = ROOT / rel
            self.assertTrue(pfad.is_file(), rel)
            for nr, zeile in funde(pfad.read_text(encoding="utf-8")):
                rest.append(f"{rel}:{nr}: {zeile}")
        self.assertEqual(rest, [])


if __name__ == "__main__":
    unittest.main()
