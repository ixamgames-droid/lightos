"""PRIV-01 — Waechter: keine privaten Laufzeitdaten im OEFFENTLICHEN Repo.

★ Am 2026-08-05 kam mit PR #593 eine **echte Show-Datenbank** ins Repo:
`data/_backup/current_show.db.20260805-202753` — 30 gepatchte Geraete,
8 Fixture-Gruppen, also der komplette Aufbau eines realen Rigs. Im selben
Commit `data/universes.json.bak-201618`, die Sicherung der
Ausgabe-Konfiguration. Beide lagen oeffentlich einsehbar auf GitHub.

**Warum `.gitignore` das nicht verhindert hat:** die Regeln waren
`data/*.db` und `data/*.json` — eine Ebene tief, exakte Endung. Beide Dateien
umgehen das muehelos, die eine ueber einen Unterordner **und** einen Zeitstempel
hinter der Endung, die andere ueber ein `.bak-`-Suffix. Es brauchte keinen
Vorsatz, nur ein `git add data/`.

**Warum eine Ignore-Regel allein trotzdem nicht reicht:** sie schuetzt vor
Unachtsamkeit, nicht vor einem `git add -f` — und schon gar nicht vor einer
Datei, die bereits getrackt ist (dann ist `.gitignore` wirkungslos). Deshalb
prueft dieses Gate den **Tracking-Zustand selbst**: was `git ls-files` zeigt,
ist genau das, was auf GitHub landet.

Die Regel ist eine **Positivliste**, keine Musterjagd. „Alles verboten ausser
dem, was ausdruecklich mitgeliefert wird" faengt auch die naechste Variante,
an die heute niemand denkt — die vorherige Regel scheiterte ja gerade daran,
dass sie Muster aufzaehlte.
"""
import os
import subprocess
import unittest

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _getrackte_dateien() -> list[str]:
    """Alle von git verwalteten Pfade — also alles, was oeffentlich ist."""
    r = subprocess.run(["git", "ls-files", "-z"], cwd=_REPO,
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        return []
    return [p for p in r.stdout.split("\0") if p]


def _ist_erlaubt(pfad: str) -> bool:
    """Positivliste fuer `data/` und `shows/` — alles andere ist Nutzerdatei."""
    if pfad.startswith("data/"):
        rest = pfad[len("data/"):]
        # Mitgelieferte Controller-Bibliothek + Beschreibungen.
        if rest.startswith("controller_library/"):
            return True
        return rest.lower() in ("readme.md", ".gitkeep")
    if pfad.startswith("shows/"):
        rest = pfad[len("shows/"):]
        if rest in (".gitkeep",) or rest.lower() == "readme.md":
            return True
        # Versionierte Demo-Shows: Konvention „demo" im Dateinamen, und nur
        # .lshow — eine .json daneben ist eine Nebendatei aus dem Betrieb
        # (so kam `vc show 1.json` herein).
        return rest.lower().endswith(".lshow") and "demo" in rest.lower()
    return True


class KeinePrivatenLaufzeitdatenTest(unittest.TestCase):

    def setUp(self):
        self.dateien = _getrackte_dateien()
        if not self.dateien:
            self.skipTest("kein git-Checkout (Tarball/Sandbox) — nichts zu pruefen")

    def test_data_und_shows_enthalten_nur_mitgeliefertes(self):
        verstoesse = [p for p in self.dateien
                      if (p.startswith(("data/", "shows/")) and not _ist_erlaubt(p))]
        self.assertEqual(
            verstoesse, [],
            "Private Laufzeitdaten sind im OEFFENTLICHEN Repo getrackt.\n"
            "Erlaubt sind nur data/controller_library/** und Demo-Shows.\n"
            "Entfernen mit:  git rm --cached <datei>   (die Datei bleibt lokal "
            "liegen)\nund danach pruefen, ob eine .gitignore-Regel fehlt.")

    def test_keine_datenbanken_oder_sicherungen_irgendwo(self):
        """Auch ausserhalb von `data/` — eine Show-DB ist ueberall privat.

        Bewusst auf `in`-Pruefung statt Endungs-Pruefung: die gefundene Datei
        hiess `current_show.db.20260805-202753`, die Endung war also gar nicht
        mehr `.db`. Genau daran ist die alte Regel gescheitert.
        """
        verdaechtig = []
        for p in self.dateien:
            name = os.path.basename(p).lower()
            if ".db" in name and not name.endswith((".dbf", ".dbg")):
                verdaechtig.append(p)
            elif ".bak" in name or name.endswith((".lshow.layout.json",)):
                verdaechtig.append(p)
        self.assertEqual(
            verdaechtig, [],
            "Datenbank- oder Sicherungsdateien sind getrackt — das sind "
            "Nutzerdaten, kein Quellcode.")

    def test_der_waechter_wuerde_den_echten_fall_fangen(self):
        """Positivkontrolle: sonst koennte dieser Test stumm gruen bleiben.

        Ein Gate, das nur „nichts gefunden" sagen kann, ist von einem kaputten
        Gate nicht zu unterscheiden. Hier laufen die beiden Dateien aus dem
        echten Vorfall gegen dieselbe Regel.
        """
        self.assertFalse(_ist_erlaubt("data/_backup/current_show.db.20260805-202753"))
        self.assertFalse(_ist_erlaubt("data/universes.json.bak-201618"))
        self.assertFalse(_ist_erlaubt("data/midi_mappings.json"))
        self.assertFalse(_ist_erlaubt("shows/vc show 1.json"))
        # ...und das Mitgelieferte bleibt erlaubt.
        self.assertTrue(_ist_erlaubt("data/controller_library/akai_apc_mini.json"))
        self.assertTrue(_ist_erlaubt("shows/demo_rgb_par.lshow"))
        self.assertTrue(_ist_erlaubt("shows/APC_Demo_Show.lshow"))
        self.assertTrue(_ist_erlaubt("src/core/app_state.py"))


class KeineFremdenBenutzerpfadeTest(unittest.TestCase):
    """PRIV-02: kein Klar-Benutzername in Pfaden des oeffentlichen Repos.

    Kein Datenleak wie die Show-DB, aber unnoetig: `/home/<name>/…` in einem
    Testdatensatz verraet den Kontonamen des Entwicklungsrechners, ohne dass
    der Test dadurch irgendetwas besser prueft. Anonyme Platzhalter
    (`/home/user/`, `C:\\Users\\X\\`) leisten dasselbe — die Windows-Tests
    machen es laengst so.
    """

    # Bewusst nur Quell-, Test- und Werkzeugdateien: BACKLOG/CHANGELOG sind
    # Protokolle und werden nicht rueckwirkend umgeschrieben.
    ORDNER = ("src", "tests", "tools", "docs")

    # PRIV-04: BEIDE Formen. Die Linux-Form stand hier seit jeher allein — und
    # der Waechter war gruen, WEIL nur sie geprueft wurde und nur sie bereits
    # aufgeraeumt war. Gemessen am 2026-09-03 ueber dieselben Ordner:
    # `/home/<name>/` 0 Treffer, `C:\Users\<name>\` **14**. Ein Waechter, der
    # die Haelfte seiner eigenen Regel nicht ansieht, misst nichts.
    #
    # Die Platzhalter sind die aus COORDINATION.md: `/home/user/`, `C:\Users\X\`.
    # `runner` bleibt frei — das ist der GitHub-Actions-Lauf, kein Mensch.
    MUSTER = (
        (r"/home/(?!user\b|runner\b)[a-z][a-z0-9_-]{1,}/", "/home/user/"),
        # Windows: Trenner beidseitig, Laufwerksbuchstabe egal, `X`/`user` frei.
        (r"[A-Za-z]:[\\/]+Users[\\/]+(?![Xx]\b|user\b|Public\b)"
         r"[A-Za-z][A-Za-z0-9_.-]*[\\/]", r"C:\\Users\\X\\"),
    )

    def _treffer(self, muster: str) -> list[str]:
        import re
        rx = re.compile(muster)
        treffer = []
        for p in _getrackte_dateien():
            if not p.startswith(self.ORDNER) or not p.endswith((".py", ".sh", ".md")):
                continue
            try:
                with open(os.path.join(_REPO, p), encoding="utf-8") as f:
                    for nr, zeile in enumerate(f, 1):
                        if rx.search(zeile):
                            treffer.append(f"{p}:{nr}")
            except (OSError, UnicodeDecodeError):
                continue
        return treffer

    def test_kein_benutzername_im_pfad(self):
        """Beide Schreibweisen, in einem Durchlauf — sonst faellt beim naechsten
        Umbau wieder eine hinten runter."""
        for muster, ersatz in self.MUSTER:
            with self.subTest(muster=muster):
                self.assertEqual(
                    self._treffer(muster), [],
                    f"Benutzername im Pfad — bitte durch {ersatz} ersetzen.")

    def test_der_waechter_wuerde_beide_formen_auch_finden(self):
        """★ Die Selbstpruefung, die PRIV-04 ausgeloest hat.

        Ein leerer Trefferliste bedeutet zweierlei: „es gibt nichts" oder „ich
        schaue nicht hin". Bis zum 2026-09-03 war es das Zweite — die
        Windows-Form wurde nie geprueft und hatte 14 Treffer. Deshalb wird hier
        jedes Muster gegen einen KUENSTLICHEN Fund gehalten, statt sich auf die
        leere Liste zu verlassen."""
        import re
        # ★ Die Proben werden ZUSAMMENGESETZT, nicht hingeschrieben: stuende
        # der Beispielpfad als Literal in dieser Datei, faende der Waechter
        # oben sich selbst — `tests/` ist einer seiner eigenen Ordner. Beim
        # ersten Lauf ist genau das passiert. Die Alternative waere gewesen,
        # diese Datei auszunehmen; das haette den Waechter dauerhaft blind fuer
        # sich selbst gemacht, und Testdateien sind ausdruecklich in seinem
        # Zustaendigkeitsbereich.
        _konto = "konto" + "name"
        proben = {
            self.MUSTER[0][0]: (f"/home/{_konto}/projekt/datei.py",
                                "/home/user/projekt/datei.py"),
            self.MUSTER[1][0]: (f"C:/Users/{_konto}/Desktop/x",
                                "C:/Users/X/Desktop/x"),
        }
        for muster, (trifft, trifft_nicht) in proben.items():
            with self.subTest(muster=muster):
                rx = re.compile(muster)
                self.assertTrue(rx.search(trifft),
                                f"Muster findet {trifft!r} nicht — es wacht ueber nichts")
                self.assertFalse(rx.search(trifft_nicht),
                                 f"Muster schlaegt beim Platzhalter {trifft_nicht!r} an")



class KeineGeraeteSeriennummerTest(unittest.TestCase):
    """DOC-16a: keine ENTTEC-Seriennummer im oeffentlichen Repo.

    Die Nummer des Rig-Interfaces stand in drei Doku-/Protokoll-Zeilen
    (RIG_CHECKLISTE, LINUX_STABILITY_FULL_CHECK, BACKLOG HW-5c). Sie hilft
    niemandem, der das Repo liest, identifiziert aber ein konkretes Geraet.
    Anders als bei den Benutzerpfaden gilt das auch fuer BACKLOG/CHANGELOG.
    """

    # ENTTEC-Seriennummern: "EN" + sechs Ziffern, am Wortrand.
    MUSTER = r"\bEN\d{6}\b"

    def test_keine_seriennummer(self):
        import re
        rx = re.compile(self.MUSTER)
        treffer = []
        for p in _getrackte_dateien():
            if not p.endswith((".py", ".sh", ".md", ".json", ".txt")):
                continue
            try:
                with open(os.path.join(_REPO, p), encoding="utf-8") as f:
                    for nr, zeile in enumerate(f, 1):
                        if rx.search(zeile):
                            treffer.append(f"{p}:{nr}")
            except (OSError, UnicodeDecodeError):
                continue
        self.assertEqual(treffer, [], "Seriennummer im Repo — bitte als EN•••••• schreiben.")

    def test_muster_trifft(self):
        import re
        rx = re.compile(self.MUSTER)
        probe = "EN" + "123456"   # zusammengesetzt, sonst faende der Test sich selbst
        self.assertTrue(rx.search(f"Seriennr. {probe}"))
        self.assertFalse(rx.search("EN••••••"))


def _backlog_dateien(repo: str) -> list[str]:
    """PRIV-06: die drei Backlog-Gruppen, wie sie auf der Platte liegen.

    Bewusst ``glob`` statt ``git ls-files``: ein neues Fragment in
    ``backlog.d/`` ist vor dem ersten ``git add`` noch nicht getrackt, landet
    aber mit genau diesem PR oeffentlich — der Waechter soll es VORHER sehen.
    """
    import glob
    dateien = [os.path.join(repo, n) for n in ("BACKLOG.md", "BACKLOG_ARCHIVE.md")]
    dateien += sorted(glob.glob(os.path.join(repo, "backlog.d", "*.md")))
    return [d for d in dateien if os.path.isfile(d)]


def _backlog_funde(repo: str, nur_klarnamen: bool) -> list[str]:
    """``datei:zeile: befund`` fuer jede Zeile, die ``pruefe_oeffentlich()``
    beanstandet.

    ``nur_klarnamen`` trennt die zwei Teile des Gates: der Namensteil braucht
    die LOKALE Liste (in der CI fehlt sie), der Pfad-Teil nicht.

    Die E-Mail-Regel bleibt hier aussen vor: Backlog-Zeilen notieren
    Absturz-Signaturen als ``UI-FREEZE@main.py:367`` — fuer die Regel sieht
    das wie eine Adresse aus (2 Fehlalarme am 25.10.2026, 0 echte Funde).
    """
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "_session_claim_priv06", os.path.join(repo, "tools", "session_claim.py"))
    sc = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sc)
    funde = []
    for pfad in _backlog_dateien(repo):
        rel = os.path.relpath(pfad, repo).replace(os.sep, "/")
        with open(pfad, encoding="utf-8") as f:
            for nr, zeile in enumerate(f, 1):
                for befund in sc.pruefe_oeffentlich(zeile):
                    ist_name = befund.startswith("Klarname")
                    if befund == "E-Mail-Adresse" or ist_name != nur_klarnamen:
                        continue
                    # Der Befund nennt nur den Anfangsbuchstaben — die
                    # Fehlermeldung des Gates traegt den Namen also nicht weiter.
                    funde.append(f"{rel}:{nr}: {befund}")
    return funde


