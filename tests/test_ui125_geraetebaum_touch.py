"""UI-125 (Touch-Audit C-10): „Gerät hinzufügen“ — Baum zugeklappt, ein Tipp klappt auf.

Geprueft mit dem echten Dialog (offscreen) und einer erfundenen
Geraetebibliothek (``fdb`` im Modul ersetzt) — die Tests brauchen weder die
echte ``fixtures.db`` noch eine frisch geseedete:

* Der Baum startet zugeklappt.
* Ein Fingertipp auf einen Hersteller klappt auf, ein zweiter wieder zu
  (ueber den Anwendungsfilter aus ``ziehen_scrollen``, der den Druck am
  Finger zurueckhaelt und beim Loslassen nachreicht).
* Ein Wisch scrollt den Baum und waehlt kein Geraet.
* Ein Tipp auf ein Geraet waehlt es.
* Maus: Klick auf den Namen klappt auf/zu, Doppelklick klappt genau einmal
  (nicht auf und gleich wieder zu), das Dreieck schaltet wie bisher.
* Suche: Treffer stehen flach und sichtbar da.
* Touch-Modus: Zeilen >= 40 px (gemessen), mit der Maus unveraendert.
"""
from __future__ import annotations

import os
import tempfile
import types
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
# Sicherheitsnetz: nie die echte Bibliothek oeffnen (der Test ersetzt ``fdb``).
os.environ.setdefault("LIGHTOS_FIXTURE_DB",
                      os.path.join(tempfile.mkdtemp(prefix="ui125_"), "x.db"))

from PySide6.QtCore import QEvent, QPoint, QPointF, Qt               # noqa: E402
from PySide6.QtGui import QMouseEvent                                # noqa: E402
from PySide6.QtTest import QTest                                     # noqa: E402
from PySide6.QtWidgets import QApplication                           # noqa: E402

from src.ui import touch_keyboard as tk                              # noqa: E402
from src.ui import ziehen_scrollen as zs                             # noqa: E402
from src.ui.widgets import fixture_browser as fb                     # noqa: E402

_app = QApplication.instance() or QApplication([])

_HERSTELLER = 30
_JE = 4


def _fake_fdb():
    """Kleine erfundene Bibliothek: 30 Hersteller mit je 4 Geraeten."""
    hersteller = [types.SimpleNamespace(id=h, name=f"Hersteller {h:02d}")
                  for h in range(1, _HERSTELLER + 1)]
    profile = {}
    for m in hersteller:
        for j in range(_JE):
            fid = m.id * 100 + j
            modus = types.SimpleNamespace(id=fid * 10, name="Standard", channel_count=4)
            profile[fid] = types.SimpleNamespace(
                id=fid, name=f"Par {m.id}-{j}", short_name=f"P{fid}",
                fixture_type="par", manufacturer=m, modes=[modus], source="user")

    def nach_hersteller(mid):
        return [p for p in profile.values() if p.manufacturer.id == mid]

    def suche(q):
        q = q.lower()
        return [p for p in profile.values()
                if q in p.name.lower() or q in p.manufacturer.name.lower()]

    def kein_engine():
        raise RuntimeError("keine echte DB im Test")

    return types.SimpleNamespace(
        get_all_manufacturers=lambda: list(hersteller),
        get_fixtures_by_manufacturer=nach_hersteller,
        abgeloeste_profile=lambda: {},
        search_fixtures=suche,
        get_fixture=lambda fid: profile.get(fid),
        get_modes=lambda fid: list(profile[fid].modes),
        engine=kein_engine,
    )


