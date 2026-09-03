"""PROC-10: "keine Checks" darf nicht wie "alle gruen" aussehen.

**Der Vorfall (2026-09-03, Sitzung B).** Ein PR ist gemergt worden, ohne dass CI
gelaufen war. ``gh pr checks --watch`` beendete sich mit **Exit 0** — nicht weil
die Checks gruen waren, sondern weil es zu dem Zeitpunkt **gar keine** gab: der
Lauf war zehn Sekunden alt und stand in der Warteschlange. Der Exit-Code heisst
also zweierlei, und genau diese Zweideutigkeit hebelt PROC-03 aus.

★ **Der Zustand ist hier der Normalfall, nicht die Ausnahme:** an genau diesem
Tag hat GitHub **dreimal** fuer einen frischen PR verzoegert oder gar keinen Lauf
angelegt — zweimal bei Sitzung A (#705, #706), einmal bei B (#688).

⚠️ **Warum ein Werkzeug und kein weiterer Absatz:** PROC-03 („kein Merge ohne
CI") stand laengst da und wurde trotzdem verletzt, weil das Werkzeug die
Unterscheidung nicht anbot. Eine Regel im Fliesstext hat an dieser Stelle
nachweislich nicht getragen.

Geprueft wird die **reine** Bewertung: mit einem echten PR liesse sich der Fall
"leere Liste" nicht auf Bestellung herstellen, und genau er ist der gefaehrliche.
"""
from __future__ import annotations

import unittest

from tools.pr_ci_status import bewerte


def _check(name="CI", status="COMPLETED", conclusion="SUCCESS"):
    return {"name": name, "status": status, "conclusion": conclusion}


class BewertungTest(unittest.TestCase):

    def test_keine_checks_ist_NICHT_gruen(self):
        """★★ Der Fall, der den Vorfall ausgeloest hat."""
        gruen, grund = bewerte([])
        self.assertFalse(gruen, grund)
        self.assertIn("KEINE Checks", grund)
        self.assertIn("PROC-10", grund)

    def test_keine_checks_nennt_die_abhilfe(self):
        """Rot allein hilft um drei Uhr nachts nicht weiter.

        Die Abhilfe ist gemessen, nicht geraten: Sitzung A hat sie am 03.09.
        zweimal erfolgreich gefahren — `main` IN den Zweig mergen erzeugt frische
        SHAs und laesst sich ohne Force-Push pushen.
        """
        _gruen, grund = bewerte([])
        self.assertIn("main", grund)
        self.assertIn("Force-Push", grund)

    def test_alle_erfolgreich_ist_gruen(self):
        gruen, grund = bewerte([_check("Linux"), _check("Windows 3.11")])
        self.assertTrue(gruen, grund)
        self.assertIn("2 Check(s)", grund)

    def test_ein_laufender_check_ist_nicht_gruen(self):
        """Der eigentliche Zeitpunkt-Fehler: der Lauf hatte noch nicht begonnen."""
        gruen, grund = bewerte([_check("Linux"),
                                _check("Windows", status="IN_PROGRESS", conclusion="")])
        self.assertFalse(gruen, grund)
        self.assertIn("Noch nicht fertig", grund)
        self.assertIn("Windows", grund)

    def test_ein_wartender_check_ist_nicht_gruen(self):
        gruen, grund = bewerte([_check("Linux", status="QUEUED", conclusion="")])
        self.assertFalse(gruen, grund)
        self.assertIn("Noch nicht fertig", grund)

    def test_ein_fehlschlag_ist_nicht_gruen(self):
        gruen, grund = bewerte([_check("Linux", conclusion="FAILURE"),
                                _check("Windows")])
        self.assertFalse(gruen, grund)
        self.assertIn("Fehlgeschlagen", grund)
        self.assertIn("Linux", grund)

    def test_uebersprungene_und_neutrale_checks_zaehlen_nicht_als_fehler(self):
        """★ Gegenprobe zur Absicht.

        Ohne sie koennte die Pruefung pauschal rot faerben und alle Tests oben
        blieben gruen — aus dem Schutz gegen ungeprueftes Mergen waere dann ein
        Werkzeug geworden, das nie etwas durchlaesst und deshalb umgangen wird.
        """
        gruen, grund = bewerte([_check("Linux"),
                                _check("Optional", conclusion="SKIPPED"),
                                _check("Info", conclusion="NEUTRAL")])
        self.assertTrue(gruen, grund)

    def test_unbekanntes_ergebnis_ist_im_zweifel_rot(self):
        """QA-53-Regel: wer nicht weiss, ob es gut ging, hat kein Gruen."""
        gruen, grund = bewerte([_check("Seltsam", conclusion="STALE")])
        self.assertFalse(gruen, grund)
        self.assertIn("Fehlgeschlagen", grund)

    def test_abgeschlossen_ohne_ergebnis_ist_nicht_gruen(self):
        gruen, grund = bewerte([_check("Ohne", conclusion="")])
        self.assertFalse(gruen, grund)
        self.assertIn("Unklares Ergebnis", grund)

    def test_kein_rollup_ist_nicht_gruen(self):
        """``gh`` kann ``null`` liefern — das ist keine Auskunft, also kein Gruen."""
        gruen, grund = bewerte(None)
        self.assertFalse(gruen, grund)
        self.assertIn("unbekannt", grund.lower())


class WorkflowNenntDasWerkzeugTest(unittest.TestCase):
    """Ein Werkzeug, das niemand kennt, ersetzt keine Regel.

    PROC-10 entstand daraus, dass die Regel allein nicht trug. Sie jetzt durch
    ein Werkzeug zu ersetzen, das nirgends steht, waere derselbe Fehler mit
    vertauschten Rollen.
    """

    def test_workflow_md_verweist_auf_das_werkzeug(self):
        import os
        wurzel = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(wurzel, "WORKFLOW.md"), encoding="utf-8") as f:
            text = f.read()
        self.assertIn("pr_ci_status.py", text,
                      "WORKFLOW.md nennt das Werkzeug nicht — dann findet es "
                      "niemand, und die Luecke aus PROC-10 bleibt offen")


if __name__ == "__main__":
    unittest.main()
