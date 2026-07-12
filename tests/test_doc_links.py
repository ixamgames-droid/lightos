"""QA-17-Gate: keine toten relativen Markdown-Querverweise in der Doku.

Verhindert, dass eine Anleitung/README/BACKLOG/ROADMAP/CHANGELOG auf ein nicht
existierendes `.md`/Datei-Ziel verlinkt (Pfad-Tippfehler, umbenannte/gelöschte
Datei). Nutzt tools/check_doc_links.py (Bilder + Archiv-Ordner ausgenommen).
"""
import os
import sys
import unittest

_TOOLS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools")
if _TOOLS not in sys.path:
    sys.path.insert(0, _TOOLS)

import check_doc_links  # noqa: E402


class DocLinksTest(unittest.TestCase):
    def test_no_dead_crossreferences(self):
        dead = check_doc_links.find_dead_links()
        msg = "\n".join(f"  {md}: {ref} -> fehlt {tgt}" for md, ref, tgt in dead)
        self.assertEqual(dead, [], f"Tote Querverweise in der Doku:\n{msg}")


if __name__ == "__main__":
    unittest.main()
