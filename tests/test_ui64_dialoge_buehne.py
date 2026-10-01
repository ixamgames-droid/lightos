"""UI-64 (e–h) — Dialoge und 2D-Bühne: nichts abgeschnitten, nichts überdeckt.

(e) Geräte-Dialog: Die „Typ"-Spalte war 80 px breit und zeigte den rohen
    Datenbank-Bezeichner — aus ``moving_head`` wurde „moving_h…".
(f) DMX-Monitor: Neben der OUT-52-Warnung („⚠ Universe 1 hat keinen Ausgang —
    nur gerechnet") passte die Legende nicht mehr in die Werkzeugzeile und
    wurde rechts abgeschnitten („…Blau/Positic").
(g) 2D-Bühne: Das FX-Badge lag über dem „100%"-Schild, der gelbe Auswahlring
    lief durch das Label unter der Lampe.
(h) Qt-Standardrückfragen zeigten „Yes"/„No", weil kein QTranslator geladen
    wurde.
"""
from __future__ import annotations

import importlib
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QRectF                               # noqa: E402
from PySide6.QtGui import QFont, QFontMetricsF                  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox         # noqa: E402

_app = QApplication.instance() or QApplication([])

from src.core.show.show_file import reset_show                  # noqa: E402
from src.ui.views import live_view                              # noqa: E402
from src.ui.widgets.fixture_browser import (                    # noqa: E402
    FixtureBrowserDialog, typ_anzeige)


# ════════════════════════════════════════════════════════════════════════════
# (e) Geräte-Dialog
# ════════════════════════════════════════════════════════════════════════════

class GeraeteDialogTypSpalteTest(unittest.TestCase):
    def setUp(self):
        reset_show()

    def _dlg(self) -> FixtureBrowserDialog:
        d = FixtureBrowserDialog(1)
        self.addCleanup(d.deleteLater)
        return d

    def test_typ_anzeige_ist_lesbar(self):
        self.assertEqual(typ_anzeige("moving_head"), "Moving Head")
        self.assertEqual(typ_anzeige("led_bar"), "LED-Bar")
        self.assertEqual(typ_anzeige("par"), "PAR")
        self.assertEqual(typ_anzeige("other"), "Sonstiges")
        # Unbekannter Typ: lesbarer Rückfall statt Unterstrich-Bezeichner.
        self.assertEqual(typ_anzeige("pixel_ring"), "Pixel Ring")
        self.assertEqual(typ_anzeige(""), "")
        self.assertEqual(typ_anzeige(None), "")

    def _alle_typtexte(self, tree):
        stack = [tree.topLevelItem(i) for i in range(tree.topLevelItemCount())]
        while stack:
            it = stack.pop()
            if it.text(1):
                yield it.text(1)
            stack.extend(it.child(j) for j in range(it.childCount()))

    def _pruefe_spalte(self, d):
        tree = d._tree
        texte = set(self._alle_typtexte(tree))
        self.assertTrue(texte, "Gerätedatenbank leer — nichts zu prüfen")
        for t in texte:
            self.assertNotIn("_", t, f"roher Datenbank-Bezeichner: {t!r}")
        fm = tree.fontMetrics()
        breitester = max(texte, key=fm.horizontalAdvance)
        # Mindestens Textbreite plus Zellrand (Qt zieht links+rechts je ~3 px
        # Innenabstand ab, bevor es mit „…" kürzt).
        self.assertGreaterEqual(
            tree.columnWidth(1), fm.horizontalAdvance(breitester) + 12,
            f"Typ-Spalte zu schmal für {breitester!r}")

    def test_baum_typspalte_passt(self):
        self._pruefe_spalte(self._dlg())

    def test_suche_typspalte_passt(self):
        d = self._dlg()
        d._search.setText("moving")
        self.assertIn("Moving Head", set(self._alle_typtexte(d._tree)))
        self._pruefe_spalte(d)


# ════════════════════════════════════════════════════════════════════════════
# (f) DMX-Monitor
# ════════════════════════════════════════════════════════════════════════════

class _OmOhneAusgang:
    def sendet_wirklich(self, _univ):
        return False

    def sende_probleme(self):
        return []


class DmxMonitorLegendeTest(unittest.TestCase):
    def setUp(self):
        reset_show()

    def _view(self, breite: int):
        from src.ui.views.dmx_monitor_view import DmxMonitorView
        v = DmxMonitorView()
        self.addCleanup(v.deleteLater)
        v._timer.stop()
        v._update_ausgang_label(_OmOhneAusgang(), 1, False)
        self.assertIn("keinen Ausgang", v._lbl_ausgang.text())
        v.resize(breite, 700)
        v.show()
        _app.processEvents()
        self.addCleanup(v.hide)
        return v

    def _legende_ganz_sichtbar(self, v):
        leg = v._lbl_legend
        # Die Legende liegt ganz im Fenster …
        self.assertLessEqual(leg.geometry().right(), v.width())
        self.assertGreaterEqual(leg.geometry().left(), 0)
        # … und ihr Text passt hinein: einzeilig in die Breite, oder umbrochen
        # mit genug Höhe.
        fm = leg.fontMetrics()
        if leg.wordWrap():
            self.assertGreaterEqual(leg.height(), leg.heightForWidth(leg.width()))
        else:
            self.assertGreaterEqual(leg.width(), fm.horizontalAdvance(leg.text()),
                                    "Legende abgeschnitten")

    def test_1600px_mit_warnung(self):
        self._legende_ganz_sichtbar(self._view(1600))

    def test_schmales_fenster_bricht_um(self):
        """Gegenprobe mit Reserve (höhere Skalierung/breitere Schrift auf dem
        Betreiber-Rechner): auch bei 900 px bleibt die Legende vollständig."""
        v = self._view(900)
        self._legende_ganz_sichtbar(v)
        # Eigene Zeile: unterhalb der Warnung, nicht daneben.
        self.assertGreaterEqual(v._lbl_legend.geometry().top(),
                                v._lbl_ausgang.geometry().bottom())


