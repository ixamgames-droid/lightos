"""FIXTEST-FRESH — ein Profil-Test muss den QUELLTEXT prüfen, nicht die Datei.

Die Fixture-Profile stehen in `fixture_db.py` und werden **einmal** in eine
Datei geschrieben (``~/.local/share/LightOS/fixtures.db``). ``ensure_builtins()``
legt ein Builtin nur an, wenn sein ``short_name`` **fehlt** — steht es schon
drin, wird der Quelltext nie wieder angesehen. Ein Test, der die Datei liest,
prueft damit den Stand vom ersten Lauf.

**Gemessen am 2026-08-02** (globale Mutation: jeder Kanal bekommt das Attribut
``raw``): 18 von 19 Profil-Tests wurden rot, **einer blieb gruen** —
``test_claypaky_mythos_profile.py``. Die anderen hatten sich die Loesung jeweils
selbst hinkopiert: **17 Kopien derselben Funktion, schon in zwei Varianten
auseinandergelaufen.** Der Test, der sie NICHT kopiert hatte, war der blinde.

Daraus die zwei Regeln hier:

1. **Kein Test definiert die Konstruktion selbst.** Sie liegt in
   `tests/_fixture_quelle.py`. Siebzehn Kopien haben genau den Fall erzeugt, den
   sie verhindern sollten — und die achtzehnte fehlte einfach.
2. **Jeder Profil-Test benutzt sie.** Der Dateiname ist hier die verlaessliche
   Kennung: die Familie heisst durchgaengig ``test_<geraet>_profile.py`` bzw.
   ``..._profiles.py``.

Die zweite Regel greift beim NAECHSTEN Geraeteprofil — also genau dort, wo der
Fehler zweimal passiert ist (Mythos und, im ersten Wurf, MAC 700).
"""
from __future__ import annotations

import os
import re
import unittest

_TESTS = os.path.dirname(os.path.abspath(__file__))

# Dateien, die trotz Namensmuster keine Builtin-Definition pruefen. Leer — und
# das ist die Aussage: faellt hier je etwas hinein, gehoert eine Begruendung
# daneben, kein stilles Ueberspringen.
_AUSNAHMEN: dict[str, str] = {}


def _profil_tests():
    for name in sorted(os.listdir(_TESTS)):
        if re.fullmatch(r"test_.*_profiles?\.py", name):
            yield name


def _text(name: str) -> str:
    with open(os.path.join(_TESTS, name), encoding="utf-8") as fh:
        return fh.read()


class ProfilTestsLesenDieQuelleTest(unittest.TestCase):

    def test_die_familie_ist_nicht_leer(self):
        """Ohne diese Zusicherung waeren beide Regeln unten stumm gruen, sobald
        das Namensmuster nicht mehr passt."""
        familie = list(_profil_tests())
        self.assertGreater(len(familie), 10,
                           f"kaum Profil-Tests erkannt: {familie}")
        self.assertIn("test_claypaky_mythos_profile.py", familie)
        self.assertIn("test_martin_mac700_profile.py", familie)

    def test_niemand_baut_die_konstruktion_selbst_nach(self):
        """Siebzehn Kopien sind auseinandergelaufen; die achtzehnte fehlte."""
        # Der Suchbegriff steht zwangslaeufig in DIESER Datei — die eigene
        # Datei und der Helfer selbst sind deshalb ausgenommen. (Genau daran
        # schlug der erste Wurf an: ein Gate, das sich selbst meldet.)
        selbst = os.path.basename(__file__)
        muster = "def " + "_temp_seeded_engine"
        eigenbau = [n for n in os.listdir(_TESTS)
                    if n.endswith(".py") and n not in (selbst, "_fixture_quelle.py")
                    and muster in _text(n)]
        self.assertEqual(
            eigenbau, [],
            "diese Dateien bauen die frische Library selbst nach statt "
            f"`from _fixture_quelle import frische_library`: {eigenbau}")

    def test_jeder_profil_test_baut_aus_der_quelle(self):
        blind = []
        for name in _profil_tests():
            if name in _AUSNAHMEN:
                continue
            if "frische_library" not in _text(name):
                blind.append(name)
        self.assertEqual(
            blind, [],
            "diese Profil-Tests lesen die abgelegte fixtures.db und pruefen "
            "damit den Stand vom ersten Lauf, nicht den Quelltext: "
            f"{blind}. Loesung: `cls._eng = frische_library(cls)` in "
            "setUpClass, s. tests/_fixture_quelle.py")

    def test_der_helfer_raeumt_auf(self):
        """Die kopierte Fassung benutzte ``tempfile.mktemp()`` und loeschte
        nichts — gemessen 4 zurueckgelassene Datenbanken pro Lauf allein aus
        ``test_spider_profile.py``, an einem Tag 1935 Dateien / 218 MB.

        Geprueft wird die Wirkung, nicht die Formulierung: der Helfer legt an,
        raeumt weg, und danach ist nichts mehr da.
        """
        import _fixture_quelle
        from src.core.database import fixture_db as FDB

        gesehen = {}

        class _Fall:
            @staticmethod
            def addCleanup(fn):
                gesehen["aufraeumen"] = fn

        # Der Seed wird hier ABGESCHALTET: geprueft wird das Anlegen und
        # Wegraeumen des Verzeichnisses, nicht der Inhalt der Library. Ein
        # echter Seed kostet hier ~1,5 s CPU — und dieser Test laeuft in der
        # parallelen Spur neben den WebEngine-Segmenten, denen genau das den
        # GPU-Kontext wegnimmt (XPLAT-17, gemessen: mit Seed 3/3 rot, ohne
        # 558/558 gruen).
        echt = FDB._seed
        FDB._seed = lambda _s: None
        self.addCleanup(lambda: setattr(FDB, "_seed", echt))
        motor = _fixture_quelle.frische_library(_Fall())
        pfad = str(motor.url.database)
        self.assertTrue(os.path.exists(pfad), "Library wurde nicht angelegt")
        self.assertIn("aufraeumen", gesehen, "kein Aufraeumen registriert")
        gesehen["aufraeumen"]()
        self.assertFalse(os.path.exists(pfad),
                         "Temp-Library blieb nach dem Aufraeumen liegen")


if __name__ == "__main__":
    unittest.main()
