"""PROC-14 — ``tools/pr_bereit.py`` setzt den Claim durch, statt ihn nur zu verlangen.

Der Befund: Claim und Release waren reine Modelldisziplin. COORDINATION.md
verlangt den Claim vor der Arbeit, aber kein Werkzeug hat ihn geprueft — und
genau so ist ENG-20 (#743/#744) entstanden. Jetzt ist ein PR, dessen Zweig
keinen Claim auf der Tafel hat, nicht bereit, und die Merge-Pruefung (mit
PR-Nummern) endet mit Exit 1.

Nachgeschaerft im Review: ein VERFALLENER Claim haelt den Merge nicht auf (der
Release kommt erst nach dem Merge, CI kann laenger als 4 h dauern) — nur eine
Warnung. Der Bericht ueber alle offenen PRs endet wegen fehlender Claims nur
mit ``--strict`` mit Exit 1, und Entwuerfe zaehlen nie als „Claim fehlt".

Was hier geprueft wird und was NICHT
------------------------------------
NIE die echte Tafel und NIE GitHub: ``claim_pruefung()`` und ``mit_claim()``
sind rein, und fuer den Weg durch ``main()`` werden ``_gh_json`` und
``_lade_tafel`` durch Attrappen ersetzt (dasselbe Prinzip wie in
``test_proc03_pr_bereit.py``: gemessen wird die Entscheidung, nicht das Netz).
"""
import contextlib
import io
import os
import sys
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))

import pr_bereit  # noqa: E402
from pr_bereit import (BEREIT, ENTWURF, OHNE_CLAIM, ROT,  # noqa: E402
                       claim_pruefung, mit_claim)

JETZT = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)
ZWEIG = "fix/proc14-claim-pruefung"


def _claim(branch=ZWEIG, seit=JETZT - timedelta(minutes=30), item="PROC-14",
           sitzung="B"):
    stempel = seit if isinstance(seit, str) else seit.strftime("%Y-%m-%dT%H:%MZ")
    return {"item": item, "sitzung": sitzung, "branch": branch,
            "seit": stempel, "dateien": "-"}


class ClaimPruefungTest(unittest.TestCase):
    def test_aktiver_claim_auf_dem_zweig_genuegt(self):
        ok, grund = claim_pruefung({"claims": [_claim()]}, ZWEIG, JETZT)
        self.assertTrue(ok)
        self.assertIn("PROC-14", grund)

    def test_leere_tafel_ist_kein_claim(self):
        ok, grund = claim_pruefung({"claims": []}, ZWEIG, JETZT)
        self.assertFalse(ok)
        # Die Meldung sagt, was zu tun ist — und wie man bewusst uebersteuert.
        self.assertIn("claim", grund)
        self.assertIn("--ohne-claim", grund)

    def test_claim_auf_anderem_zweig_zaehlt_nicht(self):
        ok, _ = claim_pruefung({"claims": [_claim(branch="fix/anderes")]},
                               ZWEIG, JETZT)
        self.assertFalse(ok)

    def test_claim_ohne_zweig_zaehlt_nicht(self):
        # `claim` ohne `--branch` schreibt "-" — das darf keinen PR decken.
        ok, _ = claim_pruefung({"claims": [_claim(branch="-")]}, ZWEIG, JETZT)
        self.assertFalse(ok)

    def test_verfallener_claim_zaehlt_mit_warnung(self):
        # Der Release kommt erst nach dem Merge — ein PR, der laenger als
        # VERFALL auf CI wartet, darf am verfallenen Claim nicht scheitern.
        alt = _claim(seit=JETZT - timedelta(hours=5))
        ok, grund = claim_pruefung({"claims": [alt]}, ZWEIG, JETZT)
        self.assertTrue(ok)
        self.assertTrue(grund.startswith("Warnung"), grund)
        self.assertIn("verfallen", grund)
        self.assertIn("refresh", grund)

    def test_verfall_kommt_aus_session_claim(self):
        # Knapp innerhalb der Frist ist aktiv — dieselbe Grenze wie `list`.
        knapp = _claim(seit=JETZT - pr_bereit.session_claim.VERFALL
                       + timedelta(minutes=1))
        ok, _ = claim_pruefung({"claims": [knapp]}, ZWEIG, JETZT)
        self.assertTrue(ok)

    def test_ein_aktiver_neben_einem_verfallenen_genuegt(self):
        tafel = {"claims": [_claim(seit=JETZT - timedelta(hours=9), item="ALT-1"),
                            _claim()]}
        ok, grund = claim_pruefung(tafel, ZWEIG, JETZT)
        self.assertTrue(ok)
        self.assertIn("PROC-14", grund)
        # Der aktive wird genannt — keine Warnung, obwohl ein alter daneben steht.
        self.assertNotIn("Warnung", grund)

    def test_vorsatz_am_zweignamen_stoert_nicht(self):
        for eingetippt in ("origin/" + ZWEIG, "refs/heads/" + ZWEIG,
                           f"  {ZWEIG} "):
            ok, _ = claim_pruefung({"claims": [_claim(branch=eingetippt)]},
                                   ZWEIG, JETZT)
            self.assertTrue(ok, eingetippt)

    def test_pr_ohne_zweignamen_faellt_durch(self):
        ok, _ = claim_pruefung({"claims": [_claim(branch="-")]}, "", JETZT)
        self.assertFalse(ok)


