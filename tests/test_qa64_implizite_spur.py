"""QA-64 (Rest) — die implizite Spur als echter CI-Waechter.

Fast jedes Item bringt eine Testdatei mit, die nach seiner ID heisst
(``UI-137`` -> ``tests/test_ui137_*.py``). Steht so eine Datei im Baum, ist die
Arbeit gelandet. Steht das Item trotzdem auf ``todo``, wird es beim naechsten
Lauf erneut angeboten — genau dieser eine Fall macht diesen Test rot.

Anders als die ausdrueckliche Spur (``tests/test_qa64_status_drift.py``)
braucht diese Pruefung KEINE Git-Refs: nur BACKLOG.md, die Fragmente und die
Dateiliste von ``tests/``. Deshalb wirkt sie auch in der CI.

Bewusst eng: ``review`` + Datei ist der normale Zustand nach dem Merge bis zum
Einsammeln (nur gezaehlt), ``teils``/``blocked``/``decision`` duerfen Vorarbeit
samt Test haben, ``done`` ohne Datei hat schlicht keine Spur. Ausnahme am Item:
``<!-- spur: keine -->``.
"""
import contextlib
import io
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "tools"))

import backlog_status_drift as bsd  # noqa: E402

# Gemessen am 16.11.2026 (origin/main 1157c28e): 1111 Items, davon 27 mit
# ausdruecklicher und 512 mit impliziter Spur = 48,5 %. Der Sockel liegt etwas
# darunter, damit eine Runde neuer Befund-Items (todo, noch ohne Test) ihn
# nicht reisst; faellt er doch, wurde die Benennung aufgegeben.
SOCKEL = 0.45

KOPF = ("| ID | Prio | Status | Titel | Details |\n"
        "|---|---|---|---|---|\n")


def _items(*zeilen):
    return bsd.wirksame_items(KOPF + "".join(zeilen), [])


class IdGrenzeTest(unittest.TestCase):
    def _index(self, *namen):
        return bsd.testdateien_nach_schluessel(namen)

    def test_schluessel(self):
        self.assertEqual(bsd.id_schluessel("UI-137"), "ui137")
        self.assertEqual(bsd.id_schluessel("FM-14b"), "fm14b")
        self.assertEqual(bsd.id_schluessel("QA-LIVE"), "qalive")
        self.assertEqual(bsd.datei_schluessel("test_ui137_x_y.py"), "ui137")
        self.assertEqual(bsd.datei_schluessel("test_ui137.py"), "ui137")
        self.assertIsNone(bsd.datei_schluessel("backlog_eintrag.py"))
        self.assertIsNone(bsd.datei_schluessel("test_ui137_x.txt"))

    def test_kurze_id_trifft_keine_laengere(self):
        idx = self._index("test_ui137_x.py", "test_fm14b_ring.py")
        self.assertEqual(bsd.implizite_spur("UI-13", idx), [])
        self.assertEqual(bsd.implizite_spur("UI-1", idx), [])
        self.assertEqual(bsd.implizite_spur("FM-14", idx), [])
        self.assertEqual(bsd.implizite_spur("UI-137", idx), ["test_ui137_x.py"])
        self.assertEqual(bsd.implizite_spur("FM-14b", idx), ["test_fm14b_ring.py"])

    def test_sonder_id_ohne_nummer(self):
        idx = self._index("test_qalive_probe.py", "test_qa_live_x.py",
                          "test_qalive2_x.py")
        self.assertEqual(bsd.implizite_spur("QA-LIVE", idx), ["test_qalive_probe.py"])
        self.assertEqual(bsd.implizite_spur("VIZ-PERF", idx), [])


class UrteilTest(unittest.TestCase):
    def test_nur_todo_mit_datei_wird_beanstandet(self):
        self.assertEqual(bsd.implizit_urteil("offen", True), bsd.IMPLIZIT_TODO)
        self.assertEqual(bsd.implizit_urteil("review", True), "wartet")
        for k in ("unterwegs", "erledigt"):
            self.assertIsNone(bsd.implizit_urteil(k, True), k)
        for k in ("offen", "review", "unterwegs", "erledigt"):
            self.assertIsNone(bsd.implizit_urteil(k, False), k)

    def test_positivkontrolle_todo_plus_datei(self):
        erg = bsd.implizite_pruefung(
            _items("| QA-900 | P2 | todo | Neu | Text |\n"), ["test_qa900_x.py"])
        self.assertEqual(len(erg["beanstandet"]), 1, erg)
        self.assertIn("QA-900", erg["beanstandet"][0])
        self.assertIn("tests/test_qa900_x.py", erg["beanstandet"][0])

    def test_negativkontrollen(self):
        erg = bsd.implizite_pruefung(_items(
            "| QA-901 | P2 | todo | Ohne jede Spur | Text |\n",
            "| QA-902 | P2 | review (PR #1) | Im PR | Text |\n",
            "| QA-903 | P2 | ✅ teils (Teil 1) | Halb | Text |\n",
            "| QA-904 | P2 | blocked (Hardware) | Wartet | Text |\n",
            "| QA-905 | P2 | decision | Offen | Text |\n",
            "| QA-906 | P2 | ✅ done (2026-11-01) | Fertig | Text |\n",
            "| QA-907 | P2 | ✅ done (2026-11-01) | Fertig ohne Test | Text |\n"),
            ["test_qa902_x.py", "test_qa903_x.py", "test_qa904_x.py",
             "test_qa905_x.py", "test_qa906_x.py"])
        self.assertEqual(erg["beanstandet"], [])
        self.assertEqual(erg["wartet"], ["QA-902"])
        self.assertEqual(sorted(erg["ohne"]), ["QA-901", "QA-907"])

    def test_ausnahme_am_item(self):
        erg = bsd.implizite_pruefung(_items(
            "| QA-910 | P2 | todo | Absicht | Text <!-- spur: keine :: Probe --> |\n"),
            ["test_qa910_x.py"])
        self.assertEqual(erg["beanstandet"], [])
        self.assertEqual(erg["ausnahme"], ["QA-910"])
        self.assertEqual(erg["ausdruecklich"], [])

    def test_ausdrueckliche_spur_geht_vor(self):
        erg = bsd.implizite_pruefung(_items(
            "| QA-911 | P2 | todo | X | Text <!-- spur: tools/x.py :: Y --> |\n"),
            ["test_qa911_x.py"])
        self.assertEqual(erg["ausdruecklich"], ["QA-911"])
        self.assertEqual(erg["beanstandet"], [])


