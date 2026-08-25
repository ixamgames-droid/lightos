"""Die Entscheidungsregeln von ``tools/backlog_ids.py`` sind festgenagelt.

Der Befund dahinter: zweimal in vier Tagen haben parallel arbeitende Sitzungen
dieselbe Backlog-ID vergeben — am 22.08. zwei Agenten ein ``FM-26``, am 25.08.
**drei** Zweige ein ``FM-30``. Die Mechanik ist beide Male dieselbe: jeder nimmt
die naechste freie Nummer aus dem ``BACKLOG.md``, **das er sieht**.
``test_ids_are_unique`` faengt das erst, wenn zwei davon gelandet sind.

Was hier geprueft wird und was NICHT
------------------------------------
Das Werkzeug braucht Remote-Refs und ``gh`` — in der CI ist beides nicht da
(``actions/checkout@v4`` holt einen Commit ohne weitere Refs). Ein Test, der
dort still ueberspringt, waere die Sorte Absicherung aus PROC-02b/PROC-04.

Die Entscheidung steckt deshalb in reinen Funktionen ohne Git und ohne Netz —
dieser Test misst **sie**, nicht eine Nachbildung des Aufrufs (QA-52).
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))

from backlog_ids import (_PR_LIMIT, items_aus_backlog,  # noqa: E402
                         kollisionen, naechste_freie, zerlege)

KOPF = "| ID | Prio | Status | Titel | Details |\n|---|---|---|---|---|\n"


def tabelle(*zeilen: str) -> str:
    return KOPF + "".join(z + "\n" for z in zeilen)


class ZerlegeTest(unittest.TestCase):
    def test_gewoehnliche_id(self):
        self.assertEqual(zerlege("FM-30"), ("FM", 30, ""))

    def test_mehrstelliges_praefix(self):
        self.assertEqual(zerlege("PROC-02"), ("PROC", 2, ""))

    def test_buchstabe_hinten_ist_eine_verfeinerung_keine_neue_nummer(self):
        # PROC-02c gehoert zu PROC-02. Wer das als eigene Nummer zaehlt,
        # verschenkt Nummern und meldet Kollisionen, wo keine sind.
        self.assertEqual(zerlege("PROC-02c"), ("PROC", 2, "c"))

    def test_id_ohne_zaehler_faellt_heraus(self):
        # Die gibt es wirklich (LAS-HW-VERIFY, QA-LIVE, RIG-DUNKEL) — sie
        # duerfen die Zaehlung nicht durcheinanderbringen.
        for ohne in ("LAS-HW-VERIFY", "QA-LIVE", "RIG-DUNKEL", "TOOL-SMOKEDIM"):
            self.assertIsNone(zerlege(ohne), ohne)


class ItemsAusBacklogTest(unittest.TestCase):
    def test_liest_id_und_titel(self):
        t = tabelle("| FM-30 | P2 | todo | **Ein Titel** | Text |")
        self.assertEqual(items_aus_backlog(t), {"FM-30": "**Ein Titel**"})

    def test_kopfzeile_ist_kein_item(self):
        # `| ID | Prio | …` sieht aus wie ein Item namens "ID". Genau dieser
        # Fehler steckte in backlog_status_drift.py und kostete dort 58
        # Geister-Items — die zweite Spalte muss eine Prioritaet sein.
        self.assertEqual(items_aus_backlog(KOPF), {})

    def test_fliesstext_mit_strichen_ist_kein_item(self):
        self.assertEqual(items_aus_backlog("Ein Satz | mit | Strichen."), {})


class NaechsteFreieTest(unittest.TestCase):
    def test_ueber_ALLE_zweige_nicht_nur_den_eigenen(self):
        # Der Kern der Sache: Zweig A sieht FM-30 nicht und wuerde sie vergeben.
        je_zweig = {
            "origin/main": items_aus_backlog(tabelle("| FM-29 | P2 | done | **A** | x |")),
            "origin/a":    items_aus_backlog(tabelle("| FM-29 | P2 | done | **A** | x |")),
            "origin/b":    items_aus_backlog(tabelle("| FM-29 | P2 | done | **A** | x |",
                                                     "| FM-30 | P3 | todo | **B** | x |")),
        }
        self.assertEqual(naechste_freie(je_zweig, "FM"), 31)

    def test_luecken_werden_NICHT_gefuellt(self):
        """★ Der Punkt, an dem der erste Entwurf falsch lag.

        Luecken entstehen durch archivierte oder zurueckgezogene Items, und
        deren Nummern stehen weiter in Commit-Nachrichten, im CHANGELOG und in
        Code-Kommentaren. Eine Nummer neu zu vergeben, die dort schon eine
        andere Bedeutung hat, waere eine zweite Kollision — nur eine, die kein
        Gate mehr findet, weil beide Eintraege nie gleichzeitig im BACKLOG
        stehen.
        """
        je_zweig = {"origin/main": items_aus_backlog(tabelle(
            "| FM-1 | P1 | done | **A** | x |", "| FM-3 | P1 | done | **C** | x |"))}
        self.assertEqual(naechste_freie(je_zweig, "FM"), 4)

    def test_leere_gruppe_faengt_bei_eins_an(self):
        je_zweig = {"origin/main": items_aus_backlog(tabelle(
            "| QA-9 | P1 | done | **A** | x |"))}
        self.assertEqual(naechste_freie(je_zweig, "FM"), 1)

    def test_fremde_gruppe_stoert_nicht(self):
        je_zweig = {"origin/main": items_aus_backlog(tabelle(
            "| FM-1 | P1 | done | **A** | x |", "| QA-99 | P1 | done | **B** | x |"))}
        self.assertEqual(naechste_freie(je_zweig, "FM"), 2)


class KollisionenTest(unittest.TestCase):
    def _je_zweig(self, main_zeilen, a_zeilen, b_zeilen):
        return {
            "origin/main": items_aus_backlog(tabelle(*main_zeilen)),
            "origin/a": items_aus_backlog(tabelle(*a_zeilen)),
            "origin/b": items_aus_backlog(tabelle(*b_zeilen)),
        }

    def test_zwei_zweige_greifen_nach_derselben_neuen_nummer(self):
        jz = self._je_zweig(
            ["| FM-29 | P2 | done | **Alt** | x |"],
            ["| FM-29 | P2 | done | **Alt** | x |", "| FM-30 | P2 | todo | **Return speichert** | x |"],
            ["| FM-29 | P2 | done | **Alt** | x |", "| FM-30 | P3 | todo | **Block-Regler** | x |"])
        treffer = kollisionen(jz, auf_main=set(jz["origin/main"]))
        self.assertEqual([t[0] for t in treffer], ["FM-30"])
        self.assertEqual(set(treffer[0][1].values()),
                         {"**Return speichert**", "**Block-Regler**"})

    # ── Positivkontrollen: was NICHT gemeldet werden darf ───────────────────
    def test_derselbe_eintrag_auf_zwei_staenden_ist_keine_kollision(self):
        jz = self._je_zweig(
            ["| FM-29 | P2 | done | **Alt** | x |"],
            ["| FM-29 | P2 | done | **Alt** | x |", "| FM-30 | P2 | todo | **Gleich** | x |"],
            ["| FM-29 | P2 | done | **Alt** | x |", "| FM-30 | P2 | review | **Gleich** | x |"])
        self.assertEqual(kollisionen(jz, auf_main=set(jz["origin/main"])), [])

    def test_ein_auf_main_vorhandenes_item_mit_geschaerftem_titel_ist_keine_kollision(self):
        """★ Der Filter, ohne den das Werkzeug unbrauchbar ist.

        Gemessen an UI-52: auf dem eigenen Zweig wurde aus „Die Gruppen-Legende
        zaehlt …" ein „Die Legende zaehlt …". Beide Zweige haben die ID von
        `main` GEERBT — das ist eine Umformulierung, keine doppelte Vergabe.
        Eine echte Kollision ist per Definition NEU.
        """
        jz = self._je_zweig(
            ["| UI-52 | P3 | todo | **Die Gruppen-Legende zaehlt falsch** | x |"],
            ["| UI-52 | P3 | todo | **Die Gruppen-Legende zaehlt falsch** | x |"],
            ["| UI-52 | P3 | review | **Die Legende zaehlt falsch** | x |"])
        self.assertEqual(kollisionen(jz, auf_main=set(jz["origin/main"])), [])

    def test_ohne_den_main_filter_WAERE_es_eine_kollision(self):
        # Die Gegenprobe zum Test darueber: derselbe Fall, aber die ID gilt als
        # neu. Ohne sie waere nicht zu sehen, dass der Filter ueberhaupt wirkt.
        jz = self._je_zweig(
            ["| UI-52 | P3 | todo | **Die Gruppen-Legende zaehlt falsch** | x |"],
            ["| UI-52 | P3 | todo | **Die Gruppen-Legende zaehlt falsch** | x |"],
            ["| UI-52 | P3 | review | **Die Legende zaehlt falsch** | x |"])
        self.assertEqual([t[0] for t in kollisionen(jz, auf_main=set())], ["UI-52"])

    def test_ein_einziger_zweig_meldet_nie(self):
        jz = {"origin/main": items_aus_backlog(tabelle("| FM-30 | P2 | todo | **A** | x |"))}
        self.assertEqual(kollisionen(jz, auf_main=set()), [])


class FailClosedTest(unittest.TestCase):
    """★ CDX-57 (zweite Codex-Runde): eine Warnung allein genuegt nicht.

    Die erste Fassung meldete Luecken in der Abdeckung — und gab trotzdem eine
    Nummer aus und beendete mit 0. Wer den Exit-Code prueft, bekam gruenes Licht
    auf unvollstaendigen Daten und legt genau die Kollision an, gegen die es
    dieses Werkzeug gibt.

    Gemessen wird ueber ``main()``, nicht ueber eine innere Funktion: der
    Exit-Code IST hier die Aussage.
    """

    def _main_mit(self, zweige, warnung):
        import backlog_ids as bi
        orig = bi.offene_pr_zweige
        bi.offene_pr_zweige = lambda: (zweige, warnung)
        try:
            return bi.main(["--gruppe", "FM", "--kein-fetch"])
        finally:
            bi.offene_pr_zweige = orig

    def test_ein_unlesbarer_ref_verhindert_die_auskunft(self):
        self.assertEqual(self._main_mit(["gibt-es-garantiert-nicht"], None), 2)

    def test_eine_warnung_aus_gh_verhindert_die_auskunft(self):
        self.assertEqual(self._main_mit([], "`gh pr list` fehlgeschlagen: …"), 2)

    def test_ohne_luecke_gibt_es_die_auskunft(self):
        # Positivkontrolle: sonst waere das Werkzeug nie zu gebrauchen.
        self.assertEqual(self._main_mit([], None), 0)


class AbdeckungTest(unittest.TestCase):
    """★ CDX-57: das Werkzeug darf nie weniger liefern, als sein Name verspricht.

    Codex hat drei Wege gefunden, auf denen die erste Fassung stillschweigend
    unvollstaendig wurde: ein `--limit`, das hart abschneidet; ein
    fehlgeschlagenes `git fetch`, dessen Rueckgabewert verworfen wurde; und
    Fork-PRs, deren Kopf es als `origin/<branch>` gar nicht gibt. Alle drei
    enden im selben Schaden — eine Nummer wird als frei gemeldet, die es nicht
    ist.
    """

    def test_das_pr_limit_liegt_weit_ueber_dem_realistischen_bestand(self):
        # Kein Ersatz fuer echtes Blaettern, aber der Wert darf nicht in der
        # Naehe dessen liegen, was das Repo je offen hat. Ueberschreitet die
        # Zahl der PRs ihn doch, meldet das Werkzeug eine Warnung statt einer
        # kuerzeren Liste — das ist der eigentliche Schutz.
        self.assertGreaterEqual(_PR_LIMIT, 200)


if __name__ == "__main__":
    unittest.main()
