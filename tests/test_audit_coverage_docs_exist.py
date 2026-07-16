"""DOC-10: der Audit-Coverage-Tracker (docs/AUDIT_COVERAGE.md) darf nur auf
existierende Docs verlinken. Faengt Umbenennungen/Tippfehler, die den Tracker
still veralten liessen.
"""
import os
import re
import unittest

_DOCS_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "docs"))
_TRACKER = os.path.join(_DOCS_DIR, "AUDIT_COVERAGE.md")

# Markdown-Links [text](ziel) — nur relative .md-Ziele pruefen (keine http/absoluten).
_LINK_RE = re.compile(r"\]\(([^)]+)\)")


class TestAuditCoverageLinks(unittest.TestCase):
    def test_tracker_exists(self):
        self.assertTrue(os.path.isfile(_TRACKER), f"AUDIT_COVERAGE.md fehlt: {_TRACKER}")

    def test_all_referenced_md_docs_exist(self):
        with open(_TRACKER, "r", encoding="utf-8") as f:
            text = f.read()
        missing = []
        checked = 0
        for target in _LINK_RE.findall(text):
            target = target.strip()
            # Anchor abschneiden, externe/absolute Ziele ueberspringen.
            path = target.split("#", 1)[0].strip()
            if not path or path.startswith(("http://", "https://", "/")):
                continue
            if not path.lower().endswith(".md"):
                continue
            checked += 1
            resolved = os.path.normpath(os.path.join(_DOCS_DIR, path))
            if not os.path.isfile(resolved):
                missing.append(path)
        self.assertGreater(checked, 0, "keine relativen .md-Links im Tracker gefunden (Regex kaputt?)")
        self.assertEqual(missing, [], f"Im Audit-Tracker verlinkte Docs fehlen: {missing}")


if __name__ == "__main__":
    unittest.main()
