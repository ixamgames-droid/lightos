"""XPLAT-20: die Prozess-Werkzeuge muessen auch ohne ``PYTHONUTF8`` arbeiten.

**Der Vorfall (31.08.2026).** Der erste Claim, den eine Windows-Sitzung mit
``tools/session_claim.py`` setzte, hat die geteilte Tafel zerstoert. Nicht ihren
Inhalt — ihren **Dateinamen**: im Baum von ``origin/sessions`` lag danach

    100644 blob eb26193…    "SESSIONS.md\\r"

statt ``SESSIONS.md``. Fuer die andere Sitzung war die Tafel damit spurlos weg
(``git show origin/sessions:SESSIONS.md`` -> „does not exist"), und zwar
lautlos: der Push war erfolgreich, das Werkzeug meldete „gehoert jetzt Sitzung
B". Die Koordination zweier Rechner haengt an dieser einen Datei.

**Die Ursache** ist ein einziges ``text=True`` in ``_git`` — und es macht zwei
verschiedene Fehler gleichzeitig:

1. *Dekodierung.* ``text=True`` nimmt die Locale-Kodierung, auf Windows cp1252.
   ``BACKLOG.md``/``CHANGELOG.md`` enthalten ★ ⚠ ⏳; deren Bytes kennt cp1252
   nicht. Der ``UnicodeDecodeError`` faellt im subprocess-Reader-Thread und wird
   verschluckt — ``stdout`` ist danach ``None`` bei ``returncode == 0``.
2. *Zeilenenden.* ``text=True`` uebersetzt beim SCHREIBEN ``\\n`` nach
   ``os.linesep``. Die mktree-Zeile ``"100644 blob <hash>\\tSESSIONS.md\\n"``
   bekam damit ein ``\\r`` — mitten in eine Datenstruktur, in der das ``\\n``
   ein Trennzeichen ist und kein Zeilenende.

**Warum dieser Test das statische Muster UND das Verhalten prueft:** der
naheliegende Fix — ``encoding="utf-8"`` ergaenzen — behebt nur Punkt 1. Punkt 2
bleibt, weil die Newline-Uebersetzung an ``newline=None`` haengt und
``subprocess.run`` gar kein ``newline``-Argument kennt. Ein Test, der nur nach
``encoding=`` sucht, wuerde den Fix von damals also gruen abnicken und den
Dateinamen-Fehler ein zweites Mal durchlassen. Deshalb steht unten ein Test,
der einen echten Baum baut und den Namen darin ansieht.

**Warum das Gate NICHT ``PYTHONUTF8=1`` setzt:** damit waere dieser ganze
Fehlerraum im Gate unsichtbar — und genau dort wieder da, wo die Werkzeuge
wirklich laufen: in der PowerShell des Menschen. Die Werkzeuge muessen ohne die
Variable stimmen, nicht mit ihr.
"""
from __future__ import annotations

import ast
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
WERKZEUGE = REPO / "tools"

# Werkzeuge, die mit git/gh reden oder einen Bericht ausgeben und deshalb unter
# die Regel fallen. Bewusst eine Positivliste: eine Musterjagd ueber alles in
# tools/ wuerde bei jedem neuen Hilfsskript falsch anschlagen.
GEPRUEFTE_WERKZEUGE = (
    "session_claim.py",
    "backlog_ids.py",
    "backlog_status_drift.py",
    "pr_bereit.py",
    "pseudonymisieren.py",
    "zeitbomben_gate.py",
    "library_testreste.py",
    "audit_bilder_stand.py",
    "changelog_sammeln.py",
)


def _cp1252_umgebung() -> dict:
    """Umgebung ohne die UTF-8-Schalter — so startet David die Werkzeuge.

    ``PYTHONUTF8``/``PYTHONIOENCODING`` stehen auf diesem Rechner nur zufaellig
    in der Umgebung der KI-Sitzung; weder ``verify_loop.ps1`` noch der
    Lock-Runner setzen sie. Ohne sie ist die Locale-Kodierung cp1252.
    """
    env = dict(os.environ)
    env.pop("PYTHONUTF8", None)
    env.pop("PYTHONIOENCODING", None)
    return env