class FragmentTest(unittest.TestCase):
    """Wirksamer Status = Zeile plus Fragment — gelesen ueber backlog_sammeln."""

    def setUp(self):
        self.verz = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.verz)
        os.makedirs(os.path.join(self.verz, "tests"))
        self.bs = bsd._sammler()
        os.makedirs(os.path.join(self.verz, self.bs.FRAGMENT_ORDNER))

    def _schreib(self, rel, text):
        with open(os.path.join(self.verz, rel), "w", encoding="utf-8") as f:
            f.write(text)

    def _frag(self, item_id, kopf, frei=""):
        self._schreib(os.path.join(self.bs.FRAGMENT_ORDNER, item_id + ".md"),
                      kopf + "\n\n" + frei + "\n")

    def test_fragment_uebersteuert_die_zeile(self):
        self._schreib("BACKLOG.md", KOPF
                      + "| QA-920 | P2 | todo | War offen | Text |\n"
                      + "| QA-921 | P2 | review (PR #2) | War im PR | Text |\n")
        self._frag("QA-920", "ID: QA-920\nStatus: review")
        self._frag("QA-921", "ID: QA-921\nStatus: todo")
        self._frag("QA-922", "ID: QA-922\nPrioritaet: P2\nStatus: todo\nTitel: Neu")
        self._frag("QA-923", "ID: QA-923\nPrioritaet: P2\nStatus: todo\nTitel: Neu",
                   "Absicht. <!-- spur: keine -->")
        for n in ("test_qa920_x.py", "test_qa921_x.py", "test_qa922_x.py",
                  "test_qa923_x.py"):
            self._schreib(os.path.join("tests", n), "")
        erg = bsd.implizite_pruefung_im_repo(self.verz)
        beanstandet = sorted(b.split(":")[0] for b in erg["beanstandet"])
        self.assertEqual(beanstandet, ["QA-921", "QA-922"], erg)
        self.assertEqual(erg["wartet"], ["QA-920"])
        self.assertEqual(erg["ausnahme"], ["QA-923"])

    def test_werkzeug_nur_implizit_strict_wird_rot(self):
        self._schreib("BACKLOG.md", KOPF + "| QA-930 | P2 | todo | X | Text |\n")
        self._schreib(os.path.join("tests", "test_qa930_x.py"), "")
        puffer = io.StringIO()
        with mock.patch.object(bsd, "BACKLOG", os.path.join(self.verz, "BACKLOG.md")), \
                mock.patch.object(bsd, "_git", side_effect=AssertionError("kein git")), \
                contextlib.redirect_stdout(puffer):
            rc = bsd.main(["--nur-implizit", "--strict"])
        self.assertEqual(rc, 1, puffer.getvalue())
        self.assertIn("QA-930", puffer.getvalue())
        self.assertIn("ausdrueckliche Spur 0", puffer.getvalue())
        self.assertIn("implizite Spur (ID-Testdatei) 1", puffer.getvalue())


class EchterBaumTest(unittest.TestCase):
    """Das eigentliche Gate: der heutige Arbeitsbaum."""

    @classmethod
    def setUpClass(cls):
        cls.erg = bsd.implizite_pruefung_im_repo(REPO)

    def test_kein_todo_item_hat_eine_id_testdatei(self):
        self.assertEqual(self.erg["beanstandet"], [], (
            "Diese Items stehen auf todo, obwohl ihre Testdatei im Baum steht — "
            "die Arbeit ist gelandet, das Item wuerde erneut angeboten. Status "
            "im Fragment nachziehen (review/teils), oder bei Absicht "
            "<!-- spur: keine --> an das Item:\n  "
            + "\n  ".join(self.erg["beanstandet"])))

    def test_abdeckung_faellt_nicht_unter_den_sockel(self):
        self.assertGreaterEqual(bsd.abdeckung(self.erg), SOCKEL,
                                "\n".join(bsd.bericht_implizit(self.erg)))

    def test_bericht_nennt_beide_arten_getrennt(self):
        zeilen = "\n".join(bsd.bericht_implizit(self.erg))
        self.assertIn("ausdrueckliche Spur", zeilen)
        self.assertIn("implizite Spur (ID-Testdatei)", zeilen)
        self.assertIn("wartet aufs Einsammeln", zeilen)


if __name__ == "__main__":
    unittest.main()
