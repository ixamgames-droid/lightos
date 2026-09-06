"""`validate_and_repair` loeschte Nutzerwerte, wenn eine Pruefung WARF.

★★★ Zwei Fragen, eine Menge — mit ENTGEGENGESETZTEN sicheren Richtungen
(Review-Checkliste 18):

* *„EXISTIERT dieses Geraet im Patch?"* — das ist die **Loeschgrundlage**:
  `validate_and_repair` raeumt Programmer-, Cue- und Szenenwerte fuer fids, die
  nicht in `valid_fids` stehen. Hier ist **Uebertreiben sicher**: ein Geraet zu
  viel heisst „ein verwaister Wert bleibt liegen".
* *„Ist seine KONFIGURATION in Ordnung?"* — das sind die `issues`. Dort ist
  Untertreiben sicher.

Bis 2026-09-06 beantwortete `valid_fids` beide: der `add` stand am ENDE des
`try`, also NACH allen Pruefungen. Warf eine davon, wurde er nie erreicht — und
das Geraet galt als nicht vorhanden. Die Folge war kein Hinweis, sondern ein
**Loeschen** seiner Werte, bei JEDEM `open_show`.

⚠️ Der Ausloeser liegt real vor: in der Bibliothek des Betreibers stehen **2
doppelte `(fixture_id, name)`-Modus-Paare** (gemessen mit
`SELECT fixture_id, name, COUNT(*) ... HAVING COUNT(*)>1`), und
`scalar_one_or_none()` wirft darauf `MultipleResultsFound`.
"""
from __future__ import annotations

import io
import os
import sys
import tokenize
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

QUELLE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                      "src", "core", "sync.py")


def _nur_code(text: str) -> str:
    """Quelltext ohne Kommentare — Zeilen und Spalten bleiben.

    ★ Muss sein, und zwar aus eigener Erfahrung: die erste Fassung dieser
    Pruefung fand ``scalar_one_or_none()`` im **Kommentar**, den ich zur
    Erklaerung des Fixes daneben geschrieben hatte, und meldete deshalb
    „nicht behoben". Ein Textsucher liest den Text, den man ueber ihn schreibt
    (Review-Checkliste 20). Gleiche Loesung wie in QA-76.
    """
    zeilen = text.splitlines(keepends=True)
    try:
        marken = list(tokenize.generate_tokens(io.StringIO(text).readline))
    except (tokenize.TokenError, IndentationError, SyntaxError):
        return text
    for m in marken:
        if m.type != tokenize.COMMENT:
            continue
        z = m.start[0] - 1
        if z < len(zeilen):
            zeilen[z] = (zeilen[z][:m.start[1]]
                         + " " * (m.end[1] - m.start[1])
                         + zeilen[z][m.end[1]:])
    return "".join(zeilen)


class ExistenzVorGueltigkeitTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        with open(QUELLE, encoding="utf-8") as f:
            cls.code = _nur_code(f.read())
        cls.rumpf = cls.code[cls.code.index("for f in patched:"):]

    def test_die_fid_wird_VOR_den_pruefungen_vermerkt(self):
        """★★ Der Kern. Steht der ``add`` hinter einer Pruefung, die werfen
        kann, entscheidet ein Konfigurationsfehler ueber das LOESCHEN von
        Nutzerwerten — und das ist die falsche Fehlrichtung."""
        add = self.rumpf.index("valid_fids.add(fid)")
        werfend = self.rumpf.index("scalar_one_or_none()")
        self.assertLess(
            add, werfend,
            "valid_fids.add(fid) steht hinter einer werfenden Pruefung — "
            "dann loescht ein Konfigurationsfehler Programmer-, Cue- und "
            "Szenenwerte")

    def test_der_add_steht_nicht_am_ende_des_try(self):
        """Gegenprobe zur Stellung: zwischen ``add`` und dem ``except`` muss
        noch echter Pruef-Code liegen. Waere der ``add`` die letzte Anweisung,
        waere er wieder von allem davor abhaengig."""
        add = self.rumpf.index("valid_fids.add(fid)")
        exc = self.rumpf.index("except Exception as e_inner")
        dazwischen = self.rumpf[add:exc]
        self.assertGreater(dazwischen.count("issues.append"), 3,
                           "zwischen add und except stehen kaum Pruefungen — "
                           "Stellung vermutlich wieder verrutscht")

    def test_die_fehlermeldung_nennt_das_geraet(self):
        """Ohne fid stand dort nur „PatchedFixture", und man konnte nicht
        sehen, WELCHES Geraet sich nicht pruefen liess."""
        exc = self.rumpf.index("except Exception as e_inner")
        block = self.rumpf[exc:exc + 500]
        self.assertIn("PatchedFixture[", block)

    def test_die_loeschstellen_haengen_wirklich_an_valid_fids(self):
        """Belegt die Praemisse dieses Tests: ``valid_fids`` IST eine
        Loeschgrundlage. Faellt das weg, ist die Stellung des ``add`` egal —
        dann darf dieser Test ruhig scheitern und neu gedacht werden."""
        for marke in ("stale_progs", "stale_in_cue"):
            with self.subTest(stelle=marke):
                self.assertIn(marke, self.code)
        self.assertGreaterEqual(
            self.code.count("not in valid_fids"), 3,
            "weniger Loeschstellen als erwartet — Annahme pruefen")


class KommentareTaeuschenNichtTest(unittest.TestCase):
    """★ Die Selbstkontrolle der Pruefung oben."""

    def test_ein_kommentar_zaehlt_nicht_als_code(self):
        probe = ("x = 1\n"
                 "# hier steht scalar_one_or_none() nur als Erklaerung\n"
                 "y = 2\n")
        code = _nur_code(probe)
        self.assertNotIn("scalar_one_or_none", code)
        self.assertEqual(len(code.splitlines()), len(probe.splitlines()),
                         "Zeilenstruktur muss erhalten bleiben")


if __name__ == "__main__":
    unittest.main()