class KeinTextTrueOhneEncodingTest(unittest.TestCase):
    """Statische Haelfte: ``subprocess`` nie mit der Locale-Kodierung."""

    def test_jeder_subprocess_aufruf_legt_die_kodierung_fest(self):
        funde = []
        for name in GEPRUEFTE_WERKZEUGE:
            pfad = WERKZEUGE / name
            if not pfad.exists():                       # Werkzeug entfernt
                continue
            baum = ast.parse(pfad.read_text(encoding="utf-8"), filename=str(pfad))
            for knoten in ast.walk(baum):
                if not isinstance(knoten, ast.Call):
                    continue
                schluessel = {kw.arg for kw in knoten.keywords}
                textmodus = schluessel & {"text", "universal_newlines"}
                if not textmodus:
                    continue
                if "encoding" not in schluessel:
                    funde.append(f"{name}:{knoten.lineno}")
        self.assertEqual(
            funde, [],
            "subprocess mit text=True ohne encoding= — dekodiert auf Windows "
            "mit cp1252 und stirbt an den ★/⚠-Zeichen im Repo. Entweder "
            "encoding='utf-8' setzen oder (wenn geschrieben wird!) auf Bytes "
            f"umstellen. Fundstellen: {funde}")


class SchreibpfadBleibtLfTest(unittest.TestCase):
    """Verhaltens-Haelfte: der Fehler, den ``encoding=`` allein NICHT behebt."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = self._tmp.name
        subprocess.run(["git", "init", "-q"], cwd=self.repo, check=True,
                       capture_output=True)
        self.addCleanup(self._tmp.cleanup)

    def _sc(self):
        """``session_claim`` laden, ohne ``tools`` als Paket zu brauchen."""
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "_sc_unter_test", WERKZEUGE / "session_claim.py")
        assert spec and spec.loader, "session_claim.py nicht ladbar"
        modul = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modul)
        return modul

    def test_der_baum_traegt_den_dateinamen_ohne_wagenruecklauf(self):
        """Der eigentliche Vorfall: ``SESSIONS.md\\r`` statt ``SESSIONS.md``."""
        sc = self._sc()
        blob = sc._git("hash-object", "-w", "--stdin",
                       eingabe="inhalt\n", repo=self.repo)
        baum = sc._git("mktree", eingabe=f"100644 blob {blob}\t{sc.DATEI}\n",
                       repo=self.repo)
        eintraege = subprocess.run(["git", "ls-tree", baum], cwd=self.repo,
                                   capture_output=True).stdout.decode("utf-8")
        self.assertIn(f"\t{sc.DATEI}\n", eintraege,
                      "der Dateiname im Baum ist nicht exakt SESSIONS.md — "
                      f"so sah der Vorfall aus. Baum: {eintraege!r}")
        self.assertNotIn("\\r", eintraege,
                         "git zeigt den Namen escaped an, das heisst er "
                         f"enthaelt ein Sonderzeichen: {eintraege!r}")

    def test_geschriebener_inhalt_behaelt_lf(self):
        """Auch der Blob-Inhalt darf auf Windows kein CRLF bekommen."""
        sc = self._sc()
        blob = sc._git("hash-object", "-w", "--stdin",
                       eingabe="zeile1\nzeile2\n", repo=self.repo)
        roh = subprocess.run(["git", "cat-file", "blob", blob], cwd=self.repo,
                             capture_output=True).stdout
        self.assertEqual(roh, b"zeile1\nzeile2\n",
                         "Zeilenenden wurden beim Schreiben uebersetzt — auf "
                         "Windows macht text=True aus \\n ein \\r\\n")

    def test_umlaute_ueberleben_den_weg_durch_git(self):
        """Der Gedankenstrich der Tafel ist der Kanarienvogel.

        ``—`` (U+2014) ist in cp1252 als EIN Byte 0x97 darstellbar. Genau
        deshalb faellt der Fehler hier nicht auf, sondern erst drueben: die
        Linux-Sitzung liest UTF-8 und findet ein ungueltiges Startbyte.
        """
        sc = self._sc()
        text = "# SESSIONS.md — wer arbeitet gerade woran\n"
        blob = sc._git("hash-object", "-w", "--stdin", eingabe=text,
                       repo=self.repo)
        roh = subprocess.run(["git", "cat-file", "blob", blob], cwd=self.repo,
                             capture_output=True).stdout
        self.assertEqual(roh, text.encode("utf-8"),
                         "der Gedankenstrich kam nicht als UTF-8 an — mit "
                         "cp1252 waere er ein einzelnes Byte 0x97 und die "
                         "Tafel fuer die Linux-Sitzung unlesbar")


def _wegwerf_tafel(wurzel: str, blocker: list[str]) -> str:
    """QA-113: eine Tafel nur fuer diesen Test — Bare-Repo ``lightos-intern.git``
    (Stellvertreter fuer GitHub, wie in ``test_session_claim``) plus Klon mit
    ``SESSIONS.md`` auf ``main``. Liefert den Klon-Pfad fuer
    ``LIGHTOS_TAFEL_REPO``. Nie die echte Tafel: deren Inhalt schreiben andere
    Sitzungen, ein Test darf nicht davon abhaengen, was dort gerade steht."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("_sc_tafel", WERKZEUGE / "session_claim.py")
    sc = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sc)

    def git(*a, cwd=None):
        subprocess.run(["git", *a], cwd=cwd, check=True, capture_output=True)

    bare = os.path.join(wurzel, "lightos-intern.git")
    klon = os.path.join(wurzel, "lightos-intern")
    git("init", "--quiet", "--bare", bare)
    git("clone", "--quiet", bare, klon)
    git("config", "user.email", "test@example.invalid", cwd=klon)
    git("config", "user.name", "Test", cwd=klon)
    git("checkout", "--quiet", "-b", "main", cwd=klon)
    inhalt = sc.rendere({"claims": [], "blocker": blocker, "verlauf": []})
    with open(os.path.join(klon, sc.DATEI), "w", encoding="utf-8", newline="\n") as f:
        f.write(inhalt)
    git("add", sc.DATEI, cwd=klon)
    git("commit", "--quiet", "-m", "Tafel fuer den Test", cwd=klon)
    git("push", "--quiet", "origin", "main", cwd=klon)
    return klon


