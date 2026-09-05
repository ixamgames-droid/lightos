"""STAB-CURSHOW (a) Lint-Gate: tools/-Skripte, die den App-State / die Show-DB
anfassen koennen, MUESSEN isoliert laufen.

Regel: Referenziert ein Top-Level-Skript in tools/ eine der State-/DB-APIs
(get_state, app_state, load_show, save_show, reset_show, get_function_manager),
muss es entweder `import _gen_env` enthalten (setzt seit STAB-CURSHOW (a) eine
Wegwerf-`LIGHTOS_SHOW_DB`) oder selbst `LIGHTOS_SHOW_DB` setzen. Sonst arbeitet
ein Tool-Lauf auf Davids geteilter data/current_show.db — der dokumentierte
Race/Desync-Fall (46 Duplikat-Zeilen, nichtdeterministische Patch-Zahlen).

Whitelist nur fuer bewusste Ausnahmen mit Begruendung. tools/_archiv/ ist
ausgenommen (ausgemusterte Skripte, siehe tools/_archiv/README.md).
"""
import os
import re
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = os.path.join(REPO, "tools")

STATE_API = re.compile(
    r"\b(get_state|app_state|load_show|save_show|reset_show|get_function_manager)\b")
# Echte Isolation, nicht blosse Erwaehnung: Import am Zeilenanfang ODER eine
# echte os.environ-Zuweisung/-setdefault auf LIGHTOS_SHOW_DB. Ein Kommentar,
# der die Variable nur nennt, darf den Lint nicht beruhigen (Review 2026-07-19).
ISOLATION = re.compile(
    r"^\s*import _gen_env\b"
    r"|os\.environ(?:\.setdefault)?\s*[\(\[]\s*[\"']LIGHTOS_SHOW_DB",
    re.M)

def _nur_code(text: str) -> str:
    """Quelltext ohne Kommentare und Docstrings — Zeilen und Spalten bleiben.

    ★★ QA-76: Beide Muster dieses Waechters suchen im ROHTEXT und koennen
    „erwaehnt" nicht von „benutzt" unterscheiden. Gemessen wurde beides, und
    die Loecher zeigen in ENTGEGENGESETZTE Richtungen:

    * **Falscher Alarm.** ``tools/session_claim.py`` fasst den App-State
      nirgends an, erwaehnt aber in einem Kommentar die Datei ``app_state.py``
      (es erklaert einen Koordinationsfehler). Der Waechter meldete einen
      Verstoss. Der naheliegende „Fix" waere gewesen, den Kommentar
      umzuschreiben — also Prosa zu verbiegen, um einen Textsucher zu beruhigen.
    * **Falsche Entwarnung, und das ist die teure Richtung.** Ein Werkzeug, das
      ``get_state()`` benutzt und ``LIGHTOS_SHOW_DB`` nur in einem Kommentar
      oder Docstring NENNT, galt als isoliert und kam durch — es haette auf der
      echten ``data/current_show.db`` laufen koennen. Genau das schliesst der
      Kommentar an :data:`ISOLATION` seit 2026-07-19 aus, aber nur fuer die
      ``import _gen_env``-Haelfte (die einen Zeilenanfang verlangt), nicht fuer
      die ``os.environ``-Haelfte.

    Es wurde also an Kommentare gedacht, die SICHERHEIT vortaeuschen, und nicht
    an solche, die GEFAHR vortaeuschen — und die erste Haelfte war nur zur
    Haelfte umgesetzt. Beides faellt weg, wenn beide Muster auf CODE schauen
    statt auf Text.

    Zeichenweise GELEERT statt entfernt: ``^\s*import _gen_env`` haengt am
    Zeilenanfang, ein Umbau der Zeilenstruktur wuerde das Muster brechen.
    """
    import ast
    import io as _io
    import tokenize
    zeilen = text.splitlines(keepends=True)
    if not zeilen:
        return text

    def leeren(z1, s1, z2, s2):
        for z in range(z1, z2 + 1):
            if z - 1 >= len(zeilen):
                break
            zeile = zeilen[z - 1]
            von = s1 if z == z1 else 0
            bis = s2 if z == z2 else len(zeile.rstrip("\n"))
            zeilen[z - 1] = zeile[:von] + " " * max(0, bis - von) + zeile[bis:]

    # Docstrings ueber den Syntaxbaum finden (ein String als ganze Anweisung).
    doc = set()
    try:
        for knoten in ast.walk(ast.parse(text)):
            koerper = getattr(knoten, "body", None)
            if not isinstance(koerper, list) or not koerper:
                continue
            erst = koerper[0]
            if (isinstance(erst, ast.Expr)
                    and isinstance(erst.value, ast.Constant)
                    and isinstance(erst.value.value, str)):
                doc.add((erst.value.lineno, erst.value.col_offset))
    except SyntaxError:
        pass                      # unlesbar -> dann bleibt der Rohtext streng

    try:
        marken = list(tokenize.generate_tokens(_io.StringIO(text).readline))
    except (tokenize.TokenError, IndentationError, SyntaxError):
        return text               # im Zweifel STRENG bleiben, nicht entwarnen
    for m in marken:
        if m.type == tokenize.COMMENT or (m.type == tokenize.STRING and m.start in doc):
            leeren(m.start[0], m.start[1], m.end[0], m.end[1])
    return "".join(zeilen)


