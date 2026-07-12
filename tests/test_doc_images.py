"""DOC-10-Gate: keine toten Bild-Links in der Doku.

Verhindert, dass eine Anleitung/README ein Bild referenziert, das nicht existiert
(z. B. Pfad-Tippfehler oder geloeschtes Bild). Nutzt tools/check_doc_images.py.
"""
import os
import sys
import unittest

_TOOLS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools")
if _TOOLS not in sys.path:
    sys.path.insert(0, _TOOLS)

import check_doc_images  # noqa: E402


class DocImageLinksTest(unittest.TestCase):
    def test_no_dead_image_links(self):
        dead = check_doc_images.find_dead_links()
        msg = "\n".join(f"  {md}: {ref} -> fehlt {tgt}" for md, ref, tgt in dead)
        self.assertEqual(dead, [], f"Tote Bild-Links in der Doku:\n{msg}")


if __name__ == "__main__":
    unittest.main()
