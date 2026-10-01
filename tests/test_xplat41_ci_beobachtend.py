"""XPLAT-41 — beobachtende CI-Legs blockieren die Merge-Werkzeuge nicht.

``continue-on-error: true`` auf Job-Ebene haelt nur den Workflow-Status gruen.
Der Check-Run des Jobs endet bei einem Fehlschlag trotzdem mit
``conclusion=failure`` und steht bis zum Ende (bis ``timeout-minutes``) als
laufend am PR. ``tools/pr_bereit.py`` und ``tools/pr_ci_status.py`` werten jeden
Check-Run einzeln — ohne Ausnahme blockierte die „nur beobachtende"
Windows-ARM64-Leg also doch jeden Merge.

Die Ausnahme steht an EINER Stelle: ``tools/_ci_beobachtend.BEOBACHTEND``.
Der Waechter unten haelt sie an der echten ``ci.yml`` fest: jeder Name muss
genau das ``name:`` eines Jobs mit ``continue-on-error: true`` sein. Sonst
wuerde ein umbenannter Job still blockieren — oder, schlimmer, ein scharf
geschalteter Job still ignoriert.
"""
import os
import sys
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "tools"))
sys.path.insert(0, os.path.join(REPO, "tests"))

import _ci_beobachtend  # noqa: E402
from pr_bereit import BEREIT, ROT, UNFERTIG, teile_checks, urteil  # noqa: E402
from pr_ci_status import bewerte  # noqa: E402
from test_ci_windows_legs import _ci_text, ci_jobs, job_schluessel  # noqa: E402

ARM = "Windows-ARM64 — volle Suite (segmentiert, beobachtend)"
PFLICHT = ("Linux — volle Suite (segmentiert)", "Windows-Smoke (Python 3.12)")


def _run(name, status="completed", conclusion="success"):
    """Eintrag wie aus ``repos/.../check-runs`` (kleingeschrieben)."""
    return {"name": name, "status": status, "conclusion": conclusion}


def _rollup(name, status="COMPLETED", conclusion="SUCCESS"):
    """Eintrag wie aus ``gh pr view --json statusCheckRollup``."""
    return {"name": name, "status": status, "conclusion": conclusion}


class ListeGegenCiYmlTest(unittest.TestCase):
    """Der Waechter: die Liste trifft echte, beobachtende Jobs."""

    def setUp(self):
        self.jobs = ci_jobs(_ci_text())
        self.assertTrue(self.jobs, "keine Jobs in ci.yml gelesen")

    def test_liste_ist_nicht_leer(self):
        self.assertTrue(_ci_beobachtend.BEOBACHTEND)

    def test_jeder_name_ist_ein_job_mit_continue_on_error(self):
        namen = {job_schluessel(z, "name"): (k, z) for k, z in self.jobs.items()}
        for name in _ci_beobachtend.BEOBACHTEND:
            with self.subTest(name=name):
                self.assertIn(name, namen,
                              f"kein Job in ci.yml heisst '{name}' — umbenannt? "
                              "Dann blockiert die Leg still jeden Merge")
                key, zeilen = namen[name]
                self.assertEqual(job_schluessel(zeilen, "continue-on-error"), "true",
                                 f"Job '{key}' ist scharf geschaltet — dann aus "
                                 "_ci_beobachtend.BEOBACHTEND nehmen, sonst wird "
                                 "ein blockierender Job ignoriert")
                # Mit Matrix haengt GitHub Werte an den Anzeigenamen — der
                # Eintrag traefe dann keinen Check-Run mehr.
                self.assertFalse(any(z.strip().startswith("strategy:") for z in zeilen),
                                 f"Job '{key}' hat eine Matrix")
                self.assertNotIn("${{", name)

    def test_der_arm_job_ist_gelistet(self):
        self.assertEqual(job_schluessel(self.jobs["windows-arm"], "name"), ARM)
        self.assertTrue(_ci_beobachtend.ist_beobachtend(ARM))


class PrBereitTest(unittest.TestCase):

    def _urteil(self, runs):
        pflicht, beobachtet = teile_checks(runs)
        return urteil(len(pflicht), [c["conclusion"] for c in pflicht], 0,
                      "MERGEABLE", beobachtet=beobachtet)

    def test_roter_arm_check_bei_gruenen_pflicht_checks_ist_bereit(self):
        u, grund = self._urteil([_run(n) for n in PFLICHT]
                                + [_run(ARM, conclusion="failure")])
        self.assertEqual(u, BEREIT, grund)
        self.assertIn("beobachtend", grund)
        self.assertIn("Windows-ARM64 rot", grund)
        self.assertIn("2 Checks gruen", grund)

    def test_laufender_arm_check_ist_nicht_laeuft_noch(self):
        u, grund = self._urteil([_run(n) for n in PFLICHT]
                                + [_run(ARM, status="in_progress", conclusion=None)])
        self.assertEqual(u, BEREIT, grund)
        self.assertIn("Windows-ARM64 laeuft noch", grund)

    def test_roter_pflicht_check_bleibt_rot(self):
        u, grund = self._urteil([_run(PFLICHT[0], conclusion="failure"),
                                 _run(PFLICHT[1]), _run(ARM)])
        self.assertEqual(u, ROT, grund)
        self.assertIn("Windows-ARM64 gruen", grund)

    def test_laufender_pflicht_check_bleibt_unfertig(self):
        u, _ = self._urteil([_run(PFLICHT[0], status="queued", conclusion=None),
                             _run(PFLICHT[1]), _run(ARM, conclusion="failure")])
        self.assertEqual(u, UNFERTIG)

    def test_nur_der_arm_check_ist_nicht_bereit(self):
        u, _ = self._urteil([_run(ARM)])
        self.assertNotEqual(u, BEREIT)

    def test_ohne_beobachtete_bleibt_die_begruendung_wie_bisher(self):
        _, grund = urteil(2, ["success", "success"], 0, "MERGEABLE")
        self.assertNotIn("beobachtend", grund)


class PrCiStatusTest(unittest.TestCase):

    def test_roter_arm_check_bei_gruenen_pflicht_checks_ist_gruen(self):
        gruen, grund = bewerte([_rollup(n) for n in PFLICHT]
                               + [_rollup(ARM, conclusion="FAILURE")])
        self.assertTrue(gruen, grund)
        self.assertIn("Windows-ARM64 rot", grund)

    def test_laufender_arm_check_ist_gruen_mit_hinweis(self):
        gruen, grund = bewerte([_rollup(n) for n in PFLICHT]
                               + [_rollup(ARM, status="IN_PROGRESS", conclusion=None)])
        self.assertTrue(gruen, grund)
        self.assertIn("Windows-ARM64 laeuft noch", grund)

    def test_roter_pflicht_check_bleibt_fehlgeschlagen(self):
        gruen, grund = bewerte([_rollup(PFLICHT[0], conclusion="FAILURE"),
                                _rollup(PFLICHT[1]), _rollup(ARM)])
        self.assertFalse(gruen)
        self.assertIn("Fehlgeschlagen", grund)
        self.assertNotIn(ARM, grund.split("\n")[0])

    def test_nur_der_arm_check_ist_nicht_gruen(self):
        gruen, grund = bewerte([_rollup(ARM)])
        self.assertFalse(gruen, grund)
        self.assertIn("PROC-10", grund)


if __name__ == "__main__":
    unittest.main()
