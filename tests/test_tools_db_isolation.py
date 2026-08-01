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


class DbIsolationLintTest(unittest.TestCase):
    def test_state_touching_tools_are_isolated(self):
        offenders = []
        for name, path in _tool_scripts():
            if name in WHITELIST:
                continue
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                text = f.read()
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
                text = f.read()
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
