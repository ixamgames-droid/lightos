"""QA-55 — die Doku- und Backlog-Waechter sehen jetzt, was sie sehen sollen.

Zwei Waechter mit je einer Luecke, beide aus dem Werkzeug-Audit:

* **Der Doku-Link-Pruefer trennte den Anker ab und warf ihn weg.** Ein Link auf
  einen Abschnitt, den es nicht gibt, galt als heil — der Leser landet oben auf
  der Seite und sucht selbst. Und gescannt wurde eine feste Liste von fuenf
  Wurzeldateien; ungeprueft blieben ausgerechnet die, die ein Neuzugang zuerst
  liest (WORKFLOW.md, INSTALL.md, ARCHITECTURE.md, CONTRIBUTING.md, …).
* **Der Backlog-Guard hatte dieselbe Blindstelle wie das Muster, gegen das er
  schuetzt** — er verlangte selbst eine ID aus Buchstaben. Eine Zeile ohne
  solche ID war fuer beide unsichtbar, und der Waechter meldete Ruhe.
"""
import os
import re
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class AnkerWerdenGeprueftTest(unittest.TestCase):

    def test_slug_folgt_githubs_regel_fuer_mehrfache_leerzeichen(self):
        """★★ Die Feinheit, an der die erste Fassung scheiterte.

        GitHub ersetzt **jedes einzelne** Leerzeichen durch ``-`` und fasst sie
        NICHT zusammen. „Sync — der Teil" wird deshalb ``sync--der-teil`` mit
        ZWEI Bindestrichen: der Gedankenstrich faellt weg, seine beiden
        Leerzeichen bleiben. Mit ``\\s+`` zusammengefasst meldete das Gate neun
        tote Anker, von denen fuenf gar keine waren — und der naechste Schritt
        waere gewesen, **korrekte Links zu „reparieren"**.
        """
        from tools.check_doc_links import _slug
        self.assertEqual("4-synchronisierung--der-wichtige-teil",
                         _slug("4. Synchronisierung — der wichtige Teil"))
        self.assertEqual("einfach-normal", _slug("Einfach normal"))

    def test_emoji_und_satzzeichen_fallen_weg(self):
        from tools.check_doc_links import _slug
        self.assertEqual("werkzeuge", _slug("🧰 Werkzeuge:"))

    def test_anker_werden_aus_ueberschriften_und_html_gelesen(self):
        import tempfile
        from tools.check_doc_links import _anker
        with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False,
                                         encoding="utf-8") as f:
            f.write('# Erste Ebene\n\n## Zweite Ebene\n\n'
                    '<a name="handgemacht"></a>\n\n'
                    '```\n## In einem Codeblock\n```\n')
            pfad = f.name
        try:
            a = _anker(pfad)
        finally:
            os.unlink(pfad)
        self.assertIn("erste-ebene", a)
        self.assertIn("zweite-ebene", a)
        self.assertIn("handgemacht", a)
        self.assertNotIn("in-einem-codeblock", a,
                         "Ueberschriften in Codebloecken sind keine Anker")

    def test_das_gate_findet_einen_toten_anker(self):
        """Positivkontrolle: ohne sie waere nicht zu unterscheiden, ob das
        Gate nichts findet oder nichts mehr prueft."""
        import tempfile
        from tools.check_doc_links import _anker
        with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False,
                                         encoding="utf-8") as f:
            f.write("# Nur dieser Abschnitt\n")
            pfad = f.name
        try:
            self.assertNotIn("gibt-es-nicht", _anker(pfad))
            self.assertIn("nur-dieser-abschnitt", _anker(pfad))
        finally:
            os.unlink(pfad)

    def test_alle_wurzel_markdown_dateien_werden_gescannt(self):
        """Eine Aufzaehlung vergisst jede kuenftige Datei automatisch."""
        from tools.check_doc_links import _iter_md_files
        gescannt = {os.path.relpath(p, REPO) for p in _iter_md_files()}
        for pflicht in ("WORKFLOW.md", "INSTALL.md", "ARCHITECTURE.md",
                        "CONTRIBUTING.md", "AGENTS.md", "COORDINATION.md"):
            if os.path.exists(os.path.join(REPO, pflicht)):
                self.assertIn(pflicht, gescannt,
                              f"{pflicht} wird nicht auf tote Links geprueft")

    def test_das_repo_hat_keine_toten_anker(self):
        """Die Aussage, die das Gate im Alltag trifft."""
        from tools.check_doc_links import scan
        _total, dead, _ok = scan()
        anker_tot = [d for d in dead if "Abschnitt" in d[2]]
        self.assertEqual([], anker_tot, f"tote Abschnitts-Links: {anker_tot}")

    def test_scan_meldet_einen_toten_anker_wirklich(self):
        """★★ Von der Mutationsmessung erzwungen.

        Der Test darueber prueft, dass es KEINE toten Anker gibt — und bleibt
        deshalb gruen, wenn man die Anker-Pruefung ersatzlos abschaltet: dann
        gibt es erst recht keine. Ein Gate, dessen einziger Beleg „nichts
        gefunden" lautet, ist von einem abgeschalteten Gate nicht zu
        unterscheiden. Hier laeuft ``scan()`` deshalb ueber ein Verzeichnis mit
        einem ECHTEN toten Anker und muss ihn melden.
        """
        import tempfile
        from unittest import mock
        import tools.check_doc_links as cdl

        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, "docs"))
            with open(os.path.join(tmp, "docs", "a.md"), "w",
                      encoding="utf-8") as f:
                f.write("# Es gibt nur diesen Abschnitt\n\n"
                        "[hin](#den-abschnitt-gibt-es-nicht)\n"
                        "[her](#es-gibt-nur-diesen-abschnitt)\n")
            with mock.patch.object(cdl, "REPO", tmp):
                total, dead, _ok = cdl.scan()

        self.assertEqual(2, total, "beide Anker-Links muessen gezaehlt werden")
        self.assertEqual(1, len(dead), f"erwartet genau einen toten: {dead}")
        self.assertIn("den-abschnitt-gibt-es-nicht", dead[0][1])


