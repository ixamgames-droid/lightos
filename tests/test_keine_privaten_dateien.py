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
    # DOC-78: dazu die Startseite und Anleitungen im Wurzelordner, die
    # GitHub-Vorlagen und Workflows — das sieht ein Besucher zuerst.
    ORDNER = ("src", "tests", "tools", "docs", ".github/")
    WURZEL_DATEIEN = ("README.md", "INSTALL.md", "CONTRIBUTING.md", "AGENTS.md",
                      "WORKFLOW.md", "ARCHITECTURE.md", "ROADMAP.md",
                      "COORDINATION.md", "DEVELOPMENT_NOTES.md",
                      "THIRD_PARTY_NOTICES.md", "start.ps1", "start.sh",
                      "start.bat", "Code-Film.bat", "Code-Film.sh")
    ENDUNGEN = (".py", ".sh", ".md", ".ps1", ".bat", ".cmd", ".yml", ".yaml")

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
            if p not in self.WURZEL_DATEIEN and (
                    not p.startswith(self.ORDNER) or not p.endswith(self.ENDUNGEN)):
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


# ── DOC-78: Zugangsschluessel ────────────────────────────────────────────────
#: Nur Formate, die praktisch nie zufaellig entstehen — die weichen Muster aus
#: ``tools/session_claim.py`` („Kennwort: …", ``token=…``) schlagen in Tests
#: und Doku zu oft an, um als hartes Gate zu taugen. Gemeldet wird die ART,
#: nie der Wert.
ZUGANGS_MUSTER = (
    ("GitHub-Token", r"(?<![A-Za-z0-9])gh[pousr]_[A-Za-z0-9]{30,}"),
    ("GitHub-Token (fein)", r"(?<![A-Za-z0-9])github_pat_[A-Za-z0-9_]{30,}"),
    ("AWS-Schluessel", r"(?<![A-Z0-9])(?:AKIA|ASIA)[0-9A-Z]{16}(?![A-Z0-9])"),
    ("privater Schluessel-Block",
     r"-----BEGIN (?:[A-Z0-9]+ )*PRIVATE KEY(?: BLOCK)?-----"),
    ("API-Schluessel (sk-…)", r"(?<![A-Za-z0-9-])sk-(?:ant-|proj-)?[A-Za-z0-9_-]{32,}"),
    ("GitLab-Token", r"(?<![A-Za-z0-9])glpat-[A-Za-z0-9_-]{20,}"),
    ("Slack-Token", r"(?<![A-Za-z0-9])xox[abprs]-[A-Za-z0-9-]{20,}"),
)

#: Handy-Konsole: ein echter Link traegt den Schluessel als ``?k=…`` (8
#: Zeichen aus ``secrets.token_urlsafe(6)``). In Anleitungen steht dort nur ein
#: Platzhalter (``<Schlüssel>``, ``…``) — ein konkreter Wert waere ein
#: abfotografierter Zugang.
HANDY_LINK_MUSTER = r"[?&](?:k|token|key)=[A-Za-z0-9_-]{6,}"


def _textzeilen(pfad: str):
    try:
        if os.path.getsize(pfad) > 4 * 1024 * 1024:
            return
        with open(pfad, encoding="utf-8") as f:
            for nr, zeile in enumerate(f, 1):
                yield nr, zeile
    except (OSError, UnicodeDecodeError):
        return


class KeineZugangsschluesselTest(unittest.TestCase):
    """DOC-78: kein Token, kein privater Schluessel, kein Handy-Schluessel.

    Die Durchsicht vom 15.11.2026 fand keinen echten Schluessel im Repo —
    gewacht hat darueber aber nur ``session_claim.py``, und das nur fuer die
    Sitzungs-Tafel. Dieses Gate prueft JEDE getrackte Textdatei.
    """

    def setUp(self):
        self.dateien = _getrackte_dateien()
        if not self.dateien:
            self.skipTest("kein git-Checkout (Tarball/Sandbox) — nichts zu pruefen")

    def test_kein_zugangsschluessel_in_getrackten_dateien(self):
        import re
        muster = [(art, re.compile(m)) for art, m in ZUGANGS_MUSTER]
        funde = []
        for p in self.dateien:
            for nr, zeile in _textzeilen(os.path.join(_REPO, p)):
                for art, rx in muster:
                    if rx.search(zeile):
                        funde.append(f"{p}:{nr}: {art}")
        self.assertEqual(funde, [], "Zugangsschluessel im OEFFENTLICHEN Repo — "
                                    "Datei bereinigen UND den Schluessel beim "
                                    "Anbieter wechseln (die Git-Historie behaelt ihn).")

    def test_kein_handy_schluessel_in_anleitungen(self):
        import re
        rx = re.compile(HANDY_LINK_MUSTER)
        funde = []
        for p in self.dateien:
            if not p.endswith(".md"):
                continue
            for nr, zeile in _textzeilen(os.path.join(_REPO, p)):
                if rx.search(zeile):
                    funde.append(f"{p}:{nr}")
        self.assertEqual(funde, [], "Link mit konkretem Zugangsschluessel in der "
                                    "Doku — Platzhalter <Schlüssel> verwenden.")

    def test_die_muster_wuerden_einen_fund_erkennen(self):
        """Gegenprobe mit ZUSAMMENGESETZTEN Proben (sonst faende das Gate sich
        selbst) — und die Platzhalter der Doku bleiben frei."""
        import re
        x30 = "Ab3" * 12
        proben = {
            "GitHub-Token": "gh" + "p_" + x30,
            "GitHub-Token (fein)": "github" + "_pat_" + x30,
            "AWS-Schluessel": "AK" + "IA" + "ABCDEFGH12345678",
            "privater Schluessel-Block": "-----BEGIN " + "OPENSSH PRIVATE " + "KEY-----",
            "API-Schluessel (sk-…)": "s" + "k-ant-" + x30,
            "GitLab-Token": "gl" + "pat-" + x30,
            "Slack-Token": "xo" + "xb-" + x30,
        }
        for art, m in ZUGANGS_MUSTER:
            with self.subTest(art=art):
                self.assertTrue(re.search(m, proben[art]), f"{art}: Probe nicht erkannt")
        self.assertFalse(re.search(ZUGANGS_MUSTER[3][1], "-----BEGIN PUBLIC KEY-----"))
        self.assertFalse(re.search(ZUGANGS_MUSTER[4][1], "fix/ui95-kiosk-vollbild-ohne-bearbeiten"))
        rx = re.compile(HANDY_LINK_MUSTER)
        self.assertTrue(rx.search("http://192.0.2.10:5000/konsole?k=" + "Ab-_9xYz"))
        self.assertFalse(rx.search("http://<PC-IP>:5000/konsole?k=<Schlüssel>"))
        self.assertFalse(rx.search("/konsole?k=…"))