# ════════════════════════════════════════════════════════════════════════════
# (g) 2D-Bühne: Texte und Ringe überdecken sich nicht
# ════════════════════════════════════════════════════════════════════════════

def _pct_rect(size, tscale, text="100%") -> QRectF:
    """Tatsächliche Fläche des zentrierten %-Texts im %-Schild."""
    f = QFont("Arial"); f.setPointSizeF(7 * tscale)
    fm = QFontMetricsF(f)
    w = fm.horizontalAdvance(text)
    o = live_view.oben_rect(size, tscale)
    return QRectF(-w / 2, o.bottom() - fm.height(), w, fm.height())


class BuehneGeometrieTest(unittest.TestCase):
    GROESSEN = (20.0, 30.0, 45.0, 60.0)
    ZOOMS = (0.5, 1.0, 2.0)

    def test_fx_badge_liegt_neben_dem_prozentschild(self):
        for size in self.GROESSEN:
            for zoom in self.ZOOMS:
                ts = 1.0 / zoom
                pct = _pct_rect(size, ts)
                badge = live_view.fx_badge_rect(size, ts, pct.width())
                self.assertFalse(
                    badge.intersects(pct),
                    f"FX-Badge {badge} überdeckt %-Text {pct} "
                    f"(size={size}, zoom={zoom})")

    def test_label_beginnt_unter_allen_ringen(self):
        for size in self.GROESSEN:
            for zoom in self.ZOOMS:
                ts = 1.0 / zoom
                lab = live_view.label_rect(size, ts)
                # Auswahlring 0.70 (Stift 3), Effekt 0.72 (Stift 2),
                # Gruppe 0.82 (Stift 4) — jeweils äußerer Rand.
                for r_aussen in (size * 0.70 + 1.5, size * 0.72 + 1.0,
                                 size * 0.82 + 2.0):
                    self.assertGreater(lab.top(), r_aussen,
                                       f"size={size}, zoom={zoom}")

    def test_prozentschild_und_badge_ueber_allen_ringen(self):
        for size in self.GROESSEN:
            for zoom in self.ZOOMS:
                ts = 1.0 / zoom
                grenze = -live_view.ring_aussenradius(size)
                self.assertLess(live_view.oben_rect(size, ts).bottom(), grenze)
                badge = live_view.fx_badge_rect(size, ts, 30 * ts)
                self.assertLess(badge.bottom(), grenze)

    def test_renderer_zeichnet_mit_allem_ohne_fehler(self):
        """Rauchtest: selektiert + hervorgehoben + Effekt + 100 %."""
        from PySide6.QtGui import QImage, QPainter, QColor
        img = QImage(200, 200, QImage.Format.Format_ARGB32)
        img.fill(0)
        p = QPainter(img)
        try:
            live_view.FixtureRenderer.draw(
                p, "moving_head", 100, 100, 30, QColor("#ff8800"),
                intensity=255, label="12", selected=True, highlighted=True,
                effects=[object(), object()], lod=0)
        finally:
            p.end()


# ════════════════════════════════════════════════════════════════════════════
# (h) Qt-Standardknöpfe deutsch
# ════════════════════════════════════════════════════════════════════════════

class QtUebersetzungTest(unittest.TestCase):
    def setUp(self):
        self.main = importlib.import_module("main")

    def _knoepfe(self):
        mb = QMessageBox(QMessageBox.Icon.Question, "Neue Show",
                         "Aktuelle Show verwerfen?",
                         QMessageBox.StandardButton.Yes
                         | QMessageBox.StandardButton.No)
        self.addCleanup(mb.deleteLater)
        return (mb.button(QMessageBox.StandardButton.Yes).text(),
                mb.button(QMessageBox.StandardButton.No).text(),
                mb.windowTitle(), mb.text())

    def test_knoepfe_deutsch_eigene_texte_unveraendert(self):
        tr = self.main._install_qt_translator(_app)
        self.assertIsNotNone(tr, "qtbase_de.qm nicht gefunden in "
                             f"{self.main._qt_uebersetzungs_ordner()}")
        self.addCleanup(_app.removeTranslator, tr)
        ja, nein, titel, text = self._knoepfe()
        self.assertEqual(ja.replace("&", ""), "Ja")
        self.assertEqual(nein.replace("&", ""), "Nein")
        # Eigene Texte bleiben, wie sie sind.
        self.assertEqual(titel, "Neue Show")
        self.assertEqual(text, "Aktuelle Show verwerfen?")

    def test_fehlende_datei_kein_fehler(self):
        """Rückfall: ohne Übersetzungsordner bleibt es still bei Englisch."""
        orig = self.main._qt_uebersetzungs_ordner
        self.main._qt_uebersetzungs_ordner = lambda: ["/gibt/es/nicht"]
        self.addCleanup(setattr, self.main, "_qt_uebersetzungs_ordner", orig)
        self.assertIsNone(self.main._install_qt_translator(_app))

    def test_main_ruft_uebersetzer_beim_start(self):
        import inspect
        quelle = inspect.getsource(self.main.main)
        self.assertIn("_install_qt_translator(app)", quelle)


if __name__ == "__main__":
    unittest.main()
