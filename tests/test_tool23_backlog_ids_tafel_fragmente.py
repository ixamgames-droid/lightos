"""TOOL-23: ``backlog_ids`` liest Tafel und Fragmente wie die Tabelle — und
meldet, wenn es sie nicht lesen kann.

Zwei Befunde aus dem Codex-Review #876 (TOOL-11, Punkt 4):

1. **Andere Zerlegung im freien Text.** Die BACKLOG-Tabelle kennt mehrteilige
   Praefixe (``PATCH-GRP-02`` -> Gruppe ``PATCH-GRP``) und den Buchstaben hinten
   (``FM-46b`` -> Nummer 46). Fuer Tafel und Fragment-Dateinamen galt ein
   eigenes Muster, ``\\b[A-Z][A-Z0-9]*-\\d+\\b``. Es fand ``FM-46b`` und
   ``UI-72_UI-73`` GAR NICHT (``\\b`` greift weder zwischen Ziffer und
   Buchstabe noch am Unterstrich) und machte aus ``PATCH-GRP-02`` ein
   ``GRP-02``. Beides sind echte Namen: ``changelog.d/2026-10-02-FM-46b.md``,
   ``…-UI-72_UI-73.md``, der Claim ``FM-46c`` auf der Tafel.

   Die Folge ist genau der Schaden, gegen den es das Werkzeug gibt: eine
   Nummer, die nur auf der Tafel oder in einem Fragment steht, zaehlte nicht —
   und wurde als frei angeboten.

2. **Unlesbare Tafel ohne Warnung.** Liess sich
   ``origin/sessions:SESSIONS.md`` nicht lesen, rechnete das Werkzeug ohne sie
   weiter und endete mit Exit 0.

Gemessen wird an den reinen Funktionen und am Exit-Code von ``main()`` — der
Griff nach git ist zugehalten (wie in ``test_backlog_ids.py``).
"""
import io
import os
import sys
import unittest
from contextlib import redirect_stdout

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))

import backlog_ids as B  # noqa: E402

KOPF = "| ID | Prio | Status | Titel | Details |\n|---|---|---|---|---|\n"


def _gruppen(text: str) -> set:
    """``{(Gruppe, Nummer)}`` aller im Text gefundenen IDs."""
    return {B.zerlege(i)[:2] for i in B.ids_aus_text(text)}


class ZerlegungImTextTest(unittest.TestCase):

    def test_buchstabe_hinten_zaehlt_mit_seiner_nummer(self):
        self.assertIn(("FM", 46), _gruppen("| FM-46c | A | feat/fm46-qxf-head |"))
        self.assertIn(("FM", 46), _gruppen("changelog.d/2026-10-02-FM-46b.md"))
        self.assertIn(("OUT", 61), _gruppen("changelog.d/2026-10-04-OUT-61b.md"))

    def test_zwei_ids_in_einem_fragmentnamen(self):
        self.assertEqual(B.ids_aus_text("changelog.d/2026-10-03-UI-72_UI-73.md"),
                         {"UI-72", "UI-73"})

    def test_mehrteiliges_praefix_bleibt_ganz(self):
        self.assertIn(("PATCH-GRP", 2), _gruppen("| PATCH-GRP-02 | B | fix/x |"))
        self.assertIn(("CRASH-TRIAGE", 1), _gruppen("siehe CRASH-TRIAGE-1, eilt"))

    def test_jede_lesart_zaehlt_lieber_zu_viel_als_zu_wenig(self):
        """Ob ``NEU-FM-73`` zur Gruppe NEU-FM gehoert oder FM-73 mit einem Wort
        davor ist, laesst sich im freien Text nicht entscheiden — beides zaehlt."""
        self.assertEqual(B.ids_aus_text("NEU-FM-73"), {"NEU-FM-73", "FM-73"})
        self.assertLessEqual({("FM", 73)}, _gruppen("Stand: NEU-FM-73 fertig"))

    def test_text_und_tabelle_zerlegen_gleich(self):
        """Der Kern von TOOL-23: dieselbe ID ergibt in allen drei Quellen
        dieselbe Gruppe und Nummer."""
        for item_id in ("FM-30", "PROC-02c", "PATCH-GRP-02", "CRASH-TRIAGE-1",
                        "A3D-26", "FM-46b", "UI-72", "XPLAT-48"):
            with self.subTest(item_id):
                aus_tabelle = B.items_aus_backlog(
                    KOPF + f"| {item_id} | P2 | todo | **T** | d |\n")
                self.assertEqual(list(aus_tabelle), [item_id])
                soll = B.zerlege(item_id)[:2]
                self.assertIn(soll, _gruppen(f"| {item_id} | A | zweig | 2026-10-10T10:47Z |"),
                              "Tafel liest die ID anders als die Tabelle")
                self.assertIn(soll, _gruppen(f"changelog.d/2026-10-10-{item_id}.md"),
                              "Fragmentname liest die ID anders als die Tabelle")

    def test_was_keine_id_ist_bleibt_draussen(self):
        for text in ("SAMMEL-DOKU-C", "LAS-HW-VERIFY", "BACKLOG-STATUS",
                     "seit 2026-10-10T10:47Z", "README.md", "Art-Net 6454",
                     "fix/viz98-bodenfleck-ueber-horizont", "docs/doc70-netzwerk-windows"):
            with self.subTest(text):
                self.assertEqual(B.ids_aus_text(text), set())

    def test_bisheriges_verhalten_bleibt(self):
        text = ("DOC-43           C    -   seit 2026-10-02\n"
                "  - (C) C AN A — Stand: NEU #869 DOC-23, FM-33 fertig")
        self.assertEqual(B.ids_aus_text(text), {"DOC-43", "DOC-23", "FM-33"})
        self.assertEqual(B.ids_aus_text("VIZ-84..87, QA-87/QA-89 und BPM-28."),
                         {"VIZ-84", "QA-87", "QA-89", "BPM-28"})


