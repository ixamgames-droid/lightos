"""UI-25: faire Max-Min-Verteilung der Sektions-Tab-Breiten.

Vorher verteilte QHBoxLayout den Platzmangel unfair — der kurze Tab „E/A"
kollabierte zu reinem „…", waehrend der lange „Virtual Console" voll blieb. Jetzt
teilt der Tab-Container die Breite fair auf: kurze Labels behalten ihren Volltext,
nur die langen Titel eliden, und KEIN Tab zeigt je ein reines „…".
"""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from src.ui.main_window import _allocate_tab_widths

_app = QApplication.instance() or QApplication([])


class TestAllocatePure(unittest.TestCase):
    """Reine Verteil-Funktion (kein Qt) — der Kern der Fairness."""

    def test_all_fit_full(self):
        self.assertEqual(_allocate_tab_widths([50, 60, 70], 500, 56), [50.0, 60.0, 70.0])

    def test_short_kept_long_shrinks(self):
        # klar kurze (60,70) bleiben voll (unter dem fairen Level), nur die langen
        # (200,200) schrumpfen auf ein gemeinsames Level.
        full = [60, 70, 200, 200]
        w = _allocate_tab_widths(full, 400, 56)
        self.assertAlmostEqual(w[0], 60.0, places=1)   # kurz -> voll
        self.assertAlmostEqual(w[1], 70.0, places=1)   # kurz -> voll
        self.assertLess(w[2], 200.0)                   # lang -> elidiert
        self.assertLess(w[3], 200.0)
        self.assertAlmostEqual(w[2], w[3], places=3)   # lange teilen sich gleich
        self.assertLessEqual(sum(w), 400.0 + 1e-6)     # nie Ueberlauf

    def test_never_overflow_even_when_extremely_tight(self):
        full = [100, 120, 160, 220, 170, 130, 76, 76]
        for avail in (50, 200, 448, 600, 900, 1064, 2000):
            w = _allocate_tab_widths(full, avail, 56)
            self.assertLessEqual(sum(w), avail + 1e-6, f"Ueberlauf bei avail={avail}")
            for wi, fi in zip(w, full):
                self.assertLessEqual(wi, fi + 1e-6)    # nie breiter als Volltext

    def test_floor_respected_when_room(self):
        # solange avail > n*floor bleibt jeder Tab >= floor
        full = [300, 300, 300, 300]
        w = _allocate_tab_widths(full, 400, 56)        # 400 > 4*56=224
        self.assertTrue(all(wi >= 56.0 - 1e-6 for wi in w))

    def test_monotonic_more_space_never_shrinks(self):
        full = [100, 120, 160, 220, 170, 130, 76, 76]
        prev = _allocate_tab_widths(full, 500, 56)
        for avail in (600, 800, 1000, 1064, 1400):
            cur = _allocate_tab_widths(full, avail, 56)
            for a, b in zip(prev, cur):
                self.assertGreaterEqual(b + 1e-6, a, "mehr Platz darf keinen Tab schmaler machen")
            prev = cur

    def test_empty(self):
        self.assertEqual(_allocate_tab_widths([], 500, 56), [])


class TestSectionTabsFairInWindow(unittest.TestCase):
    """Echtes Fenster: der kurze Tab „E/A" bleibt lesbar (kein reines „…"),
    waehrend die langen Titel eliden — genau die vorher unfaire Situation."""

    @classmethod
    def setUpClass(cls):
        from src.ui.main_window import MainWindow
        cls.win = MainWindow()
        cls.win.show()
        for _ in range(4):
            _app.processEvents()

    @classmethod
    def tearDownClass(cls):
        try:
            cls.win.close()
            cls.win.deleteLater()
        except Exception:
            pass
        for _ in range(2):
            _app.processEvents()
        try:
            from src.core.show.show_file import reset_show
            reset_show()
        except Exception:
            pass
        for _ in range(2):
            _app.processEvents()

    def _resize(self, w, h=896):
        self.win.resize(w, h)
        for _ in range(5):
            _app.processEvents()

    def _tab(self, needle):
        return next(b for b in self.win._section_btns if needle in b._full_text)

    def test_no_tab_shows_pure_ellipsis_at_1344(self):
        self._resize(1344)
        for b in self.win._section_btns:
            self.assertNotIn(b.text(), ("…", "...", ""),
                             f"Tab {b._full_text!r} zeigt reines '…' bei 1344px")

    def test_short_label_never_more_elided_than_long(self):
        # Fairness FONT-UNABHAENGIG (keine feste Pixelbreite -> kein Widerspruch
        # zu TestSectionButtonsFullTextAt1440, Codex-Fund CDX): sobald es eng wird
        # (Container kann nicht alle Volltexte fassen), darf der KURZE Tab (E/A)
        # nie staerker gekuerzt sein als der LANGE (Virtual Console). Max-Min gibt
        # kurzen Labels Vorrang -> ihr sichtbarer Anteil ist >= der der langen.
        def frac(b):
            return len(b.text().rstrip("…")) / max(1, len(b._full_text))
        checked = False
        for W in (1000, 1100, 1200, 1300, 1344):
            self._resize(820)          # neutralisieren, dann Ziel -> hysteresefrei
            self._resize(W)
            tabs = self.win._section_btns
            full_sum = sum(b._full_text_size_hint().width() for b in tabs)
            if full_sum <= self.win._tab_container.width():
                continue               # passt alles -> keine Enge, ueberspringen
            ea, vc = self._tab("E/A"), self._tab("Virtual")
            self.assertGreaterEqual(
                frac(ea) + 1e-9, frac(vc),
                f"@{W}px: kurzer Tab staerker gekuerzt als langer (unfair)")
            self.assertNotIn(vc.text(), ("…", "...", ""))   # nie reines '…'
            checked = True
        self.assertTrue(checked, "keine enge Breite im Testbereich gefunden")

    def test_full_text_when_plenty_of_room(self):
        self._resize(2600)
        for b in self.win._section_btns:
            self.assertEqual(b.text(), b._full_text,
                             f"bei viel Platz muss {b._full_text!r} voll stehen")

    def test_no_overflow_and_no_overlap_across_width_band(self):
        # Review-Regression: pro-Tab-round() liess die Breiten-Summe > Container
        # werden -> Tabs liefen in die GM-Gruppe. Ueber ein BREITES Raster
        # (nicht nur 1344) pruefen: (a) Summe der Tab-Breiten <= Container (kein
        # Ueberlauf), (b) koordinaten-korrekt (alles ins Fenster gemappt) kein
        # Tab/GM-Ueberlapp.
        gm = self.win._slider_gm.parentWidget()
        for W in (1000, 1100, 1200, 1280, 1300, 1344, 1366, 1428, 1500):
            # doppelter Resize -> settle ohne Hysterese-Artefakt
            self._resize(820)
            self._resize(W)
            tabs = self.win._section_btns
            self.assertLessEqual(
                sum(b.width() for b in tabs), self.win._tab_container.width(),
                f"Tab-Breiten-Summe ueberlaeuft den Container bei {W}px")
            spans = []
            for w in list(tabs) + [gm]:
                tl = w.mapTo(self.win, w.rect().topLeft())
                spans.append((tl.x(), tl.x() + w.width()))
            for i in range(len(spans)):
                for j in range(i + 1, len(spans)):
                    self.assertLessEqual(
                        min(spans[i][1], spans[j][1]) - max(spans[i][0], spans[j][0]), 0,
                        f"Tabs/GM-Gruppe ueberlappen bei {W}px")


if __name__ == "__main__":
    unittest.main()