# Bewusste Ausnahmen: Datei -> Begruendung (bitte NUR mit gutem Grund erweitern).
WHITELIST = {
    "_run_showcase_app.py": "Echt-App-Launcher fuer Doku-Captures: soll sich wie die "
                            "reale App verhalten (Fenster + echte Show-DB).",
    "patch_quarantaene.py": "STAB-DEDUP-OPT: raeumt Davids ECHTEN Patch auf — eine "
                            "Wegwerf-DB waere leer und das Werkzeug damit sinnlos. "
                            "Abgesichert stattdessen durch die Vorgaben des Werkzeugs "
                            "selbst: ohne --anwenden wird nichts veraendert, der "
                            "Unbeladen-Riegel bricht ab, wenn die Show nicht geladen "
                            "ist, und verschoben wird in eine Quarantaene statt "
                            "geloescht. LIGHTOS_SHOW_DB wird respektiert — wer an "
                            "einer Kopie ueben will, setzt sie.",
}


def _tool_scripts():
    for name in sorted(os.listdir(TOOLS)):
        if not name.endswith(".py"):
            continue
        path = os.path.join(TOOLS, name)
        if os.path.isfile(path):
            yield name, path


class ProsaIstKeinCodeTest(unittest.TestCase):
    """★★★ QA-76 — und der wichtigste Test hier ist die POSITIVKONTROLLE.

    Einen Waechter praeziser zu machen heisst immer auch, ihn blinder machen zu
    koennen. Diese Klasse prueft deshalb beide Seiten in EINER Tabelle: was
    weiterhin anschlagen MUSS, und was nie haette anschlagen duerfen.
    """

    def _urteil(self, quelltext):
        """(faengt_zustand, gilt_als_isoliert) nach der Bereinigung."""
        code = _nur_code(quelltext)
        return bool(STATE_API.search(code)), bool(ISOLATION.search(code))

    def test_faelle(self):
        F = [
            # (Name, Quelltext, faengt_zustand, gilt_als_isoliert, Begruendung)
            ('echte Nutzung ohne Isolation',
             'from src.core.app_state import get_state\nget_state()\n',
             True, False, 'POSITIVKONTROLLE: der Fall, fuer den es den Waechter gibt'),
            ('echte Nutzung MIT _gen_env',
             'import _gen_env\nfrom src.core.app_state import get_state\n',
             True, True, 'sauber isoliert'),
            ('echte Nutzung MIT os.environ',
             'import os\nos.environ["LIGHTOS_SHOW_DB"] = "/tmp/x.db"\nfrom src.core.app_state import get_state\n',
             True, True, 'die zweite erlaubte Form'),
            ('nur im Kommentar ERWAEHNT',
             '# erklaert einen Fehler in app_state.py, fasst ihn aber nicht an\nprint(1)\n',
             False, False, 'der falsche Alarm, an dem PROC-12 haengenblieb'),
            ('nur im Docstring ERWAEHNT',
             '"""Dieses Werkzeug fasst get_state() ausdruecklich NICHT an."""\nprint(1)\n',
             False, False, 'dieselbe Klasse, eine Ebene tiefer'),
            ('Nutzung + Isolation NUR im Kommentar',
             '# wer will, setzt os.environ["LIGHTOS_SHOW_DB"] selbst\nfrom src.core.app_state import get_state\nget_state()\n',
             True, False, 'DIE TEURE RICHTUNG: kam vorher als isoliert durch'),
            ('Nutzung + Isolation NUR im Docstring',
             '"""Setze os.environ["LIGHTOS_SHOW_DB"], wenn du willst."""\nfrom src.core.app_state import get_state\nget_state()\n',
             True, False, 'dieselbe falsche Entwarnung'),
            ('auskommentierter _gen_env-Import',
             '# import _gen_env\nfrom src.core.app_state import get_state\n',
             True, False, 'war schon vorher dicht, bleibt es'),
        ]
        for name, quelle, zustand, isoliert, warum in F:
            with self.subTest(fall=name):
                self.assertEqual(self._urteil(quelle), (zustand, isoliert), warum)

    def test_unlesbare_datei_bleibt_STRENG(self):
        """★ Die Fehlrichtung im Fehlerfall ist eine Entscheidung, keine
        Nebensache: laesst sich eine Datei nicht zerlegen, wird der ROHTEXT
        geprueft. Lieber ein falscher Alarm, den jemand ansieht, als eine
        stille Entwarnung fuer eine Datei, die niemand lesen konnte."""
        kaputt = 'def f(:\n  # os.environ["LIGHTOS_SHOW_DB"]\n  get_state()\n'
        self.assertEqual(_nur_code(kaputt), kaputt, "unveraendert = streng")
        self.assertTrue(STATE_API.search(_nur_code(kaputt)))

    def test_zeilenstruktur_bleibt_erhalten(self):
        """Der Zeilenanker von ``import _gen_env`` haengt am Zeilenanfang — wer
        Kommentare ENTFERNT statt sie zu leeren, verschiebt Zeilen und bricht
        das Muster."""
        quelle = '# ein Kommentar\nimport _gen_env\nx = 1  # noch einer\n'
        code = _nur_code(quelle)
        self.assertEqual(len(code.splitlines()), len(quelle.splitlines()))
        self.assertTrue(ISOLATION.search(code), "Zeilenanker muss weiter greifen")

    def test_die_echten_werkzeuge_bleiben_beurteilbar(self):
        """Gegenprobe am echten Bestand: die Bereinigung darf keine Datei
        unlesbar machen und keine Isolation wegputzen, die wirklich da ist."""
        geprueft = 0
        for name, pfad in _tool_scripts():
            with open(pfad, "r", encoding="utf-8", errors="replace") as f:
                roh = f.read()
            code = _nur_code(roh)
            geprueft += 1
            self.assertEqual(len(code.splitlines()), len(roh.splitlines()),
                             name + ": Zeilenzahl veraendert")
            if re.search(r"^\s*import _gen_env\b", roh, re.M):
                self.assertTrue(ISOLATION.search(code),
                                name + ": echte Isolation wegbereinigt")
        self.assertGreater(geprueft, 10, "zu wenige Werkzeuge geprueft")