class GeraetebaumTouchTest(unittest.TestCase):

    def setUp(self):
        self.f = zs.einrichten(_app)
        self.f.aktiv = True
        self.addCleanup(self.f._abbrechen)
        self.addCleanup(lambda: getattr(self.f, "_menue_aus", lambda: None)())
        self.addCleanup(setattr, self.f, "_menue_schlucken", False)
        self.addCleanup(self.f.schwung_stoppen)
        p = mock.patch.object(fb, "fdb", _fake_fdb())
        p.start()
        self.addCleanup(p.stop)
        p = mock.patch.object(fb.FixtureBrowserDialog, "_universum_vorbelegung",
                              lambda self: 1)
        p.start()
        self.addCleanup(p.stop)
        self.addCleanup(tk.setze_touch_modus, tk.is_touch_mode())
        self.dev = QTest.createTouchDevice()

    def _dlg(self, touch: bool = False) -> fb.FixtureBrowserDialog:
        tk.setze_touch_modus(touch)
        d = fb.FixtureBrowserDialog(1)
        self.addCleanup(d.deleteLater)
        self.addCleanup(d.close)
        d.resize(800, 520)
        d.show()
        QApplication.processEvents()
        return d

    @staticmethod
    def _oben(d):
        t = d._tree
        return [t.topLevelItem(i) for i in range(t.topLevelItemCount())]

    @staticmethod
    def _textpunkt(tree, item) -> QPoint:
        r = tree.visualItemRect(item)
        return QPoint(r.left() + 30, r.center().y())

    def _tipp(self, v, p: QPoint):
        QTest.touchEvent(v, self.dev).press(0, p, v).commit()
        QTest.touchEvent(v, self.dev).release(0, p, v).commit()
        QApplication.processEvents()

    # ── Start ───────────────────────────────────────────────────────────────

    def test_startet_zugeklappt(self):
        d = self._dlg()
        oben = self._oben(d)
        self.assertEqual(len(oben), _HERSTELLER)
        self.assertTrue(all(it.childCount() == _JE for it in oben))
        self.assertFalse(any(it.isExpanded() for it in oben), "Baum zugeklappt")
        self.assertIsNone(d._selected_profile)

    # ── Finger ──────────────────────────────────────────────────────────────

    def test_finger_tipp_klappt_auf_und_zu(self):
        d = self._dlg(touch=True)
        t, v = d._tree, d._tree.viewport()
        h = self._oben(d)[2]
        self._tipp(v, self._textpunkt(t, h))
        self.assertTrue(h.isExpanded(), "Tipp klappt auf")
        self.assertIsNone(d._selected_profile, "Hersteller ist kein Geraet")
        self.assertFalse(d._btn_add.isEnabled())
        # zweiter Tipp (mit Pause, damit es kein Doppeltippen ist)
        QTest.qWait(QApplication.doubleClickInterval() + 50)
        self._tipp(v, self._textpunkt(t, h))
        self.assertFalse(h.isExpanded(), "zweiter Tipp klappt zu")

    def test_finger_tipp_auf_geraet_waehlt_es(self):
        d = self._dlg(touch=True)
        t, v = d._tree, d._tree.viewport()
        h = self._oben(d)[1]
        self._tipp(v, self._textpunkt(t, h))
        self.assertTrue(h.isExpanded())
        QTest.qWait(QApplication.doubleClickInterval() + 50)
        kind = h.child(1)
        self._tipp(v, self._textpunkt(t, kind))
        self.assertIs(t.currentItem(), kind)
        self.assertIsNotNone(d._selected_profile)
        self.assertEqual(d._selected_profile.id, kind.data(0, Qt.ItemDataRole.UserRole))
        self.assertTrue(d._btn_add.isEnabled())
        self.assertTrue(h.isExpanded(), "Geraet antippen klappt nichts zu")

    def test_finger_wisch_scrollt_und_waehlt_nichts(self):
        d = self._dlg(touch=True)
        t, v = d._tree, d._tree.viewport()
        for it in self._oben(d)[:10]:
            it.setExpanded(True)
        QApplication.processEvents()
        bar = t.verticalScrollBar()
        self.assertGreater(bar.maximum(), 0, "Baum muss scrollen koennen")
        kind = self._oben(d)[0].child(2)
        start = self._textpunkt(t, kind)
        aufgeklappt = [it.isExpanded() for it in self._oben(d)]
        QTest.touchEvent(v, self.dev).press(0, start, v).commit()
        for dy in range(15, 150, 15):
            QTest.touchEvent(v, self.dev).move(0, start - QPoint(0, dy), v).commit()
        QTest.touchEvent(v, self.dev).release(0, start - QPoint(0, 135), v).commit()
        self.f.schwung_stoppen()
        QApplication.processEvents()
        self.assertGreater(bar.value(), 0, "Wisch scrollt")
        self.assertIsNone(d._selected_profile, "Wisch waehlt kein Geraet")
        self.assertFalse(d._btn_add.isEnabled())
        self.assertEqual([it.isExpanded() for it in self._oben(d)], aufgeklappt,
                         "Wisch klappt nichts auf/zu")

    def test_finger_wisch_ueber_hersteller_klappt_nicht(self):
        d = self._dlg(touch=True)
        t, v = d._tree, d._tree.viewport()
        h = self._oben(d)[8]
        start = self._textpunkt(t, h)
        QTest.touchEvent(v, self.dev).press(0, start, v).commit()
        for dy in range(15, 150, 15):
            QTest.touchEvent(v, self.dev).move(0, start - QPoint(0, dy), v).commit()
        QTest.touchEvent(v, self.dev).release(0, start - QPoint(0, 135), v).commit()
        self.f.schwung_stoppen()
        QApplication.processEvents()
        self.assertGreater(t.verticalScrollBar().value(), 0, "Wisch scrollt")
        self.assertFalse(any(it.isExpanded() for it in self._oben(d)))

    def test_touch_zielgroessen(self):
        d = self._dlg(touch=True)
        t = d._tree
        h = self._oben(d)[0]
        h.setExpanded(True)
        QApplication.processEvents()
        for it in (h, h.child(0)):
            self.assertGreaterEqual(t.visualItemRect(it).height(), fb.TOUCH_ZEILE,
                                    f"Zeile {it.text(0)!r} zu niedrig")
        self.assertGreaterEqual(t.indentation(), fb.TOUCH_EINZUG)

    # ── Maus ────────────────────────────────────────────────────────────────

    def test_maus_ohne_touch_unveraendert_klein(self):
        d = self._dlg(touch=False)
        self.assertEqual(d._tree.styleSheet(), "")
        self.assertLess(d._tree.indentation(), fb.TOUCH_EINZUG)

    def test_maus_klick_doppelklick_und_dreieck(self):
        d = self._dlg()
        t, v = d._tree, d._tree.viewport()
        h = self._oben(d)[3]
        p = self._textpunkt(t, h)
        QTest.mouseClick(v, Qt.MouseButton.LeftButton, pos=p)
        self.assertTrue(h.isExpanded(), "Klick klappt auf")
        QTest.qWait(QApplication.doubleClickInterval() + 50)
        QTest.mouseClick(v, Qt.MouseButton.LeftButton, pos=p)
        self.assertFalse(h.isExpanded(), "Klick klappt zu")
        QTest.qWait(QApplication.doubleClickInterval() + 50)
        # Doppelklick wie gewohnt: am Ende aufgeklappt (nicht auf+zu)
        QTest.mouseClick(v, Qt.MouseButton.LeftButton, pos=p)
        QTest.mouseDClick(v, Qt.MouseButton.LeftButton, pos=p)
        self.assertTrue(h.isExpanded(), "Doppelklick klappt auf")
        QTest.qWait(QApplication.doubleClickInterval() + 50)
        # Dreieck links neben dem Namen schaltet genau einmal
        r = t.visualItemRect(h)
        dreieck = QPoint(r.left() - t.indentation() // 2, r.center().y())
        QTest.mouseClick(v, Qt.MouseButton.LeftButton, pos=dreieck)
        self.assertFalse(h.isExpanded(), "Dreieck klappt zu")

    def test_maus_ziehen_im_baum_waehlt_nichts_neu(self):
        """Maus-Zug auf der Baumflaeche scrollt (UI-110) wie bisher."""
        d = self._dlg()
        t, v = d._tree, d._tree.viewport()
        for it in self._oben(d):
            it.setExpanded(True)
        QApplication.processEvents()
        start = self._textpunkt(t, self._oben(d)[0].child(1))
        g0 = v.mapToGlobal(start)
        ts = [5000]

        def maus(typ, pos, knoepfe):
            ts[0] += 10
            ev = QMouseEvent(typ, QPointF(pos), QPointF(g0 + (pos - start)),
                             Qt.MouseButton.LeftButton, knoepfe,
                             Qt.KeyboardModifier.NoModifier)
            ev.setTimestamp(ts[0])
            QApplication.sendEvent(v, ev)

        maus(QEvent.Type.MouseButtonPress, start, Qt.MouseButton.LeftButton)
        for dy in range(10, 110, 10):
            maus(QEvent.Type.MouseMove, start - QPoint(0, dy), Qt.MouseButton.LeftButton)
        maus(QEvent.Type.MouseButtonRelease, start - QPoint(0, 100), Qt.MouseButton.NoButton)
        self.f.schwung_stoppen()
        self.assertGreater(t.verticalScrollBar().value(), 0)

    # ── Suche ───────────────────────────────────────────────────────────────

    def test_suche_zeigt_treffer_sichtbar(self):
        d = self._dlg(touch=True)
        d._search.setText("Par 7-")
        QApplication.processEvents()
        oben = self._oben(d)
        self.assertEqual(len(oben), _JE)
        t = d._tree
        for it in oben:
            self.assertFalse(it.isHidden())
            self.assertTrue(t.visualItemRect(it).isValid(), "Treffer sichtbar")
            self.assertIsNotNone(it.data(0, Qt.ItemDataRole.UserRole))
        # Suche leeren: wieder der zugeklappte Baum
        d._search.setText("")
        QApplication.processEvents()
        self.assertEqual(len(self._oben(d)), _HERSTELLER)
        self.assertFalse(any(it.isExpanded() for it in self._oben(d)))


if __name__ == "__main__":
    unittest.main()
