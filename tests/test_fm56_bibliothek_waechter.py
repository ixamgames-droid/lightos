"""FM-56: Waechter der eigenen Geraete-Bibliothek (``fixtures/bibliothek/``).

* jede Datei ist ein gueltiges LightOS-Profil und liegt unter ihrem Namen;
* Hersteller + Modell kommen nur einmal vor;
* jede Datei hat ``quelle`` und ``herkunft`` mit Lizenzangabe;
* fremde Vorlagen (QLC+ Apache-2.0, OFL MIT) sind in THIRD_PARTY_NOTICES.md
  („Geräte-Bibliothek“) mit Verweis auf den Lizenztext unter ``licenses/`` gedeckt;
* SCHEMA.md erklaert im Kopf die drei Quellen und die Herkunftspflicht und
  listet jedes Attribut;
* die Muster unter ``_beispiele/`` laufen nicht vom Code-Stand weg.
"""
from __future__ import annotations

import os
import pathlib
import re
import unittest

from src.core.database import bibliothek_format as BF

ROOT = pathlib.Path(__file__).resolve().parents[1]
BIB = ROOT / "fixtures" / "bibliothek"
SCHEMA = BIB / "SCHEMA.md"
NOTICES = ROOT / "THIRD_PARTY_NOTICES.md"


def _abschnitt(text: str, titel: str) -> str:
    m = re.search(rf"^## {re.escape(titel)}\s*$(.*?)(?=^## |\Z)", text, re.M | re.S)
    return m.group(1) if m else ""


