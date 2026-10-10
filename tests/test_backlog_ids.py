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

    def test_alt_pr_mit_zeile_und_fragment_pr_gleicher_titel_keine_kollision(self):
        # Codex zu PROC-20: die Tabelle schreibt den Titel fett (**A**), das
        # Fragment traegt ihn nackt. Dieselbe ID mit demselben Titel in einem
        # Alt-PR (BACKLOG-Zeile) und einem Fragment-PR ist EIN Eintrag auf zwei
        # Staenden — sonst endet --strict mit Exit 1 ohne echte Kollision.
        import backlog_ids as B
        frag = "ID: UI-99\nPrioritaet: P2\nStatus: review\nTitel: {}\n\nText.\n"
        main_ = items_aus_backlog(tabelle("| UI-1 | P2 | done | **Alt** | x |"))
        alt_pr = items_aus_backlog(tabelle(
            "| UI-1 | P2 | done | **Alt** | x |",
            "| UI-99 | P2 | review | **Neuer Knopf** | x |"))
        for titel in ("Neuer Knopf", "**Neuer Knopf**"):
            jz = {"origin/main": main_, "origin/alt": alt_pr,
                  "origin/neu": B.mit_fragmenten(
                      main_, {"backlog.d/UI-99.md": frag.format(titel)})}
            self.assertEqual(kollisionen(jz, auf_main=set(main_)), [], titel)
        # Gegenprobe: ein ANDERER Titel bleibt eine Kollision, und die Meldung
        # zeigt die Titel so, wie sie im Zweig stehen.
        jz["origin/neu"] = B.mit_fragmenten(
            main_, {"backlog.d/UI-99.md": frag.format("Anderer Knopf")})
        treffer = kollisionen(jz, auf_main=set(main_))
        self.assertEqual([t[0] for t in treffer], ["UI-99"])
        self.assertEqual(treffer[0][1]["origin/alt"], "**Neuer Knopf**")


class FailClosedTest(unittest.TestCase):
    """★ CDX-57 (zweite Codex-Runde): eine Warnung allein genuegt nicht.

    Die erste Fassung meldete Luecken in der Abdeckung — und gab trotzdem eine
    Nummer aus und beendete mit 0. Wer den Exit-Code prueft, bekam gruenes Licht
    auf unvollstaendigen Daten und legt genau die Kollision an, gegen die es
    dieses Werkzeug gibt.

    Gemessen wird ueber ``main()``, nicht ueber eine innere Funktion: der
    Exit-Code IST hier die Aussage.
    """

    # ★ Die CI hat diesen Test beim ersten Anlauf gekippt, und sie hatte recht:
    # `main()` liest `origin/main` ueber git, und `actions/checkout@v4` holt
    # EINEN Commit ohne weitere Refs. Der Positivkontroll-Fall lief dort also in
    # dieselbe Luecke, die er ausschliessen soll — Ergebnis `2 != 0`.
    #
    # Genau deshalb ist der Griff nach git hier zugehalten: gemessen wird die
    # ENTSCHEIDUNG von `main()` (Exit-Code, Auskunft ja/nein), nicht die
    # Faehigkeit der Umgebung, Refs zu liefern. Das ist derselbe Zuschnitt, den
    # der Gegenpruefer an #668 vorgemacht hat.
    _BACKLOG = ("| ID | Prio | Status | Titel | Details |\n|---|---|---|---|---|\n"
                "| FM-29 | P2 | done | **Alt** | x |\n")

    def _main_mit(self, zweige, warnung, refs_lesbar=True):
        import backlog_ids as bi
        orig_pr, orig_je = bi.offene_pr_zweige, bi.backlog_je_zweig
        bi.offene_pr_zweige = lambda: (zweige, warnung)
        bi.backlog_je_zweig = lambda refs: (
            {r: bi.items_aus_backlog(self._BACKLOG) for r in refs}
            if refs_lesbar else {"origin/main": bi.items_aus_backlog(self._BACKLOG)})
        try:
            return bi.main(["--gruppe", "FM", "--kein-fetch"])
        finally:
            bi.offene_pr_zweige, bi.backlog_je_zweig = orig_pr, orig_je

    def test_ein_unlesbarer_ref_verhindert_die_auskunft(self):
        self.assertEqual(
            self._main_mit(["gibt-es-garantiert-nicht"], None, refs_lesbar=False), 2)

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


