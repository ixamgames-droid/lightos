"""PROC-03 — die Entscheidungsregel von ``tools/pr_bereit.py`` ist festgenagelt.

Der Befund dahinter: „ist irgendein Check rot?" ist die falsche Frage. Sie
uebersieht drei Zustaende, die alle wie gruen aussehen — **nie geprueft**,
**gruen auf altem Stand**, **teilweise geprueft** — und alle drei sind in diesem
Repo schon vorgekommen. Der schlimmste ist der erste: am 24.08.2026 bekamen zwei
PRs fuer keinen ihrer Commits einen einzigen Check-Run, und weder die
Merge-Schaltflaeche noch ``gh pr merge`` unterscheiden das von „alles gruen".

Was hier geprueft wird und was NICHT
------------------------------------
Das Werkzeug braucht ``gh`` mit angemeldetem Konto und Netz — in der CI ist
beides nicht verlaesslich da. Ein Test, der dort still ueberspringt, waere genau
die Sorte Absicherung, die dieses Repo in PROC-02b und PROC-04 zweimal teuer
bezahlt hat: er laeuft, wird gruen und wirkt nicht.

Deshalb steckt die ganze Entscheidung in ``urteil()`` — einer Funktion ohne Netz,
ohne ``gh``, ohne Zeit. Dieser Test misst **sie**, nicht eine Nachbildung des
Aufrufs (QA-52).
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))

from pr_bereit import (ALT, BEREIT, FRISCH, KONFLIKT,  # noqa: E402
                       NIE_GEPRUEFT, ROT, UNFERTIG, urteil)

GRUEN3 = ["success", "success", "success"]


class NieGepruefstTest(unittest.TestCase):
    """Der Zustand, den man am PR nicht sieht — deshalb steht er ganz oben."""

    def test_kein_check_run_ist_nie_geprueft(self):
        u, _ = urteil(0, [], main_neuer=False, mergeable="MERGEABLE")
        self.assertEqual(u, NIE_GEPRUEFT)

    def test_nie_geprueft_schlaegt_jeden_anderen_zustand(self):
        # Ohne Checks ist auch „mergeable\" bedeutungslos: es gibt nichts, was
        # gruen sein koennte. Wer hier erst auf den Konflikt schaut, meldet den
        # harmloseren Zustand und verschweigt den gefaehrlichen.
        u, _ = urteil(0, [], main_neuer=True, mergeable="CONFLICTING")
        self.assertEqual(u, NIE_GEPRUEFT)


class FrischGepushtTest(unittest.TestCase):
    """★ Die Unterscheidung, ohne die das Werkzeug bei jedem Push Fehlalarm meldet.

    GitHub legt die Check-Runs erst ein paar Sekunden nach dem Push an. Am
    25.08. an #661 und #665 beobachtet — beide standen kurz auf „kein einziger
    Check-Run" und erholten sich von selbst.
    """

    def test_frisch_gepusht_ist_nicht_nie_geprueft(self):
        u, grund = urteil(0, [], main_neuer=False, mergeable="UNKNOWN",
                          kopf_alter_s=12)
        self.assertEqual(u, FRISCH)
        self.assertIn("Push", grund)

    def test_alt_und_ohne_checks_bleibt_nie_geprueft(self):
        u, _ = urteil(0, [], main_neuer=False, mergeable="MERGEABLE",
                      kopf_alter_s=3600)
        self.assertEqual(u, NIE_GEPRUEFT)

    def test_ohne_altersangabe_bleibt_es_beim_strengen_urteil(self):
        # Kein Alter = keine Entschuldigung. Wer die Zeit nicht kennt, darf den
        # gefaehrlichen Zustand nicht wegerklaeren.
        u, _ = urteil(0, [], main_neuer=False, mergeable="MERGEABLE")
        self.assertEqual(u, NIE_GEPRUEFT)

    def test_frisch_gilt_nur_ohne_checks(self):
        # Laufen schon Checks, ist „laeuft noch" die genauere Aussage.
        u, _ = urteil(3, ["success", "pending", "success"], main_neuer=False,
                      mergeable="MERGEABLE", kopf_alter_s=5)
        self.assertEqual(u, UNFERTIG)


class RangfolgeTest(unittest.TestCase):
    def test_ein_fehlschlag_schlaegt_alles_uebrige(self):
        u, _ = urteil(3, ["success", "failure", "success"],
                      main_neuer=True, mergeable="CONFLICTING")
        self.assertEqual(u, ROT)

    def test_abgebrochen_und_zeitueberschreitung_zaehlen_als_fehlschlag(self):
        # Ein `cancelled` ist kein Ergebnis, sieht in `gh pr checks` aber nicht
        # rot aus. Wer nur auf "failure" prueft, merged darueber hinweg.
        for schluss in ("cancelled", "timed_out", "action_required"):
            u, _ = urteil(3, ["success", schluss, "success"],
                          main_neuer=False, mergeable="MERGEABLE")
            self.assertEqual(u, ROT, schluss)

    def test_laufende_checks_sind_kein_urteil(self):
        for offen in (None, "", "pending", "queued", "in_progress"):
            u, _ = urteil(3, ["success", offen, "success"],
                          main_neuer=False, mergeable="MERGEABLE")
            self.assertEqual(u, UNFERTIG, repr(offen))

    def test_konflikt_kommt_vor_dem_alten_stand(self):
        # Beides trifft oft zusammen; der Konflikt ist die konkretere Aussage.
        u, _ = urteil(3, GRUEN3, main_neuer=True, mergeable="CONFLICTING")
        self.assertEqual(u, KONFLIKT)

    def test_gruen_aber_main_ist_weitergezogen(self):
        u, grund = urteil(3, GRUEN3, main_neuer=True, mergeable="MERGEABLE")
        self.assertEqual(u, ALT)
        self.assertIn("main", grund)


class PositivkontrolleTest(unittest.TestCase):
    """Ein Waechter, der jeden Merge blockiert, wird umgangen und ist damit keiner."""

    def test_alles_gruen_und_aktuell_ist_bereit(self):
        u, _ = urteil(3, GRUEN3, main_neuer=False, mergeable="MERGEABLE")
        self.assertEqual(u, BEREIT)

    def test_unbekannte_mergefaehigkeit_blockiert_nicht(self):
        # `gh` liefert kurz nach einem Push `UNKNOWN`, waehrend GitHub noch
        # rechnet. Wer das als Konflikt wertet, meldet Fehlalarm bei jedem
        # frisch gepushten PR.
        for m in ("UNKNOWN", None, ""):
            u, _ = urteil(3, GRUEN3, main_neuer=False, mergeable=m)
            self.assertEqual(u, BEREIT, repr(m))

    def test_neutral_und_uebersprungen_blockieren_nicht(self):
        # `neutral` / `skipped` sind gueltige Abschluesse, keine Fehlschlaege —
        # ein uebersprungener Job (z. B. per `if:`) darf nicht rot faerben.
        for schluss in ("neutral", "skipped"):
            u, _ = urteil(3, ["success", schluss, "success"],
                          main_neuer=False, mergeable="MERGEABLE")
            self.assertEqual(u, BEREIT, schluss)


class BegruendungTest(unittest.TestCase):
    def test_jedes_urteil_traegt_eine_begruendung(self):
        faelle = [
            (0, [], False, "MERGEABLE"),
            (3, ["failure"] + GRUEN3, False, "MERGEABLE"),
            (3, ["pending"] + GRUEN3, False, "MERGEABLE"),
            (3, GRUEN3, True, "CONFLICTING"),
            (3, GRUEN3, True, "MERGEABLE"),
            (3, GRUEN3, False, "MERGEABLE"),
        ]
        for f in faelle:
            _u, grund = urteil(*f)
            self.assertTrue(grund.strip(), f)
            # Eine Begruendung, die nur das Urteil wiederholt, hilft niemandem.
            self.assertGreater(len(grund), 20, f)


if __name__ == "__main__":
    unittest.main()