def _doku_dateien(repo: str) -> list[str]:
    """DOC-78: was ein Besucher liest — Startseite, Anleitungen, Vorlagen.
    CHANGELOG/BACKLOG sind Protokolle (PRIV-06 regelt das Backlog)."""
    import glob
    dateien = [os.path.join(repo, n) for n in (
        "README.md", "INSTALL.md", "CONTRIBUTING.md", "AGENTS.md", "WORKFLOW.md",
        "ARCHITECTURE.md", "ROADMAP.md")]
    dateien += sorted(glob.glob(os.path.join(repo, "docs", "**", "*.md"), recursive=True))
    dateien += sorted(glob.glob(os.path.join(repo, ".github", "**", "*.md"), recursive=True))
    return [d for d in dateien if os.path.isfile(d)]


def _doku_klarnamen_funde(repo: str) -> list[str]:
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "_session_claim_doc78", os.path.join(repo, "tools", "session_claim.py"))
    sc = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sc)
    funde = []
    for pfad in _doku_dateien(repo):
        rel = os.path.relpath(pfad, repo).replace(os.sep, "/")
        for nr, zeile in _textzeilen(pfad):
            for befund in sc.pruefe_oeffentlich(zeile):
                if befund.startswith("Klarname"):
                    funde.append(f"{rel}:{nr}: {befund}")
    return funde


class KeinKlarnameInDerDokuTest(unittest.TestCase):
    """DOC-78: README, Anleitungen und docs/ sind pseudonym wie das Backlog.

    Bei der Durchsicht standen dort noch 67 Stellen mit dem Klarnamen des
    Rig-Betreibers (umgestellt mit ``tools/pseudonymisieren.py --nur docs``).
    Wie PRIV-06 braucht der Namensteil die LOKALE Liste und laeuft deshalb nur
    auf den Entwicklungsrechnern.
    """

    def test_kein_klarname_in_der_doku(self):
        if not _lokale_klarnamen(_REPO):
            self.skipTest("keine lokale Namensliste (klarnamen.txt) — laeuft nur "
                          "auf den Entwicklungsrechnern, nicht in der CI")
        funde = _doku_klarnamen_funde(_REPO)
        self.assertEqual(funde, [], "Klarname in der Doku — im Repo heisst der "
                                    "Betreiber „Robin“. Ersetzen mit:  "
                                    "tools/pseudonymisieren.py --anwenden --nur <datei>")

    def test_der_waechter_wuerde_einen_namen_in_der_doku_finden(self):
        import shutil
        import tempfile
        name = "Kasi" + "mirus"          # zusammengesetzt: kein Fund in dieser Datei
        alt = os.environ.get("LIGHTOS_KLARNAMEN")
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, "tools"))
            os.makedirs(os.path.join(tmp, "docs", "anleitung_x"))
            shutil.copy(os.path.join(_REPO, "tools", "session_claim.py"),
                        os.path.join(tmp, "tools"))
            liste = os.path.join(tmp, "klarnamen.txt")
            with open(liste, "w", encoding="utf-8") as f:
                f.write(f"# Probe\n{name}\n")
            with open(os.path.join(tmp, "README.md"), "w", encoding="utf-8") as f:
                f.write("# X\n\nRobin hat es getestet.\n")
            with open(os.path.join(tmp, "docs", "anleitung_x", "A.md"), "w",
                      encoding="utf-8") as f:
                f.write(f"# A\n\n{name}s Rig\n")
            os.environ["LIGHTOS_KLARNAMEN"] = liste
            try:
                funde = _doku_klarnamen_funde(tmp)
            finally:
                if alt is None:
                    os.environ.pop("LIGHTOS_KLARNAMEN", None)
                else:
                    os.environ["LIGHTOS_KLARNAMEN"] = alt
        self.assertEqual([f.split(":")[:2] for f in funde], [["docs/anleitung_x/A.md", "3"]])
        self.assertTrue(all(name not in f for f in funde))


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