class WerkzeugeUeberlebenCp1252Test(unittest.TestCase):
    """Der Endnachweis: ein echter Lauf ohne die UTF-8-Schalter."""

    # Nur Werkzeuge mit einem gefahrlosen Nur-Lese-Modus. `pr_bereit` fragt
    # GitHub und `zeitbomben_gate` startet pytest — beide gehoeren nicht in
    # einen Test, der bloss die Kodierung nachweisen will.
    # QA-113: dazu die Rueckgaben, die ein fehlerfreier Lauf haben darf.
    # ``backlog_ids`` fragt GitHub (``gh pr list``); ohne Anmeldung — etwa im
    # Gate mit eigenem APPDATA — meldet es „Abdeckung unvollstaendig“ mit 2.
    # Das ist eine Auskunft, kein Absturz (der endet mit 1 und Traceback).
    HARMLOSE_LAEUFE = (
        ("backlog_ids.py", ["--kein-fetch", "--gruppe", "FM"], (0, 2)),
        ("backlog_status_drift.py", ["--kein-fetch"], (0,)),
        ("session_claim.py", ["list"], (0,)),
    )

    # QA-113: so sah der Eintrag aus, der den Fehlalarm ausloeste (die Tafel
    # nannte den Fehlernamen woertlich) — dazu Zeichen, die cp1252 nicht kennt.
    TAFEL_EINTRAG = ("2026-11-02T18:39Z (D) D AN A — Testfall mit Ordner "
                     "„Jörg_Łódź“ ⏳ ★: ohne Fix "
                     "UnicodeEncodeError, sonst UnicodeDecodeError")

    @unittest.skipUnless(sys.platform == "win32",
                         "cp1252 ist die Locale-Kodierung nur auf Windows; "
                         "auf Linux ist der Lauf ohne PYTHONUTF8 ohnehin UTF-8")
    def test_kein_werkzeug_stirbt_an_der_kodierung(self):
        env = _cp1252_umgebung()
        tmp = tempfile.TemporaryDirectory(prefix="xplat20_tafel_")
        self.addCleanup(tmp.cleanup)
        env["LIGHTOS_TAFEL_REPO"] = _wegwerf_tafel(tmp.name, [self.TAFEL_EINTRAG])
        for name, argumente, erlaubt in self.HARMLOSE_LAEUFE:
            with self.subTest(werkzeug=name):
                r = subprocess.run(
                    [sys.executable, "-X", "utf8=0", str(WERKZEUGE / name),
                     *argumente],
                    cwd=REPO, capture_output=True, env=env, timeout=180)
                ausgabe = (r.stdout + r.stderr).decode("utf-8", "replace")
                schaden = _kodierschaden(r.stderr)
                self.assertIsNone(
                    schaden,
                    f"{name} stirbt ohne PYTHONUTF8 an {schaden} — genau "
                    "so startet der Mensch es in seiner PowerShell.\n"
                    f"{ausgabe[-600:]}")
                self.assertNotIn("Traceback (most recent call last)",
                                 r.stderr.decode("utf-8", "replace"),
                                 f"{name} stirbt mit einem Traceback\n{ausgabe[-600:]}")
                self.assertIn(r.returncode, erlaubt,
                              f"{name}: Rueckgabe {r.returncode}\n{ausgabe[-600:]}")


