"""FM-79 — leeren Layered-Effekt in der Bibliothek anlegen.

Befund (Live-Durchlauf QA-LIVE): „+ Layered Effekt" sass nur in der nicht mehr
eingehaengten Funktionsansicht; die Bibliothek bot keinen Weg an. Jetzt legt
„Layer +" (und der Kontextmenue-Eintrag „Layered-Effekt anlegen") einen
leeren Effekt fuer die gewaehlten Geraete an und oeffnet den Editor.

Nebenbefund: der Editor zeigt einen Hinweis, wenn KEINES der Geraete einen
Kanal fuer das Ziel hat — die Engine und die Kopplung Farbe/Dimmer bleiben
unberuehrt.

Offscreen, Wegwerf-Show, frische Bibliothek; Kanal-Abfrage synthetisch.
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
for _p in (str(ROOT), str(ROOT / "tests")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

BILDER = os.environ.get("FM79_BILDER")   # optional: Bildprobe-Verzeichnis


def _app():
    return QApplication.instance() or QApplication([])


# Synthetische Kanaele je Geraet: 1 = RGB ohne Dimmer, 2 = Dimmer + RGB.
_KANAELE = {
    1: ["color_r", "color_g", "color_b"],
    2: ["intensity", "color_r", "color_g", "color_b"],
}


def _kanaele(fx):
    return [SimpleNamespace(attribute=a, channel_number=i + 1)
            for i, a in enumerate(_KANAELE.get(int(fx.fid), []))]


class LayeredAnlegenTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _app()
        from _fixture_quelle import frische_library
        cls._eng = frische_library(cls)

    def setUp(self):
        from src.core.show.show_file import reset_show
        from src.core.app_state import get_state
        from src.core.database.models import PatchedFixture
        import src.core.app_state as app_state_mod
        import src.ui.views.snap_file_panel as sfp

        reset_show()
        self.state = get_state()
        from sqlalchemy import select
        from sqlalchemy.orm import Session
        from src.core.database.models import FixtureProfile
        with Session(self._eng) as s:
            pid = int(s.execute(select(FixtureProfile.id)).scalars().first())
        for fid, adr in ((1, 1), (2, 20), (3, 40)):
            self.state.add_fixture(PatchedFixture(
                fid=fid, label=f"Par{fid}", fixture_profile_id=pid,
                mode_name="x", universe=1, address=adr, channel_count=4,
                fixture_type="par"), undoable=False)
        self._alt_kanaele = app_state_mod.get_channels_for_patched
        app_state_mod.get_channels_for_patched = _kanaele
        self.addCleanup(setattr, app_state_mod, "get_channels_for_patched",
                        self._alt_kanaele)

        self.hinweise: list[str] = []
        self._alt_info = QMessageBox.information
        self._alt_warn = QMessageBox.warning
        QMessageBox.information = staticmethod(
            lambda *a, **k: self.hinweise.append(str(a[2] if len(a) > 2 else "")))
        QMessageBox.warning = staticmethod(
            lambda *a, **k: self.hinweise.append("WARN " + str(a[2] if len(a) > 2 else "")))
        self.addCleanup(setattr, QMessageBox, "information", self._alt_info)
        self.addCleanup(setattr, QMessageBox, "warning", self._alt_warn)

        # Modalen Dialog nicht blockieren: festhalten und ansehen.
        self.dialoge: list = []
        self._alt_ausfuehren = sfp.dialog_hilfe.ausfuehren

        def _erfassen(dlg):
            dlg.resize(720, 560)
            dlg.show()
            _app().processEvents()
            self.dialoge.append(dlg)
            return 0
        sfp.dialog_hilfe.ausfuehren = _erfassen
        self.addCleanup(setattr, sfp.dialog_hilfe, "ausfuehren", self._alt_ausfuehren)

        self.panel = sfp.SnapFilePanel()
        self.addCleanup(self.panel.deleteLater)

    def tearDown(self):
        for d in self.dialoge:
            d.close()
            d.deleteLater()
        _app().processEvents()

    def _layered(self):
        from src.core.engine.function_manager import get_function_manager
        return [f for f in get_function_manager().all()
                if getattr(f, "is_layered_effect", False)]

    def _editor(self):
        from src.ui.views.effect_layer_editor import EffectLayerEditor
        self.assertTrue(self.dialoge, "kein Editor geoeffnet")
        eds = self.dialoge[-1].findChildren(EffectLayerEditor)
        self.assertEqual(len(eds), 1)
        return eds[0]

    def test_knopf_in_der_leiste(self):
        texte = [b.text() for b in self.panel._leisten_knoepfe]
        self.assertIn("Layer +", texte)

    def test_mit_auswahl_entsteht_effekt_und_editor_ist_offen(self):
        self.state.set_selected_fids([1, 3])
        vorher = len(self._layered())
        knopf = next(b for b in self.panel._leisten_knoepfe if b.text() == "Layer +")
        knopf.click()
        neu = self._layered()
        self.assertEqual(len(neu), vorher + 1)
        eff = neu[-1]
        self.assertEqual(list(eff.fixture_ids), [1, 3])
        self.assertEqual(eff.layers, [])
        # Ziel wie die Engine es fuer einen neuen Effekt vorgibt
        from src.core.engine.effect_func import LayeredEffect
        self.assertEqual(eff.target_attribute, LayeredEffect().target_attribute)
        # steht in der Bibliothek
        self.panel._refresh_tree()
        ids = []
        it = self.panel._tree.invisibleRootItem()
        stapel = [it]
        while stapel:
            x = stapel.pop()
            for i in range(x.childCount()):
                c = x.child(i)
                ids.append(c.data(0, 0x0100))
                stapel.append(c)
        self.assertTrue(any(isinstance(d, (tuple, list)) and eff.id in d
                            or d == eff.id for d in ids)
                        or any(c == ("function", eff.id) for c in ids),
                        f"Effekt {eff.id} fehlt im Baum: {ids}")
        # Editor offen, zeigt diesen Effekt
        ed = self._editor()
        self.assertIs(ed._effect, eff)
        self.assertTrue(self.dialoge[-1].isVisible())
        if BILDER:
            self.panel.resize(420, 480)
            self.panel.show()
            _app().processEvents()
            self.panel.grab().save(os.path.join(BILDER, "fm79_bibliothek.png"))

    def test_ohne_auswahl_hinweis_und_nichts_angelegt(self):
        self.state.set_selected_fids([])
        vorher = len(self._layered())
        self.panel._new_layered_effect()
        self.assertEqual(len(self._layered()), vorher)
        self.assertEqual(self.dialoge, [])
        self.assertTrue(any("Keine Geräte gewählt" in h for h in self.hinweise),
                        self.hinweise)

    def test_hinweis_im_editor_bei_ziel_ohne_kanal(self):
        self.state.set_selected_fids([1])        # RGB ohne Dimmer
        self.panel._new_layered_effect()
        ed = self._editor()
        self.assertEqual(ed._effect.target_attribute, "intensity")
        self.assertFalse(ed._ziel_hinweis.isHidden())
        self.assertIn("intensity", ed._ziel_hinweis.text())
        if BILDER:
            self.dialoge[-1].grab().save(os.path.join(BILDER, "fm79_editor.png"))
        # Ziel mit Kanal -> Hinweis weg
        ed._target_combo.setCurrentText("color_r")
        self.assertTrue(ed._ziel_hinweis.isHidden())
        # zurueck auf intensity, dann ein Geraet MIT Dimmer dazu -> weg
        ed._target_combo.setCurrentText("intensity")
        self.assertFalse(ed._ziel_hinweis.isHidden())
        ed._fixtures_edit.setText("1,2")
        ed._apply_fixture_ids()
        self.assertTrue(ed._ziel_hinweis.isHidden())

    def test_speichern_und_neuladen_erhaelt_effekt(self):
        from src.core.show.show_file import save_show, load_show, reset_show
        self.state.set_selected_fids([2, 3])
        self.panel._new_layered_effect()
        eff = self._layered()[-1]
        eff.name = "FM79 Probe"
        with tempfile.TemporaryDirectory() as tmp:
            pfad = os.path.join(tmp, "probe.lshow")
            save_show(pfad)
            reset_show()
            self.assertFalse(any(f.name == "FM79 Probe" for f in self._layered()))
            ok, msg = load_show(pfad)
            self.assertTrue(ok, msg)
        geladen = [f for f in self._layered() if f.name == "FM79 Probe"]
        self.assertEqual(len(geladen), 1)
        self.assertEqual(list(geladen[0].fixture_ids), [2, 3])


if __name__ == "__main__":
    unittest.main()