class BibliothekWaechterTest(unittest.TestCase):

    def setUp(self):
        self.dateien = BF.bibliothek_dateien(str(BIB), mit_beispielen=True)
        self.daten = {p: BF.lade_datei(p) for p in self.dateien}

    def test_bibliothek_liegt_im_repo(self):
        self.assertEqual(os.path.normpath(BF.BIBLIOTHEK_DIR), os.path.normpath(str(BIB)))
        self.assertGreaterEqual(len(self.dateien), 3)      # mindestens die Muster

    def test_jede_datei_gueltig_richtig_abgelegt_und_einmalig(self):
        self.assertEqual(BF.pruefe_bibliothek(str(BIB)), [])

    def test_quelle_und_herkunft_mit_lizenz(self):
        for pfad, d in self.daten.items():
            with self.subTest(pfad=os.path.relpath(pfad, ROOT)):
                self.assertTrue(d["quelle"]["titel"].strip())
                self.assertIn(d["herkunft"]["lizenz"],
                              BF.HERKUNFT_ARTEN[d["herkunft"]["art"]])

    def test_fremde_lizenzen_sind_in_den_notices_gedeckt(self):
        text = NOTICES.read_text(encoding="utf-8")
        abschnitt = _abschnitt(text, "Geräte-Bibliothek")
        self.assertTrue(abschnitt, "THIRD_PARTY_NOTICES.md: Abschnitt „Geräte-Bibliothek“ fehlt")
        self.assertIn("licenses/Apache-2.0.txt", abschnitt)
        self.assertIn("fixtures/bibliothek", abschnitt)
        lizenzen = {d["herkunft"]["lizenz"] for d in self.daten.values()}
        # Unbedingt, nicht erst mit der ersten QLC+-Datei: der Konverter
        # (`bibliothek_profil.py qxf`) erzeugt Apache-2.0-Profile, und der
        # Abschnitt verweist auf den Text. Faellt er weg (z. B. weil keine
        # QLC+-3D-Modelle mehr mitkommen), muss das hier auffallen.
        self.assertTrue((ROOT / "licenses" / "Apache-2.0.txt").is_file(),
                        "licenses/Apache-2.0.txt fehlt — die Geraete-Bibliothek braucht ihn")
        if "MIT" in lizenzen:
            links = re.findall(r"licenses/[\w.-]+", abschnitt)
            ofl = [l for l in links if "ofl" in l.lower() or "open-fixture" in l.lower()]
            self.assertTrue(ofl, "OFL-Profile ohne verlinkten MIT-Lizenztext der OFL")
            for l in ofl:
                self.assertTrue((ROOT / l).is_file(), l)

    def test_hersteller_je_ordner_eine_schreibweise(self):
        """UI-74: ``eurolite/`` enthielt einmal „EuroLite“ neben „Eurolite“ —
        in der DB wurden daraus zwei Hersteller, in der Geraeteauswahl zwei
        Ordner fuer dieselbe Firma."""
        je_ordner: dict[str, set] = {}
        for pfad, d in self.daten.items():
            ordner = os.path.relpath(os.path.dirname(pfad), BIB)
            if ordner.startswith("_beispiele"):
                continue
            je_ordner.setdefault(ordner, set()).add(d["hersteller"].strip())
        for ordner, namen in sorted(je_ordner.items()):
            with self.subTest(ordner=ordner):
                self.assertEqual(len(namen), 1, f"{ordner}/: {sorted(namen)}")

    def test_hersteller_bibliotheksweit_eine_schreibweise(self):
        """UI-74: dieselbe Firma (ohne Gross/klein) heisst ueberall gleich —
        auch ``hersteller_kurz`` je Hersteller einheitlich."""
        namen: dict[str, set] = {}
        kurz: dict[str, set] = {}
        for d in self.daten.values():
            h = d["hersteller"].strip()
            namen.setdefault(h.lower(), set()).add(h)
            if d.get("hersteller_kurz"):
                kurz.setdefault(h, set()).add(d["hersteller_kurz"])
        for schluessel, varianten in sorted(namen.items()):
            with self.subTest(hersteller=schluessel):
                self.assertEqual(len(varianten), 1, sorted(varianten))
        for h, varianten in sorted(kurz.items()):
            with self.subTest(hersteller_kurz=h):
                self.assertEqual(len(varianten), 1, sorted(varianten))

    def test_schema_kopf_erklaert_quellen_und_herkunftspflicht(self):
        text = SCHEMA.read_text(encoding="utf-8")
        kopf = text.split("\n## ", 1)[0]
        for wort in ("Herstellerangaben", "selbst geschrieben", "QLC+", "Apache",
                     "Open Fixture Library", "MIT", "herkunft", "urheber", "original",
                     "geaendert", "licenses/", "THIRD_PARTY_NOTICES.md"):
            self.assertIn(wort.lower(), kopf.lower(), wort)

    def test_schema_listet_alle_attribute_und_arten(self):
        text = SCHEMA.read_text(encoding="utf-8")
        for name in list(BF.ATTRIBUTE) + list(BF.TYPEN) + [a for a in BF.RANGE_ARTEN if a]:
            self.assertIn(f"`{name}`", text, name)

    def test_raster_nur_bei_echten_farbzonen(self):
        """FM-61 (Review): ein ``raster`` behauptet ``rows*cols`` Farbzonen —
        das muss einer echten Zonenzahl entsprechen (Farbbaenke, Einzel-Dimmer
        oder Farbraeder, ggf. plus Master). Ein
        Hydrabeam-Modus mit EINER gemeinsamen RGBW-Bank und Raster 1x3 zeigte
        im 3D drei Zonen, von denen nur die erste Farbe bekam.

        Warum ``test_viz50a_panel_geometrie`` das nicht fing: seine frische
        Library kommt aus ``_seed`` und enthaelt nur die Builtins; die Dateien
        hier spielt erst ``ensure_builtins`` ein. Darum die Pruefung direkt auf
        den Dateien."""
        geprueft = 0
        for pfad, d in self.daten.items():
            for m in d.get("modi", ()):
                r = m.get("raster")
                if not r:
                    continue
                geprueft += 1
                zellen = r["rows"] * r["cols"]
                # Zonen sind Farbbaenke (color_r), Lampen mit eigenem Dimmer
                # (intensity, z. B. 2-Lampen-Blinder) oder eigenem Farbrad —
                # jeweils auch mit einem zusaetzlichen Master-Kanal.
                erlaubt = {1}
                for attr in ("color_r", "intensity", "color_wheel"):
                    n = sum(1 for c in m["kanaele"] if c.get("attribut") == attr)
                    erlaubt |= {n, n - 1} - {0}
                with self.subTest(pfad=os.path.relpath(pfad, ROOT), modus=m["name"]):
                    self.assertIn(
                        zellen, erlaubt,
                        f"Raster {r['rows']}x{r['cols']} passt zu keiner Zonenzahl "
                        f"{sorted(erlaubt)} (color_r/intensity/color_wheel, ggf. "
                        f"plus Master) — ohne echte Zonen kein raster")
        self.assertGreater(geprueft, 0, "kein Modus mit raster — Waechter leer")

    def test_kanalzahl_im_modusnamen_stimmt(self):
        """FM-61 (Review): ein Modus, der eine Kanalzahl im Namen traegt
        („16 channel“, „26-CH“, „8-Kanal“), muss genau so viele Kanaele haben."""
        muster = re.compile(r"^\s*(\d+)\s*-?\s*(?:ch|channels?|kanal|kanäle)\b", re.I)
        geprueft = 0
        for pfad, d in self.daten.items():
            for m in d.get("modi", ()):
                treffer = muster.match(m["name"])
                if not treffer:
                    continue
                geprueft += 1
                with self.subTest(pfad=os.path.relpath(pfad, ROOT), modus=m["name"]):
                    self.assertEqual(int(treffer.group(1)), len(m["kanaele"]))
        self.assertGreater(geprueft, 0)

    def test_beispiele_entsprechen_dem_code_stand(self):
        """Die Muster sind aus eingebauten Profilen konvertiert. Aendert sich das
        Builtin, faellt das hier auf — neu erzeugen mit
        ``tools/bibliothek_profil.py export --builtin <KURZ> -o <datei>`` (dann
        quelle/geprueft wieder eintragen)."""
        code = BF.code_builtins_daten()
        beispiele = [p for p in self.dateien if f"{os.sep}_beispiele{os.sep}" in p]
        self.assertEqual(len(beispiele), 3)
        for pfad in beispiele:
            d = dict(self.daten[pfad])
            with self.subTest(pfad=os.path.basename(pfad)):
                soll = dict(code[d["kurzname"]])
                for k in ("quelle", "geprueft", "herkunft", "autor"):
                    d.pop(k)
                    soll.pop(k)
                self.assertEqual(d, soll)


if __name__ == "__main__":
    unittest.main()
