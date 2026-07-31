"""VCG-01: die Grafik-Auswahl ist nach Kategorien gegliedert (David 2026-08-01).

David wollte „mehr Standard-Grafiken und eine Ordner-Struktur in der Auswahl".
Beim Nachsehen zeigte sich: **die Kategorie stand längst im Manifest** — der
Dialog benutzte sie nur nicht und zeigte eine flache Liste. Die „Ordner" waren
also nicht zu erfinden, sondern anzuzeigen.

Belegt: (1) jede Grafik hat eine Kategorie, (2) die Gruppierung ist vollständig
und verlustfrei, (3) die Reiter-Reihenfolge ist STABIL (sonst springen die
Reiter, sobald eine Grafik dazukommt), (4) eine unbekannte Kategorie fällt
nicht heraus, sondern landet hinten — eine neue Kategorie im Manifest taucht
damit von selbst auf, ohne Code-Änderung, (5) die neuen Pfeile sind wirklich da.
"""
from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from src.core.show import vc_gallery                                # noqa: E402
from src.ui.virtualconsole.vc_gallery_dialog import (               # noqa: E402
    _KAT_TITEL, VCGalleryDialog,
)


class ManifestTest(unittest.TestCase):
    def test_jede_grafik_hat_eine_kategorie(self):
        leer = [e["name"] for e in vc_gallery.entries() if not e.get("category")]
        self.assertEqual(leer, [], "ohne Kategorie landet die Grafik im "
                                   "Sammelreiter statt dort, wo man sie sucht")

    def test_pfeile_sind_vorhanden(self):
        namen = {e["name"] for e in vc_gallery.entries()}
        for n in ("pfeil_hoch", "pfeil_runter", "pfeil_links", "pfeil_rechts",
                  "pfeil_hoch_links", "pfeil_runter_rechts"):
            self.assertIn(n, namen)

    def test_es_gibt_auch_animierte_pfeile(self):
        gifs = {e["name"] for e in vc_gallery.entries() if e.get("kind") == "gif"}
        self.assertTrue({"pfeil_lauf_hoch", "pfeil_lauf_rechts"} <= gifs)


class GruppierungTest(unittest.TestCase):
    def _gruppen(self, ents):
        return VCGalleryDialog._nach_kategorie(ents)

    def test_gruppierung_verliert_nichts(self):
        ents = vc_gallery.entries()
        summe = sum(len(v) for _k, v in self._gruppen(ents))
        self.assertEqual(summe, len(ents))

    def test_reihenfolge_ist_stabil(self):
        """★ Ohne feste Reihenfolge springen die Reiter, sobald eine Grafik
        dazukommt — der Nutzer sucht dann jedes Mal neu."""
        ents = vc_gallery.entries()
        a = [k for k, _ in self._gruppen(ents)]
        b = [k for k, _ in self._gruppen(list(reversed(ents)))]
        self.assertEqual(a, b)
        bekannt = [k for k in a if k in _KAT_TITEL]
        self.assertEqual(bekannt, [k for k in _KAT_TITEL if k in a],
                         "bekannte Kategorien muessen in der Titel-Reihenfolge "
                         "stehen")

    def test_unbekannte_kategorie_faellt_nicht_raus(self):
        """Eine neue Kategorie im Manifest soll von selbst auftauchen, ohne
        dass jemand die Titel-Tabelle pflegt."""
        ents = [{"name": "x", "category": "voellig_neu"},
                {"name": "y", "category": "pfeile"}]
        gruppen = dict(VCGalleryDialog._nach_kategorie(ents))
        self.assertIn("voellig_neu", gruppen)
        reihenfolge = [k for k, _ in VCGalleryDialog._nach_kategorie(ents)]
        self.assertEqual(reihenfolge[0], "pfeile", "bekannte zuerst")

    def test_leere_liste_kippt_nicht(self):
        self.assertEqual(VCGalleryDialog._nach_kategorie([]), [])


if __name__ == "__main__":
    unittest.main()
