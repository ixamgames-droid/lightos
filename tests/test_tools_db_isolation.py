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