class MitClaimTest(unittest.TestCase):
    def test_gruen_ohne_claim_heisst_ohne_claim(self):
        u, grund, fehlt = mit_claim(BEREIT, "3 Checks gruen", False, "kein Claim")
        self.assertEqual(u, OHNE_CLAIM)
        self.assertTrue(fehlt)
        self.assertIn("kein Claim", grund)

    def test_rot_bleibt_rot_und_der_claim_wird_angehaengt(self):
        u, grund, fehlt = mit_claim(ROT, "1 von 3 rot", False, "kein Claim")
        self.assertEqual(u, ROT)
        self.assertTrue(fehlt)
        self.assertIn("kein Claim", grund)

    def test_uebersteuert_mit_begruendung(self):
        u, grund, fehlt = mit_claim(BEREIT, "3 Checks gruen", False, "kein Claim",
                                    uebersteuert="PR von vor PROC-14")
        self.assertEqual(u, BEREIT)
        self.assertFalse(fehlt)
        self.assertIn("PR von vor PROC-14", grund)

    def test_mit_claim_aendert_nichts(self):
        self.assertEqual(mit_claim(BEREIT, "g", True, "Claim X"),
                         (BEREIT, "g", False))

    def test_verfallener_claim_bleibt_bereit_mit_warnung(self):
        u, grund, fehlt = mit_claim(BEREIT, "g", True, "Warnung: verfallen")
        self.assertEqual(u, BEREIT)
        self.assertFalse(fehlt)
        self.assertIn("Warnung: verfallen", grund)

    def test_entwurf_zaehlt_nicht_als_claim_fehlt(self):
        u, grund, fehlt = mit_claim(ENTWURF, "Entwurf", False, "kein Claim",
                                    entwurf=True)
        self.assertEqual(u, ENTWURF)
        self.assertFalse(fehlt)
        self.assertIn("kein Claim", grund)


def _gh_attrappe(zweig=ZWEIG, entwuerfe=()):
    """Gruene, aktuelle PRs (#900, im Bericht auch #901 auf einem fremden
    Zweig) — alles ausser dem Claim ist in Ordnung. ``entwuerfe``: PR-Nummern,
    die als Draft gemeldet werden."""
    def gh_json(*args):
        if args[:2] == ("pr", "list"):
            return [{"number": 900}, {"number": 901}]
        if args[:2] == ("pr", "view"):
            nr = int(args[2])
            return {"headRefOid": "abc123",
                    "headRefName": zweig if nr == 900 else "fix/fremd",
                    "title": "PROC-14 Attrappe", "mergeable": "MERGEABLE",
                    "isDraft": nr in entwuerfe}
        pfad = args[1] if len(args) > 1 else ""
        if pfad.endswith("/check-runs"):
            return {"check_runs": [{"conclusion": "success"}] * 3}
        if "/compare/" in pfad:
            return {"behind_by": 0}
        if "/commits/" in pfad:
            return {"commit": {"committer": {"date": "2026-10-01T08:00:00Z"}}}
        raise AssertionError(f"unerwarteter gh-Aufruf: {args}")
    return gh_json