class TafelUndFragmenteTest(unittest.TestCase):
    """TOOL-9: Nummern, die nur auf der Tafel oder in einem Changelog-Fragment
    stehen, gelten als vergeben (02.10.: Tafel hatte DOC-23..50, das Werkzeug
    bot DOC-22 an, die A schon gemergt hatte)."""

    def test_ids_aus_tafeltext(self):
        import backlog_ids as B
        text = ("DOC-43           C    -   seit 2026-10-02\n"
                "  - (C) C AN A — Stand: NEU #869 DOC-23, FM-33 fertig")
        self.assertEqual(B.ids_aus_text(text), {"DOC-43", "DOC-23", "FM-33"})

    def test_ids_aus_fragment_dateinamen(self):
        import backlog_ids as B
        self.assertEqual(B.ids_aus_text("2026-10-02-DOC-22.md\nREADME.md\n"),
                         {"DOC-22"})

    def test_belegte_ids_heben_die_naechste_freie(self):
        nur_backlog = {"origin/main": {"DOC-21": "x"}}
        self.assertEqual(naechste_freie(nur_backlog, "DOC"), 22)
        mit_tafel = {**nur_backlog,
                     "(Tafel/Fragmente)": dict.fromkeys({"DOC-22", "DOC-50"}, "")}
        self.assertEqual(naechste_freie(mit_tafel, "DOC"), 51)

    def test_main_nutzt_die_weiteren_quellen(self):
        import backlog_ids as B
        orig = (B._git, B.offene_pr_zweige)
        tabelle_main = tabelle("| DOC-21 | P3 | todo | **T** | d |")

        def git(*args):
            if args[:1] == ("show",) and args[1].endswith(":BACKLOG.md"):
                return 0, tabelle_main
            if args[:1] == ("show",) and "SESSIONS.md" in args[1]:
                return 0, "DOC-43  C  -  seit 2026-10-02"
            if args[:1] == ("ls-tree",):
                return 0, "2026-10-02-DOC-22.md\n"
            return 0, ""
        B._git = git
        B.offene_pr_zweige = lambda: ([], None)
        try:
            import io
            from contextlib import redirect_stdout
            buf = io.StringIO()
            with redirect_stdout(buf):
                B.main(["--gruppe", "DOC", "--kein-fetch"])
        finally:
            B._git, B.offene_pr_zweige = orig
        self.assertIn("DOC-44", buf.getvalue())