class DbIsolationLintTest(unittest.TestCase):
    def test_state_touching_tools_are_isolated(self):
        offenders = []
        for name, path in _tool_scripts():
            if name in WHITELIST:
                continue
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                text = _nur_code(f.read())      # QA-76: Code lesen, nicht Prosa
            if STATE_API.search(text) and not ISOLATION.search(text):
                offenders.append(name)
        self.assertEqual(offenders, [], (
            "Diese tools/-Skripte referenzieren State-/Show-DB-APIs ohne Isolation. "
            "Fix: `import _gen_env` als erste Zeile vor den src-Imports (oder bewusst "
            "LIGHTOS_SHOW_DB setzen; echte Ausnahmen in die WHITELIST dieses Tests "
            f"mit Begruendung): {offenders}"))

    def test_archived_state_touching_tools_are_isolated(self):
        """tools/_archiv/ ist NICHT mehr generell ausgenommen (TOOLS-ALTGEN, 2026-07-27).

        Bis der Pfad-Bootstrap kam, waren die archivierten Skripte gar nicht
        startbar (Repo-Root fehlte auf ``sys.path``) — die Ausnahme war deshalb
        folgenlos. Seit ``tools/_archiv/_bootstrap.py`` laufen sie wieder, also
        lebt auch der Show-DB-Footgun wieder: fuenf von ihnen fassen den
        App-State ohne eigenes ``import _gen_env`` an. Der Bootstrap zieht
        ``_gen_env`` inzwischen selbst mit, ``import _bootstrap`` zaehlt hier
        also als Isolation — dieses Gate haelt genau das fest.
        """
        archiv = os.path.join(TOOLS, "_archiv")
        if not os.path.isdir(archiv):
            self.skipTest("tools/_archiv/ existiert nicht")
        offenders = []
        for name in sorted(os.listdir(archiv)):
            if not name.endswith(".py") or name == "_bootstrap.py":
                continue
            path = os.path.join(archiv, name)
            if not os.path.isfile(path):
                continue
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                text = _nur_code(f.read())      # QA-76, s.o.
            if not STATE_API.search(text):
                continue
            if ISOLATION.search(text) or re.search(r"^\s*import _bootstrap\b", text, re.M):
                continue
            offenders.append(name)
        self.assertEqual(offenders, [], (
            "Diese tools/_archiv/-Skripte fassen den App-State ohne Isolation an. "
            "Fix: `import _bootstrap` (zieht _gen_env mit) oder direkt "
            f"`import _gen_env`: {offenders}"))

    def test_bootstrap_pulls_in_gen_env(self):
        """Der Archiv-Bootstrap MUSS _gen_env mitziehen, sonst traegt das Gate oben nicht."""
        boot = os.path.join(TOOLS, "_archiv", "_bootstrap.py")
        if not os.path.isfile(boot):
            self.skipTest("tools/_archiv/_bootstrap.py existiert nicht")
        with open(boot, "r", encoding="utf-8") as f:
            text = f.read()
        self.assertTrue(
            re.search(r"^\s*import _gen_env\b", text, re.M),
            "_bootstrap.py muss `import _gen_env` enthalten — sonst laufen die "
            "wieder startbaren Archiv-Skripte auf der echten data/current_show.db")

    def test_whitelist_entries_still_exist(self):
        ghosts = [n for n in WHITELIST if not os.path.isfile(os.path.join(TOOLS, n))]
        self.assertEqual(ghosts, [], f"Whitelist-Eintraege ohne Datei (aufraeumen): {ghosts}")

    def test_gen_env_actually_sets_show_db(self):
        with open(os.path.join(TOOLS, "_gen_env.py"), "r", encoding="utf-8") as f:
            text = f.read()
        self.assertIn("LIGHTOS_SHOW_DB", text,
                      "_gen_env.py muss die Show-DB-Isolation setzen (STAB-CURSHOW a)")


if __name__ == "__main__":
    unittest.main()
