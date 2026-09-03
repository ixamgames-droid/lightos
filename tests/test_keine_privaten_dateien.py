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
                       capture_output=True, text=True)
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


if __name__ == "__main__":
    unittest.main()