class NaechsteFreieAusTafelUndFragmentenTest(unittest.TestCase):

    def _naechste(self, backlog_ids: set, text: str, gruppe: str) -> int:
        je_zweig = {"origin/main": dict.fromkeys(backlog_ids, "x"),
                    "(Tafel/Fragmente)": dict.fromkeys(B.ids_aus_text(text), "")}
        return B.naechste_freie(je_zweig, gruppe)

    def test_fm46b_nur_im_fragment_belegt_die_46(self):
        self.assertEqual(
            self._naechste({"FM-45"}, "changelog.d/2026-10-02-FM-46b.md", "FM"), 47)

    def test_claim_mit_buchstabe_auf_der_tafel_belegt_die_nummer(self):
        self.assertEqual(
            self._naechste({"FM-45"}, "| FM-46c | A | feat/fm46-qxf-head |", "FM"), 47)

    def test_mehrteilige_gruppe_zaehlt_in_ihrer_gruppe(self):
        self.assertEqual(
            self._naechste({"PATCH-GRP-01"}, "| PATCH-GRP-02 | B | fix/x |", "PATCH-GRP"), 3)

    def test_doppel_fragment_belegt_beide(self):
        self.assertEqual(
            self._naechste({"UI-71"}, "changelog.d/2026-10-03-UI-72_UI-73.md", "UI"), 74)


class LesefehlerTest(unittest.TestCase):
    """Eine Quelle, die sich nicht lesen laesst, ist eine Luecke — mit Warnung,
    ohne Nummer und mit Exit 2 (wie jeder unlesbare Zweig seit CDX-57)."""

    _TABELLE = KOPF + "| DOC-21 | P3 | todo | **T** | d |\n"

    def _main(self, *, tafel_rc=0, fragmente_rc=0, zweige=()):
        gefragt = []

        def git(*args):
            if args[:1] == ("show",) and args[1].endswith(":BACKLOG.md"):
                return 0, self._TABELLE
            if args[:1] == ("show",) and "SESSIONS.md" in args[1]:
                return tafel_rc, ("| DOC-43 | C | - |" if tafel_rc == 0 else "")
            if args[:1] == ("ls-tree",):
                gefragt.append(args)
                return fragmente_rc, ("changelog.d/2026-10-02-DOC-22.md\n"
                                      if fragmente_rc == 0 else "")
            return 0, ""

        orig = (B._git, B.offene_pr_zweige)
        B._git = git
        B.offene_pr_zweige = lambda: (list(zweige), None)
        puffer = io.StringIO()
        try:
            with redirect_stdout(puffer):
                code = B.main(["--gruppe", "DOC", "--kein-fetch"])
        finally:
            B._git, B.offene_pr_zweige = orig
        return code, puffer.getvalue(), gefragt

    def test_alles_lesbar_gibt_die_nummer(self):
        code, aus, _ = self._main()
        self.assertEqual(code, 0)
        self.assertIn("DOC-44", aus)

    def test_unlesbare_tafel_ist_eine_luecke(self):
        code, aus, _ = self._main(tafel_rc=128)
        self.assertEqual(code, 2, "unlesbare Tafel, aber Exit 0")
        self.assertIn("SESSIONS.md", aus)
        self.assertIn("nicht lesbar", aus)
        self.assertIn("KEINE Nummer ausgegeben", aus)
        self.assertNotIn("naechste freie Nummer", aus)

    def test_unlesbare_fragmente_sind_eine_luecke(self):
        code, aus, _ = self._main(fragmente_rc=128)
        self.assertEqual(code, 2)
        self.assertIn("changelog.d/", aus)
        self.assertIn("KEINE Nummer ausgegeben", aus)

    def test_ref_ohne_fragment_ordner_ist_keine_luecke(self):
        """``git ls-tree <ref> changelog.d/`` liefert fuer einen fehlenden
        Ordner Exit 0 und nichts — deshalb wird so gefragt, nicht mit
        ``<ref>:changelog.d`` (das schlaegt dann fehl)."""
        code, aus, gefragt = self._main(zweige=("alt",))
        self.assertEqual(code, 0)
        for args in gefragt:
            self.assertEqual(args[:2], ("ls-tree", "--name-only"))
            self.assertEqual(args[3], "changelog.d/", args)
            self.assertNotIn(":", args[2], "Ref und Pfad muessen getrennt sein")
        self.assertEqual(sorted(a[2] for a in gefragt), ["origin/alt", "origin/main"])

    def test_weitere_belegte_ids_liefert_ids_und_luecken(self):
        orig = B._git
        B._git = lambda *a: (128, "") if a[0] == "show" else (0, "changelog.d/2026-10-02-FM-46b.md\n")
        try:
            ids, luecken = B.weitere_belegte_ids(["origin/main"])
        finally:
            B._git = orig
        self.assertEqual(ids, {"FM-46b"})
        self.assertEqual(len(luecken), 1)
        self.assertIn("SESSIONS.md", luecken[0])


if __name__ == "__main__":
    unittest.main()
