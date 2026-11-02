"""VCB-35: Namenswahl unter „Erweitert" traegt sich in „Ziele" ein.

Befund: Fuer Umschalten/Flash/Effekt-Aktion/„Alle Weiss" bindet apply() den
Knopf an die Liste „Ziele" (Titel „Schaltet mit"). Die Wahl „Funktion / Chase
(Name)" unter „Erweitert" setzte nur das Roh-ID-Feld — bei leerer Liste war der
Knopf nach OK ungebunden, ohne Meldung. Entscheidung (b): die Namenswahl traegt
sich LIVE sichtbar in „Ziele" ein, im Dialog wie im Inspector. Leeren von
„Ziele" loest den Knopf weiterhin.

Es wird nichts gesendet; die Funktionsliste der Namens-Combo ist gestellt.
"""
from __future__ import annotations

import os
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QComboBox, QWidget  # noqa: E402

from src.ui.virtualconsole.target_list_editor import TargetListEditor  # noqa: E402
from src.ui.virtualconsole.vc_button import ButtonAction, VCButton      # noqa: E402

_app = QApplication.instance() or QApplication([])

import pytest as _pytest_xplat15                          # noqa: E402
from _qt_lifecycle import destroy_all_top_level_widgets  # noqa: E402  XPLAT-15


@_pytest_xplat15.fixture(autouse=True)
def _xplat15_no_leaked_widgets():
    yield
    destroy_all_top_level_widgets(QApplication.instance())


_FUNKTIONEN = [(7, "Lauflicht"), (9, "Farbwechsel")]


def _gestellte_funktionen(self, combo):
    for fid, name in _FUNKTIONEN:
        combo.addItem(f"{name}  [chaser #{fid}]", fid)


def _namens_combo(widgets):
    for cb in widgets:
        if isinstance(cb, QComboBox) and cb.count() and \
                cb.itemText(0) == "(per Erweitert / Roh-ID)":
            return cb
    raise AssertionError("Namens-Combo nicht gefunden")


def _waehle(combo, fid):
    idx = combo.findData(fid)
    assert idx >= 0
    combo.setCurrentIndex(idx)
    _app.processEvents()


def _ziele(settings):
    for _key, _t, _c, _n, rows in settings["sections"]:
        for _lbl, w in rows:
            if isinstance(w, TargetListEditor):
                return w
    raise AssertionError("Ziel-Liste nicht gefunden")


def _alle_widgets(settings):
    out = []
    for _key, _t, _c, _n, rows in settings["sections"]:
        out.extend(w for _lbl, w in rows)
    return out