def _lokale_klarnamen(repo: str) -> list[str]:
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "_session_claim_priv06_namen", os.path.join(repo, "tools", "session_claim.py"))
    sc = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sc)
    return sc._klarnamen()


class KeinKlarnameImBacklogTest(unittest.TestCase):
    """PRIV-06: BACKLOG.md, BACKLOG_ARCHIVE.md und backlog.d/ sind pseudonym.

    Der Bestand ist am 25.10.2026 umgestellt worden (204 Stellen, der
    Betreiber heisst dort „Robin“). Ohne Waechter traegt der naechste
    Eintrag den Namen wieder hinein — genau dieselbe Lage wie vor PRIV-05
    auf der Tafel. Die Pruefung ist DIESELBE wie dort: ``pruefe_oeffentlich()``
    aus ``tools/session_claim.py`` gegen die lokale Namensliste.
    """

    def test_kein_klarname_in_den_backlog_dateien(self):
        if not _lokale_klarnamen(_REPO):
            self.skipTest("keine lokale Namensliste (klarnamen.txt) — der Namensteil "
                          "braucht sie und laeuft deshalb nur auf den Entwicklungs"
                          "rechnern, nicht in der CI; der Pfad-Teil laeuft weiter")
        funde = _backlog_funde(_REPO, nur_klarnamen=True)
        self.assertEqual(
            funde, [],
            "Klarname in den Backlog-Dateien — im Repo heisst der Betreiber "
            "„Robin“. Ersetzen mit:  tools/pseudonymisieren.py --anwenden "
            "--nur <datei>")

    def test_keine_privaten_pfade_oder_links_in_den_backlog_dateien(self):
        """Pfad-Teil: braucht keine lokale Liste und laeuft deshalb ueberall."""
        alt = os.environ.get("LIGHTOS_KLARNAMEN")
        os.environ["LIGHTOS_KLARNAMEN"] = os.path.join(_REPO, "gibt-es-nicht", "x.txt")
        try:
            funde = _backlog_funde(_REPO, nur_klarnamen=False)
        finally:
            if alt is None:
                os.environ.pop("LIGHTOS_KLARNAMEN", None)
            else:
                os.environ["LIGHTOS_KLARNAMEN"] = alt
        self.assertEqual(funde, [], "Privater Pfad oder Sitzungs-Link in den "
                                    "Backlog-Dateien (Platzhalter: /home/user/…, "
                                    "C:\\Users\\X\\…)")

    def test_der_waechter_wuerde_einen_neuen_namen_finden(self):
        """Gegenprobe mit einer KUENSTLICHEN Liste in einer tmp-Kopie — sonst
        ist „keine Funde“ nicht von „schaut nicht hin“ zu unterscheiden."""
        import shutil
        import tempfile
        name = "Kasi" + "mirus"          # zusammengesetzt: kein Fund in dieser Datei
        alt = os.environ.get("LIGHTOS_KLARNAMEN")
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, "tools"))
            os.makedirs(os.path.join(tmp, "backlog.d"))
            shutil.copy(os.path.join(_REPO, "tools", "session_claim.py"),
                        os.path.join(tmp, "tools"))
            liste = os.path.join(tmp, "klarnamen.txt")
            with open(liste, "w", encoding="utf-8") as f:
                f.write(f"# Probe\n{name}\n")
            with open(os.path.join(tmp, "BACKLOG.md"), "w", encoding="utf-8") as f:
                f.write("| X-1 | P2 | todo | Robin will es so |\n")
            with open(os.path.join(tmp, "BACKLOG_ARCHIVE.md"), "w", encoding="utf-8") as f:
                f.write(f"| X-2 | done | Wunsch von {name.upper()} |\n")
            with open(os.path.join(tmp, "backlog.d", "X-3.md"), "w", encoding="utf-8") as f:
                f.write(f"ID: X-3\nStatus: todo\n\n_{name}s Auftrag: …_\n"
                        f"/home/{'konto' + 'name'}/x\n")
            os.environ["LIGHTOS_KLARNAMEN"] = liste
            try:
                namen = _backlog_funde(tmp, nur_klarnamen=True)
                pfade = _backlog_funde(tmp, nur_klarnamen=False)
            finally:
                if alt is None:
                    os.environ.pop("LIGHTOS_KLARNAMEN", None)
                else:
                    os.environ["LIGHTOS_KLARNAMEN"] = alt
        self.assertEqual([f.split(":")[0] for f in namen],
                         ["BACKLOG_ARCHIVE.md", "backlog.d/X-3.md"])
        self.assertTrue(all(name not in f for f in namen),
                        "die Fehlermeldung darf den Namen nicht ausschreiben")
        self.assertEqual([f.split(":")[:2] for f in pfade], [["backlog.d/X-3.md", "5"]])


if __name__ == "__main__":
    unittest.main()