class BacklogFragmenteTest(unittest.TestCase):
    """PROC-20: ein Item, das nur als ``backlog.d/<ID>.md`` existiert, ist
    vergeben — fuer die naechste freie Nummer UND fuer die Kollisionspruefung.
    Seit kein PR mehr BACKLOG.md anfasst, stehen neue IDs NUR dort; ohne diese
    Quelle boete das Werkzeug jede frisch vergebene Nummer noch einmal an."""

    FRAG = "ID: FM-31\nPrioritaet: P2\nStatus: todo\nTitel: {}\n\nText.\n"

    def test_fragment_liefert_id_und_titel(self):
        import backlog_ids as B
        self.assertEqual(
            B.items_aus_fragmenten({"FM-31.md": self.FRAG.format("Return speichert"),
                                    "README.md": "# Erklaerung FM-99\n"}),
            {"FM-31": "Return speichert"})

    def test_status_fragment_ohne_titel_traegt_keinen_titel_bei(self):
        # Ein reines Status-Fragment gehoert zu einer vorhandenen Zeile; ein
        # leerer Titel saehe sonst wie ein ABWEICHENDER Titel aus.
        import backlog_ids as B
        self.assertEqual(B.items_aus_fragmenten({"FM-29.md": "ID: FM-29\nStatus: done\n"}), {})

    def test_die_backlog_zeile_gewinnt_gegen_das_fragment(self):
        import backlog_ids as B
        zeilen = items_aus_backlog(tabelle("| FM-31 | P2 | todo | **Aus der Tabelle** | x |"))
        self.assertEqual(
            B.mit_fragmenten(zeilen, {"FM-31.md": self.FRAG.format("Aus dem Fragment")}),
            {"FM-31": "**Aus der Tabelle**"})

    def test_fragment_hebt_die_naechste_freie(self):
        import backlog_ids as B
        main_ = items_aus_backlog(tabelle("| FM-30 | P2 | done | **A** | x |"))
        jz = {"origin/main": main_,
              "origin/a": B.mit_fragmenten(main_, {"FM-31.md": self.FRAG.format("Neu")})}
        self.assertEqual(naechste_freie({"origin/main": main_}, "FM"), 31)
        self.assertEqual(naechste_freie(jz, "FM"), 32)

    def test_zwei_zweige_mit_demselben_neuen_fragment_kollidieren(self):
        import backlog_ids as B
        main_ = items_aus_backlog(tabelle("| FM-30 | P2 | done | **A** | x |"))
        jz = {"origin/main": main_,
              "origin/a": B.mit_fragmenten(main_, {"FM-31.md": self.FRAG.format("Return")}),
              "origin/b": B.mit_fragmenten(main_, {"FM-31.md": self.FRAG.format("Regler")})}
        self.assertEqual([t[0] for t in kollisionen(jz, auf_main=set(main_))], ["FM-31"])
        # Positivkontrolle: derselbe Titel auf beiden Zweigen ist derselbe Eintrag.
        jz["origin/b"] = jz["origin/a"]
        self.assertEqual(kollisionen(jz, auf_main=set(main_)), [])

    def test_fragment_gegen_tabellenzeile_eines_alten_pr_kollidiert(self):
        # Uebergang: Zweig a traegt die ID noch direkt in BACKLOG.md ein,
        # Zweig b legt fuer ein ANDERES Item dieselbe ID als Fragment an.
        import backlog_ids as B
        main_ = items_aus_backlog(tabelle("| FM-30 | P2 | done | **A** | x |"))
        jz = {"origin/main": main_,
              "origin/a": items_aus_backlog(tabelle("| FM-31 | P2 | todo | **Return** | x |")),
              "origin/b": B.mit_fragmenten(main_, {"FM-31.md": self.FRAG.format("Regler")})}
        self.assertEqual([t[0] for t in kollisionen(jz, auf_main=set(main_))], ["FM-31"])

    def _main(self, fragmente: dict, argv):
        """``main()`` mit zugehaltenem git; ``fragmente`` = {Ref: {Name: Text}}."""
        import backlog_ids as B
        orig = (B._git, B.offene_pr_zweige)
        tabelle_main = tabelle("| DOC-21 | P3 | todo | **T** | d |")

        def git(*args):
            if args[:1] == ("show",) and args[1].endswith(":BACKLOG.md"):
                return 0, tabelle_main
            for ref, dateien in fragmente.items():
                if args[:1] == ("ls-tree",) and args[-1] == f"{ref}:backlog.d":
                    return 0, "".join(n + "\n" for n in dateien) + "README.md\n"
                for name, text in dateien.items():
                    if args == ("show", f"{ref}:backlog.d/{name}"):
                        return 0, text
            if args[:1] in (("show",), ("ls-tree",)):
                return 1, ""
            return 0, ""
        B._git = git
        B.offene_pr_zweige = lambda: (["a", "b"], None)
        try:
            import io
            from contextlib import redirect_stdout
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = B.main(list(argv) + ["--kein-fetch"])
        finally:
            B._git, B.offene_pr_zweige = orig
        return rc, buf.getvalue()

    _DOC22 = "ID: DOC-22\nPrioritaet: P3\nStatus: review\nTitel: {}\n"

    def test_main_zaehlt_fragmente_fuer_die_naechste_freie(self):
        """Ueber ``main()`` gemessen: die Auskunft selbst muss die Fragmente sehen."""
        rc, aus = self._main({"origin/a": {"DOC-22.md": self._DOC22.format("Neu")}},
                             ["--gruppe", "DOC"])
        self.assertEqual(rc, 0, aus)
        self.assertIn("DOC-23", aus)

    def test_main_zaehlt_auch_ein_fragment_ohne_titel(self):
        # Kein Titel = kein Beitrag zur Kollisionspruefung, aber die NUMMER
        # ist vergeben (Dateiname genuegt).
        rc, aus = self._main({"origin/a": {"DOC-30.md": "ID: DOC-30\nStatus: todo\n"}},
                             ["--gruppe", "DOC"])
        self.assertEqual(rc, 0, aus)
        self.assertIn("DOC-31", aus)

    def test_main_meldet_die_kollision_zweier_fragmente(self):
        rc, aus = self._main({"origin/a": {"DOC-22.md": self._DOC22.format("Eins")},
                              "origin/b": {"DOC-22.md": self._DOC22.format("Zwei")}},
                             ["--strict"])
        self.assertEqual(rc, 1, aus)
        self.assertIn("DOC-22", aus)

    def test_main_meldet_denselben_titel_nicht(self):
        rc, aus = self._main({"origin/a": {"DOC-22.md": self._DOC22.format("Eins")},
                              "origin/b": {"DOC-22.md": self._DOC22.format("Eins")}},
                             ["--strict"])
        self.assertEqual(rc, 0, aus)

    def test_main_meldet_ein_fragment_das_auf_main_liegt_nicht(self):
        # Nach dem Merge, vor dem Sammeln: die ID ist geerbt, keine Kollision.
        rc, aus = self._main({"origin/main": {"DOC-22.md": self._DOC22.format("Eins")},
                              "origin/b": {"DOC-22.md": self._DOC22.format("Eins, geschaerft")}},
                             ["--strict"])
        self.assertEqual(rc, 0, aus)


if __name__ == "__main__":
    unittest.main()