@mock.patch.object(VCButton, "_populate_function_combo", _gestellte_funktionen)
class DialogTest(unittest.TestCase):
    """Modaler Dialog: _build_settings(live=False) + apply() beim OK."""

    def _settings(self, b):
        self.host = QWidget()
        return b._build_settings(self.host, live=False)

    def test_namenswahl_bindet_knopf_bei_leeren_zielen(self):
        for action in (ButtonAction.FUNCTION_TOGGLE, ButtonAction.FUNCTION_FLASH,
                       ButtonAction.EFFECT_ACTION, ButtonAction.ALL_WHITE):
            with self.subTest(action=action):
                b = VCButton("Neu")
                b.action = action
                s = self._settings(b)
                ziele = _ziele(s)
                self.assertEqual(ziele.ids(), [])
                _waehle(_namens_combo(_alle_widgets(s)), 7)
                self.assertEqual(ziele.ids(), [7], "Namenswahl muss in „Ziele“ stehen")
                s["apply"]()
                self.assertEqual(b.function_id, 7)
                self.assertEqual(b.function_ids, [])

    def test_namenswahl_ersetzt_haupt_ziel_und_behaelt_weitere(self):
        b = VCButton("B")
        b.action = ButtonAction.FUNCTION_TOGGLE
        b.function_id, b.function_ids = 7, [11]
        s = self._settings(b)
        _waehle(_namens_combo(_alle_widgets(s)), 9)
        self.assertEqual(_ziele(s).ids(), [9, 11])
        s["apply"]()
        self.assertEqual((b.function_id, b.function_ids), (9, [11]))

    def test_leeren_der_ziele_loest_knopf_weiterhin(self):
        b = VCButton("B")
        b.action = ButtonAction.FUNCTION_TOGGLE
        b.function_id = 7
        s = self._settings(b)
        _ziele(s).set_targets([])
        s["apply"]()
        self.assertIsNone(b.function_id)

    def test_namenswahl_eines_weiteren_ziels_wird_haupt_ziel(self):
        # Wahl eines schon gelisteten, aber nicht ersten Ziels darf nicht still
        # wirkungslos bleiben (Combo zeigte 11, Knopf blieb auf 7).
        b = VCButton("B")
        b.action = ButtonAction.FUNCTION_TOGGLE
        b.function_id, b.function_ids = 7, [9]
        s = self._settings(b)
        _waehle(_namens_combo(_alle_widgets(s)), 9)
        self.assertEqual(_ziele(s).ids(), [9])
        s["apply"]()
        self.assertEqual((b.function_id, b.function_ids), (9, []))

    @mock.patch("src.ui.virtualconsole.target_list_editor._all_functions",
                lambda: [(fid, f"{name}  [chaser #{fid}]") for fid, name in _FUNKTIONEN])
    def test_namens_combo_folgt_den_zielen(self):
        b = VCButton("B")
        b.action = ButtonAction.FUNCTION_TOGGLE
        b.function_id = 7
        s = self._settings(b)
        combo = _namens_combo(_alle_widgets(s))
        ziele = _ziele(s)
        self.assertEqual(combo.currentData(), 7)
        # Leeren ueber ✕ -> Combo zeigt keine Funktion mehr
        ziele._remove_row(ziele._rows[0])
        self.assertEqual(combo.currentData(), -1)
        # dieselbe Funktion erneut per Name waehlen bindet wieder
        _waehle(combo, 7)
        self.assertEqual(ziele.ids(), [7])
        s["apply"]()
        self.assertEqual(b.function_id, 7)
        # Haupt-Ziel in der Liste aendern -> Combo zieht nach
        row = ziele._rows[0]["func"]
        row.setCurrentIndex(row.findData(9))
        self.assertEqual(combo.currentData(), 9)

    def test_andere_knopfart_bindet_weiter_ueber_roh_id(self):
        b = VCButton("B")
        b.action = ButtonAction.TOGGLE
        s = self._settings(b)
        _waehle(_namens_combo(_alle_widgets(s)), 9)
        s["apply"]()
        self.assertEqual(b.function_id, 9)
        self.assertEqual(b.action, ButtonAction.TOGGLE)


@mock.patch.object(VCButton, "_populate_function_combo", _gestellte_funktionen)
class InspectorTest(unittest.TestCase):
    """Inspector-Panel: build_inspector_body, Aenderungen wirken sofort."""

    def test_namenswahl_bindet_sofort(self):
        b = VCButton("Neu")
        b.action = ButtonAction.FUNCTION_TOGGLE
        body = b.build_inspector_body()
        ziele = body.findChildren(TargetListEditor)[0]
        self.assertEqual(ziele.ids(), [])
        _waehle(_namens_combo(body.findChildren(QComboBox)), 7)
        self.assertEqual(ziele.ids(), [7])
        self.assertEqual(b.function_id, 7, "Inspector muss sofort binden")

    def test_leeren_im_inspector_loest(self):
        b = VCButton("B")
        b.action = ButtonAction.FUNCTION_FLASH
        b.function_id = 7
        body = b.build_inspector_body()
        body.findChildren(TargetListEditor)[0].set_targets([])
        _app.processEvents()
        self.assertIsNone(b.function_id)


if __name__ == "__main__":
    unittest.main()