class MainTest(unittest.TestCase):
    """Der Weg durch ``main()`` — mit Attrappen, nie gegen Tafel oder GitHub."""

    def _lauf(self, argv, tafel=None, tafel_fehler=None, entwuerfe=()):
        def lade():
            if tafel_fehler:
                raise tafel_fehler
            return tafel if tafel is not None else {"claims": []}
        aus = io.StringIO()
        with mock.patch.object(pr_bereit, "_gh_json",
                               _gh_attrappe(entwuerfe=entwuerfe)), \
                mock.patch.object(pr_bereit, "_lade_tafel", lade), \
                mock.patch.object(pr_bereit.session_claim, "jetzt",
                                  lambda: JETZT), \
                contextlib.redirect_stdout(aus):
            code = pr_bereit.main(argv)
        return code, aus.getvalue()

    def test_ohne_claim_exit_1_auch_ohne_strict(self):
        code, aus = self._lauf(["900"])
        self.assertEqual(code, 1)
        self.assertIn(OHNE_CLAIM, aus)

    def test_mit_aktivem_claim_bereit_und_exit_0(self):
        code, aus = self._lauf(["900", "--strict"], tafel={"claims": [_claim()]})
        self.assertEqual(code, 0, aus)
        self.assertIn("1 von 1 bereit", aus)

    def test_verfallener_claim_nur_warnung_exit_0(self):
        # Erst nach dem Merge `release` — ein PR, der 6 h auf CI gewartet hat,
        # ist trotzdem mergebar. Auch mit --strict: er IST bereit.
        alt = _claim(seit=JETZT - timedelta(hours=6))
        code, aus = self._lauf(["900", "--strict"], tafel={"claims": [alt]})
        self.assertEqual(code, 0, aus)
        self.assertIn("1 von 1 bereit", aus)
        self.assertIn("verfallen", aus)
        self.assertIn("refresh", aus)

    def test_bericht_ohne_nummern_ohne_claim_exit_0(self):
        # Der Bericht ueber ALLE offenen PRs zeigt den fehlenden Claim, haelt
        # aber nicht an — dort stehen auch alte PRs und fremde Sitzungen.
        code, aus = self._lauf([], tafel={"claims": [_claim()]})
        self.assertEqual(code, 0, aus)
        self.assertIn(OHNE_CLAIM, aus)
        self.assertIn("#901", aus)

    def test_bericht_mit_strict_ohne_claim_exit_1(self):
        code, aus = self._lauf(["--strict"], tafel={"claims": [_claim()]})
        self.assertEqual(code, 1)
        self.assertIn("Exit 1 (PROC-14)", aus)

    def test_entwurf_ohne_claim_kein_exit_1(self):
        # Ein Draft ist ohnehin nicht bereit; der fehlende Claim zaehlt dort
        # nicht als Regelverstoss — auch nicht bei der Merge-Pruefung.
        code, aus = self._lauf(["900"], entwuerfe=(900,))
        self.assertEqual(code, 0, aus)
        self.assertIn(ENTWURF, aus)
        self.assertNotIn("Exit 1", aus)

    def test_unlesbare_tafel_ist_im_zweifel_rot(self):
        code, aus = self._lauf(["900"], tafel_fehler=RuntimeError("kein git"))
        self.assertEqual(code, 1)
        self.assertIn("Tafel nicht lesbar", aus)

    def test_bewusst_uebersteuert(self):
        code, aus = self._lauf(["900", "--strict", "--ohne-claim",
                                "PR von vor PROC-14"])
        self.assertEqual(code, 0, aus)
        self.assertIn("uebersteuert: PR von vor PROC-14", aus)

    def test_uebersteuern_ohne_begruendung_wird_abgelehnt(self):
        with self.assertRaises(SystemExit) as e, \
                contextlib.redirect_stderr(io.StringIO()):
            self._lauf(["900", "--ohne-claim", "  "])
        self.assertEqual(e.exception.code, 2)

    def test_uebersteuern_ohne_pr_nummern_wird_abgelehnt(self):
        # Keine Pauschalabschaltung fuer alle offenen PRs.
        with self.assertRaises(SystemExit) as e, \
                contextlib.redirect_stderr(io.StringIO()):
            self._lauf(["--ohne-claim", "egal"])
        self.assertEqual(e.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
