"""Frische-Gate fuer tools/README.md (generiert von tools/gen_tools_index.py).

Faellt rot, wenn ein Tool in tools/ (oder tools/_archiv/) auftaucht bzw.
verschwindet, ohne dass der Index regeneriert wurde. Absichtlich NUR eine
Vollstaendigkeits-Pruefung (Dateinamen), kein Byte-Vergleich — Beschreibungs-
Aenderungen alleine reissen das Gate nicht.
"""
import os
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = os.path.join(REPO, "tools")
README = os.path.join(TOOLS, "README.md")
HINT = "-> venv/Scripts/python.exe tools/gen_tools_index.py laufen lassen"


def _scripts(folder):
    if not os.path.isdir(folder):
        return []
    return [n for n in os.listdir(folder)
            if n.endswith((".py", ".ps1")) and n != "__init__.py"
            and os.path.isfile(os.path.join(folder, n))]


class ToolsIndexTest(unittest.TestCase):
    def _readme(self):
        self.assertTrue(os.path.isfile(README), f"tools/README.md fehlt {HINT}")
        with open(README, "r", encoding="utf-8") as f:
            return f.read()

    def test_every_tool_is_listed(self):
        text = self._readme()
        missing = [n for n in _scripts(TOOLS) if f"`{n}`" not in text]
        self.assertEqual(missing, [], f"Tools ohne Index-Eintrag: {missing} {HINT}")

    def test_every_archived_tool_is_listed(self):
        text = self._readme()
        missing = [n for n in _scripts(os.path.join(TOOLS, "_archiv"))
                   if f"`_archiv/{n}`" not in text and f"`{n}`" not in text]
        self.assertEqual(missing, [], f"Archiv-Tools ohne Index-Eintrag: {missing} {HINT}")

    def test_no_ghost_entries(self):
        import re
        text = self._readme()
        listed = set(re.findall(r"`(?:_archiv/)?([\w.\-]+\.(?:py|ps1))`", text))
        existing = set(_scripts(TOOLS)) | set(_scripts(os.path.join(TOOLS, "_archiv")))
        # Generator-Selbstnennung u. ae. herausrechnen: nur echte Geister melden.
        ghosts = sorted(n for n in listed if n not in existing)
        self.assertEqual(ghosts, [], f"Index listet nicht (mehr) existierende Tools: {ghosts} {HINT}")


if __name__ == "__main__":
    unittest.main()