class BacklogGuardSiehtJedeItemZeileTest(unittest.TestCase):
    """★★ Ein Waechter mit derselben Blindstelle wie sein Schuetzling."""

    def test_zeile_ohne_buchstaben_id_wird_erkannt(self):
        """Der reale Fund: eine blockierte P3-Zeile mit einem Gedankenstrich
        statt einer ID. Fuer Verdichtung, Queue, Stats und den Lint existierte
        sie nicht — und der alte Guard meldete Ruhe, weil er selbst eine ID aus
        Buchstaben verlangte.

        ★★ Dieser Test IMPORTIERT das Muster, statt es nachzubauen. Die erste
        Fassung definierte beide Regexe selbst — und blieb deshalb gruen, als
        die Mutation den Guard im Produktionscode wieder eng machte: sie
        pruefte ihre eigene Kopie. Genau die Fehlerklasse aus QA-52, und sie
        ist mir hier im selben PR passiert, in dem ich sie beschreibe.
        """
        from test_backlog_lint import LOOKS_LIKE_ITEM, ROW
        zeile = "| — | P3 | blocked | **Hardware-Verifikation** Ether Dream |\n"
        self.assertIsNone(ROW.match(zeile),
                          "die Zeile ist fuer das ID-Muster unsichtbar — das "
                          "ist der Grund, warum es den Guard gibt")
        self.assertIsNotNone(LOOKS_LIKE_ITEM.match(zeile),
                             "der Guard muss genau diese Zeile sehen")

    def test_der_guard_bleibt_breiter_als_das_id_muster(self):
        """Die Eigenschaft dahinter, unabhaengig vom konkreten Beispiel: ein
        Waechter, der nur erkennt, was sein Schuetzling ohnehin erkennt, kann
        per Konstruktion nichts finden."""
        from test_backlog_lint import LOOKS_LIKE_ITEM, ROW
        beispiele = [
            "| — | P3 | blocked | x |\n",
            "| 3D-Umbau | P2 | todo | x |\n",
            "| mit leerzeichen | P1 | todo | x |\n",
        ]
        unsichtbar = [z for z in beispiele if not LOOKS_LIKE_ITEM.match(z)]
        self.assertEqual([], unsichtbar,
                         f"der Guard uebersieht Item-Zeilen: {unsichtbar}")
        self.assertTrue(all(ROW.match(z) is None for z in beispiele),
                        "Beispiele muessen fuer ROW unsichtbar sein, sonst "
                        "belegen sie nichts")

    def test_der_gefundene_eintrag_hat_jetzt_eine_id(self):
        with open(os.path.join(REPO, "BACKLOG.md"), encoding="utf-8") as f:
            text = f.read()
        self.assertIn("| LAS-HW-VERIFY | P3 | blocked |", text)
        self.assertNotIn("| — | P3 |", text,
                         "es gibt wieder eine Item-Zeile ohne ID")


if __name__ == "__main__":
    unittest.main()