def _kodierschaden(stderr: bytes) -> str | None:
    """QA-113: Name des Kodierfehlers, an dem ein Werkzeug WIRKLICH gestorben
    ist — sonst ``None``.

    Gesucht wird nur auf stderr und nur als Traceback-Schluss (Zeilenanfang
    ``UnicodeEncodeError:`` bzw. ``UnicodeDecodeError:``). Vorher stand hier
    eine Textsuche ueber stdout UND stderr; ``session_claim.py list`` gibt aber
    die letzten Tafel-Eintraege aus — und ein Eintrag, der den Fehlernamen
    nannte, machte den Test auf jedem Windows-Zweig rot (02.11.2026), obwohl
    das Werkzeug fehlerfrei lief."""
    text = stderr.decode("utf-8", "replace")
    if "Traceback (most recent call last)" not in text:
        return None
    for name in ("UnicodeEncodeError", "UnicodeDecodeError"):
        if re.search(rf"^\s*{name}\b", text, re.MULTILINE):
            return name
    return None


class KodierschadenErkennungTest(unittest.TestCase):
    """QA-113 Gegenprobe: die engere Pruefung findet einen echten Absturz weiter
    — und nur den."""

    def test_freier_text_mit_dem_fehlernamen_ist_kein_absturz(self):
        self.assertIsNone(_kodierschaden(
            "Hinweis: UnicodeEncodeError war gestern\n".encode("utf-8")))

    def test_traceback_auf_stderr_wird_erkannt(self):
        tb = ("Traceback (most recent call last):\n"
              '  File "x.py", line 1, in <module>\n'
              "UnicodeEncodeError: 'charmap' codec can't encode character\n")
        self.assertEqual(_kodierschaden(tb.encode("utf-8")), "UnicodeEncodeError")

    @unittest.skipUnless(sys.platform == "win32", "cp1252 nur unter Windows")
    def test_echter_kodier_absturz_wird_erkannt(self):
        """Ein Kind, das wirklich an cp1252 stirbt (``print`` von „Ł“)."""
        r = subprocess.run(
            [sys.executable, "-X", "utf8=0", "-c", "print('\\u0141')"],
            capture_output=True, env=_cp1252_umgebung(), timeout=60)
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual(_kodierschaden(r.stderr), "UnicodeEncodeError",
                         r.stderr.decode("utf-8", "replace"))


if __name__ == "__main__":
    unittest.main()
