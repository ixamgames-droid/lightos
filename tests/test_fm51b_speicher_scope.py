"""FM-51 Scheibe B: EIN Speicher-/Loesch-Scope aus dem AppState.

Ein Geraet, das nur ueber Weiss-Zellen (``"1:w3"``) gewaehlt ist, steht bewusst
NICHT in ``AppState.selected_fids``. Bis Scheibe B machten alle vier
Speicherwege (Snapshot-Slot, Quick-Snapshot, Snap-Bibliothek, Programmer ->
Szene) aus der dann leeren fid-Liste ``scope=None`` = GANZER Programmer:
fremde PAR-Restwerte und alle acht Weiss-Schluessel landeten im Snapshot. Der
„Löschen"-Knopf leerte das ganze Geraet (alle 48 RGB-Zonen und alle Segmente)
und hiess dabei „Auswahl löschen (1)".

Soll:

* ``AppState.auswahl_programmer_scope()`` — ``None`` NUR bei wirklich leerer
  Auswahl, sonst ``{fid: None | set(Schluessel)}`` (ganze Geraete, Koepfe,
  Weiss-Segmente samt geteiltem Dimmer, Anker-Regel fuer Segment 0, gemischte
  Auswahl vereinigt);
* alle Speicherwege und der Kanal-Dialog nutzen genau diesen Scope;
* ``auswahl_leeren`` leert nur-Weiss-Segmente einzeln und verankert sie auf 0,
  solange ``color_w`` steht (der Flush spiegelt es sonst darauf);
* Toolbar-Aktionen lesen ihre Ziele aus dem AppState, nicht aus der
  Editor-Liste der View.

Aufbau: fid 1 = ZQ06121 (48 RGB-Zonen + 8 Weiss-Segmente, Adresse 1: CH1
Master, CH3-146 RGB, CH147-154 Weiss 0-7), fid 2 = RGBW-PAR ZQ01424 mit einem
Restwert im Programmer. Echter AppState, echte Views und Dialoge.
"""
import copy
import inspect
import os
import types
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import (QApplication, QDialog, QInputDialog,  # noqa: E402
                               QMessageBox)
from sqlalchemy import select                                       # noqa: E402
from sqlalchemy.orm import Session                                  # noqa: E402

from src.core.app_state import get_state                            # noqa: E402
from src.core.database.fixture_db import engine, ensure_builtins    # noqa: E402
from src.core.database.models import FixtureProfile, PatchedFixture  # noqa: E402
from src.core.show.show_file import reset_show                      # noqa: E402
from src.ui.views import snap_file_panel as sfp                     # noqa: E402

_app = QApplication.instance() or QApplication([])
BALKEN_MODUS = "154-Kanal 48 Zonen RGB + 8x Weiss"
WEISS_CH0 = 147                       # DMX-Kanal von Weiss-Segment 0 (Adresse 1)


def _pid(short):
    with Session(engine()) as s:
        return s.execute(select(FixtureProfile.id).where(
            FixtureProfile.short_name == short)).scalars().first()


class _AutoDialog(sfp.ChannelSelectDialog):
    """Echter ChannelSelectDialog, der ohne Bildschirm sofort bestaetigt und
    festhaelt, was er herausfiltert. Parent wird ignoriert (Quick-Snapshot wird
    mit einem schlanken Fenster-Ersatz gerufen)."""
    letzte: list = []
    abwaehlen: tuple = ()

    def __init__(self, programmer, parent=None, **kw):
        super().__init__(programmer, None, **kw)
        self.kw = kw
        _AutoDialog.letzte.append(self)
        for attr in _AutoDialog.abwaehlen:
            cb = self._attr_checks.get(attr)
            if cb is not None:
                cb.setChecked(False)

    def exec(self):
        return QDialog.DialogCode.Accepted

    def filter_programmer(self, programmer):
        self.ergebnis = super().filter_programmer(programmer)
        return self.ergebnis


class _Rig(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        ensure_builtins()

    def setUp(self):
        reset_show()
        self.st = get_state()
        self.st.add_fixture(PatchedFixture(
            fid=1, label="Balken", fixture_profile_id=_pid("ZQ06121"),
            mode_name=BALKEN_MODUS, universe=1, address=1, channel_count=154,
            fixture_type="matrix"), undoable=False)
        self.st.add_fixture(PatchedFixture(
            fid=2, label="PAR", fixture_profile_id=_pid("ZQ01424"),
            mode_name="8-Kanal RGBW", universe=1, address=300, channel_count=8,
            fixture_type="par"), undoable=False)
        self.addCleanup(self.st.set_selected_cells, [])
        self.addCleanup(self.st.clear_programmer)
        self.st.clear_programmer()
        self.st.set_selected_cells([])
        _AutoDialog.letzte = []
        _AutoDialog.abwaehlen = ()
        p = mock.patch.object(sfp, "ChannelSelectDialog", _AutoDialog)
        p.start()
        self.addCleanup(p.stop)
        g = mock.patch.object(QInputDialog, "getText",
                              staticmethod(lambda *a, **k: ("Test", True)))
        g.start()
        self.addCleanup(g.stop)
        # Keine modalen Meldungen ohne Bildschirm — festhalten statt blockieren.
        self.meldungen = []
        for name in ("information", "warning"):
            m = mock.patch.object(QMessageBox, name, staticmethod(
                lambda *a, **k: self.meldungen.append(a[1:3])))
            m.start()
            self.addCleanup(m.stop)

    # Helfer ------------------------------------------------------------------
    def seg(self, n):
        return self.st.weiss_programmer_key(1, n)

    def dimmer(self):
        return self.st.weiss_dimmer_key(1, 3)

    def belegen(self):
        """Weiss 3 = 200 mit Master, Weiss 1 = 50, ein RGB-Wert am Balken und
        ein PAR-Restwert."""
        self.st.weiss_setzen(1, 3, 200)
        self.st.weiss_setzen(1, 1, 50)
        self.st.set_programmer_value(1, self.dimmer(), 255)
        self.st.set_programmer_value(1, "color_r#2", 77)
        self.st.set_programmer_value(1, "color_r#1", 66)
        self.st.set_programmer_value(2, "color_r", 200)

    def kanal(self, n):
        return self.st.output_manager.universes[1].get_channel(n)

    def prog(self, fid):
        return dict(self.st.programmer.get(fid, {}))


# ── 1. AppState.auswahl_programmer_scope ────────────────────────────────────

class ScopeTest(_Rig):

    def test_reine_weiss_auswahl_nur_segment_und_dimmer(self):
        self.st.set_selected_cells(["1:w3"])
        self.assertEqual(self.st.auswahl_programmer_scope(),
                         {1: {"color_w#3", self.dimmer()}})

    def test_dimmer_abwaehlbar(self):
        self.st.set_selected_cells(["1:w3"])
        self.assertEqual(self.st.auswahl_programmer_scope(mit_dimmer=False),
                         {1: {"color_w#3"}})

    def test_gemischt_ganzes_geraet_plus_segment(self):
        self.st.set_selected_cells(["2", "1:w3"])
        self.assertEqual(self.st.auswahl_programmer_scope(),
                         {2: None, 1: {"color_w#3", self.dimmer()}})

    def test_kopf_ohne_weiss_schluessel(self):
        """``color_w#2`` ist Weiss-Segment 2, NICHT Kopf 2."""
        self.belegen()
        self.st.weiss_setzen(1, 2, 10)
        self.st.set_selected_cells(["1:2"])
        sc = self.st.auswahl_programmer_scope()
        self.assertEqual(set(sc), {1})
        self.assertIn("color_r#2", sc[1])
        self.assertNotIn("color_w#2", sc[1])
        self.assertNotIn("color_r#1", sc[1])

    def test_kopf_plus_segment_vereinigt(self):
        self.st.set_selected_cells(["1:2", "1:w3"])
        sc = self.st.auswahl_programmer_scope()
        self.assertTrue({"color_r#2", "color_w#3", self.dimmer()} <= sc[1])
        self.assertNotIn("color_w#2", sc[1])

    def test_basis_segment_nimmt_anker_mit(self):
        """Segment 0 traegt ``color_w`` — ohne die Anker spiegelte der Abruf es
        auf alle acht Segmente."""
        self.st.set_selected_cells(["1:w0"])
        sc = self.st.auswahl_programmer_scope()
        self.assertEqual(sc[1] - {self.dimmer()},
                         set(self.st.weiss_alle_keys(1)))
        self.assertEqual(len(self.st.weiss_alle_keys(1)), 8)

    def test_leer_heisst_none(self):
        self.st.set_selected_cells([])
        self.assertIsNone(self.st.auswahl_programmer_scope())

    def test_active_scope_fids_bleibt_bruecke(self):
        self.st.set_selected_cells(["2", "1:w3"])
        self.assertEqual(self.st.active_scope_fids(), [2])


# ── 2. ChannelSelectDialog mit Schluessel-Scope ──────────────────────────────

class DialogTest(_Rig):

    def _prog(self):
        return {1: {"color_w#3": 200, "color_w": 0, "color_r": 9, "intensity": 255},
                2: {"color_r": 200}}

    def test_behaelt_je_geraet_genau_die_schluessel(self):
        dlg = _AutoDialog(self._prog(), scope_keys={1: {"color_w#3"}})
        self.assertEqual(dlg.filter_programmer(self._prog()), {1: {"color_w#3": 200}})

    def test_none_wert_heisst_ganzes_geraet(self):
        dlg = _AutoDialog(self._prog(), scope_keys={2: None, 1: {"color_w#3"}})
        self.assertEqual(dlg.filter_programmer(self._prog()),
                         {2: {"color_r": 200}, 1: {"color_w#3": 200}})

    def test_leeres_dict_nimmt_nichts(self):
        dlg = _AutoDialog(self._prog(), scope_keys={})
        self.assertEqual(dlg.filter_programmer(self._prog()), {})

    def test_scope_none_alles(self):
        dlg = _AutoDialog(self._prog(), scope_keys=None)
        self.assertEqual(dlg.filter_programmer(self._prog()), self._prog())

    def test_scope_helfer_liefert_schluessel_scope(self):
        self.st.set_selected_cells(["1:w3"])
        self.assertEqual(sfp._scope(self.st),
                         {"scope_keys": {1: {"color_w#3", self.dimmer()}}})

    def test_dimmer_im_dialog_abwaehlbar(self):
        self.belegen()
        self.st.set_selected_cells(["1:w3"])
        _AutoDialog.abwaehlen = (self.dimmer(),)
        dlg = _AutoDialog(self.st.programmer, **sfp._scope(self.st))
        self.assertEqual(dlg.filter_programmer(self.st.programmer),
                         {1: {"color_w#3": 200}})


# ── 3. Die vier Speicherwege ────────────────────────────────────────────────

class _Speicherweg(_Rig):
    """Je Speicherweg: reine Weiss-Auswahl / gemischt / Kopf / leer."""

    def setUp(self):
        if type(self) is _Speicherweg:
            self.skipTest("Basisklasse")
        super().setUp()

    def speichern(self) -> dict:
        raise NotImplementedError

    def ausloesen(self) -> dict:
        """Speichern ausloesen, ohne vorauszusetzen, dass der Dialog aufgeht."""
        return self.speichern()

    def test_auswahl_ohne_werte_klartext_ohne_dialog(self):
        """Befund 4: reine Weiss-Auswahl ohne Segmentwert, nur ein PAR-Rest im
        Programmer -> EINE klare Meldung, kein Kanal-Dialog, nichts gespeichert
        (vorher: Dialog „Keine Werte im Programmer." und danach „Keine Kanäle
        ausgewählt …")."""
        self.st.set_programmer_value(2, "color_r", 200)
        self.st.set_selected_cells(["1:w3"])
        self.assertFalse(self.ausloesen())
        self.assertEqual(_AutoDialog.letzte, [], "Dialog darf nicht aufgehen")
        texte = [m[1] for m in self.meldungen]
        self.assertEqual(texte, [sfp.KEINE_WERTE_IM_SCOPE])
        self.assertEqual(
            sfp.KEINE_WERTE_IM_SCOPE,
            "Die gewählten Geräte/Segmente haben keine Werte im Programmer.")

    def test_reine_weiss_auswahl(self):
        self.belegen()
        self.st.set_selected_cells(["1:w3"])
        self.assertEqual(self.speichern(),
                         {1: {"color_w#3": 200, self.dimmer(): 255}})

    def test_gemischt(self):
        self.belegen()
        self.st.set_selected_cells(["2", "1:w3"])
        self.assertEqual(self.speichern(),
                         {2: {"color_r": 200},
                          1: {"color_w#3": 200, self.dimmer(): 255}})

    def test_kopf(self):
        self.belegen()
        self.st.weiss_setzen(1, 2, 10)
        self.st.set_selected_cells(["1:2"])
        ergebnis = self.speichern()
        # Erwartet: genau die Kopf-2-Schluessel, die JETZT im Programmer stehen
        # (die Programmer-View verankert beim Kopf-Aufbau G/B des Kopfs) — ohne
        # Weiss-Segment 2, ohne Kopf 1, ohne PAR.
        erwartet = {k: v for k, v in self.prog(1).items()
                    if k.endswith("#2") and not k.startswith("color_w")}
        self.assertEqual(ergebnis, {1: erwartet})
        self.assertEqual(erwartet.get("color_r#2"), 77)

    def test_leer_ganzer_programmer(self):
        self.belegen()
        self.st.set_selected_cells([])
        erwartet = copy.deepcopy(dict(self.st.programmer))
        self.assertEqual(self.speichern(), erwartet)


class SnapshotSlotTest(_Speicherweg):

    def speichern(self):
        from src.ui.views.snapshots_view import SnapshotsView
        v = SnapshotsView()
        self.addCleanup(v.deleteLater)
        v._save_to_disk = lambda: None
        v.capture(0)
        return v._snapshots[0].values


class QuickSnapshotTest(_Speicherweg):

    def speichern(self):
        from src.ui.main_window import MainWindow
        from src.ui.views.snapshots_view import SnapshotsView
        sv = SnapshotsView()
        self.addCleanup(sv.deleteLater)
        sv._save_to_disk = lambda: None
        for s in sv._snapshots:
            s.values = {}
        fenster = types.SimpleNamespace(
            _snapshots_view=sv, _state=self.st,
            statusBar=lambda: types.SimpleNamespace(showMessage=lambda *a: None))
        MainWindow._quick_snapshot(fenster)
        return sv._snapshots[0].values


class SnapBibliothekTest(_Speicherweg):

    def speichern(self):
        from src.ui.views.snap_file_panel import SnapFilePanel
        panel = SnapFilePanel()
        self.addCleanup(panel.deleteLater)
        gespeichert = {}
        lib = types.SimpleNamespace(
            add_snap=lambda name, folder, vals: gespeichert.update(vals))
        panel._lib = lambda: lib
        panel._refresh_tree = lambda: None
        panel._save_snap()
        return gespeichert


class SzeneTest(_Speicherweg):

    def setUp(self):
        super().setUp()
        # View VOR der Auswahl bauen (beim Aufbau publiziert sie ihre leere Liste).
        from src.ui.views.programmer_view import ProgrammerView
        self.v = ProgrammerView()
        self.addCleanup(self.v.deleteLater)

    def speichern(self):
        self.v._sync_follow_selection()
        self.v._save_as_scene()
        self.assertTrue(_AutoDialog.letzte, "Dialog nicht geoeffnet")
        return _AutoDialog.letzte[-1].ergebnis

    def ausloesen(self):
        self.v._sync_follow_selection()
        gespeichert = {}
        with mock.patch(
                "src.ui.views.programmer_view.programmer_to_scene_values",
                lambda vals, fx: gespeichert.update(vals) or {}):
            self.v._save_as_scene()
        return gespeichert


class DialogOhneWerteTest(_Rig):
    """Befund 4: der Dialog selbst sagt bei eingeschraenktem Scope ehrlich, dass
    nur die AUSWAHL keine Werte hat."""

    def _texte(self, dlg):
        from PySide6.QtWidgets import QLabel
        return [w.text() for w in dlg.findChildren(QLabel)]

    def test_schluessel_scope_ohne_werte(self):
        dlg = _AutoDialog({2: {"color_r": 200}}, scope_keys={1: {"color_w#3"}})
        self.assertIn(sfp.KEINE_WERTE_IM_SCOPE, self._texte(dlg))
        self.assertNotIn("Keine Werte im Programmer.", self._texte(dlg))

    def test_wirklich_leerer_programmer_bleibt(self):
        dlg = _AutoDialog({}, scope_keys=None)
        self.assertIn("Keine Werte im Programmer.", self._texte(dlg))

    def test_vorab_check(self):
        self.st.set_programmer_value(2, "color_r", 200)
        self.st.set_selected_cells(["1:w3"])
        self.assertTrue(sfp.scope_ohne_werte(self.st, self.st.programmer))
        self.st.set_selected_cells([])
        self.assertFalse(sfp.scope_ohne_werte(self.st, self.st.programmer))
        self.st.set_selected_cells(["2", "1:w3"])
        self.assertFalse(sfp.scope_ohne_werte(self.st, self.st.programmer))
        self.assertFalse(sfp.scope_ohne_werte(self.st, {}))


# ── 4. Loeschen ──────────────────────────────────────────────────────────────

class LoeschenTest(_Rig):

    def setUp(self):
        super().setUp()
        from src.ui.views.programmer_view import ProgrammerView
        self.v = ProgrammerView()
        self.addCleanup(self.v.deleteLater)

    def waehle(self, zellen):
        self.st.set_selected_cells(list(zellen))
        self.v._sync_follow_selection()

    def basis_und_drei(self):
        self.st.weiss_setzen(1, 0, 100)
        self.st.weiss_setzen(1, 3, 200)
        self.st.set_programmer_value(1, self.dimmer(), 255)
        self.st.set_programmer_value(1, "color_r#2", 77)
        self.st.set_programmer_value(2, "color_r", 200)

    def test_nur_das_segment_verankert_auf_null(self):
        self.basis_und_drei()
        self.waehle(["1:w3"])
        self.v._clear_programmer()
        p1 = self.prog(1)
        self.assertEqual(p1.get("color_w#3"), 0, "Segment muss auf 0 verankert sein")
        self.assertEqual(p1.get("color_w"), 100, "Basis-Segment bleibt")
        self.assertEqual(p1.get(self.dimmer()), 255, "geteilter Master bleibt")
        self.assertEqual(p1.get("color_r#2"), 77, "RGB-Zonen bleiben")
        self.assertEqual(self.prog(2), {"color_r": 200}, "PAR unberuehrt")
        # Spiegelungs-Gegenprobe im DMX-Ausgang: Segment 3 ist wirklich 0.
        self.assertEqual(self.kanal(WEISS_CH0 + 3), 0)
        self.assertEqual(self.kanal(WEISS_CH0), 100)

    def test_gegenprobe_entfernen_wuerde_spiegeln(self):
        """Begruendung der Verankerung: ein ENTFERNTES Segment gibt color_w aus."""
        self.basis_und_drei()
        self.st._clear_programmer_attr(1, "color_w#3")
        self.assertEqual(self.kanal(WEISS_CH0 + 3), 100)

    def test_mit_basis_segment_wird_entfernt(self):
        self.basis_und_drei()
        self.waehle(["1:w0", "1:w3"])
        self.v._clear_programmer()
        p1 = self.prog(1)
        self.assertNotIn("color_w", p1)
        self.assertNotIn("color_w#3", p1)
        self.assertEqual(self.kanal(WEISS_CH0), 0)
        self.assertEqual(self.kanal(WEISS_CH0 + 3), 0)
        self.assertEqual(p1.get("color_r#2"), 77)

    def test_gemischt_ganzes_geraet_und_segment(self):
        self.basis_und_drei()
        self.waehle(["2", "1:w3"])
        self.v._clear_programmer()
        self.assertNotIn(2, self.st.programmer)
        self.assertEqual(self.prog(1).get("color_w#3"), 0)
        self.assertEqual(self.prog(1).get("color_w"), 100)

    def test_leer_leert_alles(self):
        self.basis_und_drei()
        self.waehle([])
        self.v._clear_programmer()
        self.assertEqual(dict(self.st.programmer), {})

    def test_ein_verlaufsschritt(self):
        self.basis_und_drei()
        self.st.programmer_verlauf.abschliessen()
        self.waehle(["1:w0", "1:w3"])
        vorher = self.st.programmer_verlauf.anzahl()
        self.v._clear_programmer()
        self.assertEqual(self.st.programmer_verlauf.anzahl(), vorher + 1)
        self.assertEqual(self.st.programmer_rueckgaengig(), "Löschen")
        self.assertEqual(self.prog(1).get("color_w"), 100)
        self.assertEqual(self.prog(1).get("color_w#3"), 200)

    def test_beschriftung_ein_segment(self):
        self.waehle(["1:w3"])
        self.assertEqual(self.v._btn_clear.text(), "Auswahl löschen (1 Segment)")
        hilfe = self.v._btn_clear.toolTip()
        self.assertIn("Segment", hilfe)
        self.assertIn("Master", hilfe)
        self.assertNotIn("Geräte —", hilfe)

    def test_beschriftung_mehrere_und_gemischt(self):
        self.waehle(["1:w3", "1:w4"])
        self.assertEqual(self.v._btn_clear.text(), "Segmente löschen (2)")
        self.waehle(["2", "1:w3"])
        self.assertEqual(self.v._btn_clear.text(), "Auswahl löschen (1 + 1 Segment)")
        self.waehle([])
        self.assertEqual(self.v._btn_clear.text(), "Alles löschen")

    def test_basis_segment_leeren_verankert_die_gespiegelten(self):
        """Befund 1: ``color_w`` geraeteweit (nicht ueber weiss_setzen) — die
        uebrigen sieben Segmente leuchten ueber die Flush-Spiegelung mit. Wird
        nur Segment 0 geleert, muessen sie auf ihrem Wert bleiben."""
        self.st.set_programmer_value(1, self.dimmer(), 255)
        self.st.set_programmer_value(1, "color_w", 100)
        for n in range(1, 8):
            self.assertNotIn(self.seg(n), self.prog(1))
            self.assertEqual(self.kanal(WEISS_CH0 + n), 100)
        self.st.programmer_verlauf.abschliessen()
        vorher = self.prog(1)
        self.waehle(["1:w0"])
        anzahl = self.st.programmer_verlauf.anzahl()
        self.v._clear_programmer()
        self.assertEqual(self.st.programmer_verlauf.anzahl(), anzahl + 1)
        self.assertNotIn("color_w", self.prog(1))
        self.assertEqual(self.kanal(WEISS_CH0), 0, "Segment 0 aus")
        for n in range(1, 8):
            self.assertEqual(self.kanal(WEISS_CH0 + n), 100,
                             f"Segment {n} muss weiter leuchten")
        self.assertEqual(self.st.programmer_rueckgaengig(), "Löschen")
        self.assertEqual(self.prog(1), vorher)
        for n in range(8):
            self.assertEqual(self.kanal(WEISS_CH0 + n), 100)

    def test_hilfetext_satzanfang(self):
        """Befund 3: grammatisch richtiger Satzanfang je Fall, nennt was bleibt."""
        from src.ui.views.programmer_view import ProgrammerView as PV
        faelle = {
            (0, 1): "Leert das gewählte Weiß-Segment. ",
            (0, 3): "Leert die 3 gewählten Weiß-Segmente. ",
            (1, 1): "Leert die Programmer-Werte des ausgewählten Geräts und "
                    "das gewählte Weiß-Segment. ",
            (2, 2): "Leert die Programmer-Werte der 2 ausgewählten Geräte und "
                    "die 2 gewählten Weiß-Segmente. ",
        }
        for (a, n), anfang in faelle.items():
            hilfe = PV._clear_button_labels(a, n)[1]
            self.assertTrue(hilfe.startswith(anfang), (a, n, hilfe))
            self.assertIn("Master-Dimmer", hilfe)
            self.assertIn("Farbzonen (RGB)", hilfe)
            self.assertIn("übrigen Weiß-Segmente", hilfe)
        self.waehle(["1:w3"])
        self.assertTrue(self.v._btn_clear.toolTip().startswith(
            "Leert das gewählte Weiß-Segment. "))

    def test_beschriftung_reine_funktion(self):
        from src.ui.views.programmer_view import ProgrammerView
        self.assertEqual(ProgrammerView._clear_button_labels(0, 1)[0],
                         "Auswahl löschen (1 Segment)")
        self.assertEqual(ProgrammerView._clear_button_labels(0, 3)[0],
                         "Segmente löschen (3)")
        self.assertEqual(ProgrammerView._clear_button_labels(2)[0],
                         "Auswahl löschen (2)")


# ── 5. Editor-Liste ist kein Aktionsziel ────────────────────────────────────

class EditorListeTest(_Rig):

    def setUp(self):
        super().setUp()
        from src.ui.views.programmer_view import ProgrammerView
        self.v = ProgrammerView()
        self.addCleanup(self.v.deleteLater)

    def test_toolbar_aktionen_lesen_nicht_die_editor_liste(self):
        from src.ui.views.programmer_view import ProgrammerView
        for name in ("_highlight", "_highlight_werte", "_lowlight",
                     "_clear_programmer", "_sync_clear_button",
                     "_copy_to_clipboard", "_paste_from_clipboard",
                     "_feed_fan_targets", "get_selected_fids"):
            src = inspect.getsource(getattr(ProgrammerView, name))
            for verboten in ("self._selected_fids", "self._editor_fids",
                             '"_selected_cells"'):
                self.assertNotIn(verboten, src, f"{name} liest {verboten}")

    def test_kopf_umschalter_ignoriert_nur_weiss_geraete(self):
        """Befund 2: ``['2', '1:w3']`` — der Balken ist nur ueber Weiss gewaehlt.
        Seine 48 RGB-Zonen duerfen weder den Umschalter „Köpfe: Synchron"
        einblenden noch von Synchron ihre ``color_*#N`` verlieren."""
        from PySide6.QtWidgets import QComboBox
        self.st.set_programmer_value(1, "color_r#5", 123)
        self.st.set_programmer_value(1, "color_g#7", 45)
        self.st.set_selected_cells(["2", "1:w3"])
        self.v._sync_follow_selection()
        self.assertEqual(self.v._color_head_count(), 1)
        self.assertFalse(self.v._has_auto_mode_color_head_fixture())
        umschalter = [c for c in self.v.findChildren(QComboBox)
                      if c.findData("sync") >= 0 and c.findData("separate") >= 0]
        self.assertEqual(umschalter, [], "Köpfe-Umschalter darf nicht erscheinen")
        self.v._normalize_color_heads_to_sync()
        self.assertEqual(self.prog(1).get("color_r#5"), 123)
        self.assertEqual(self.prog(1).get("color_g#7"), 45)

    def test_kopf_umschalter_gegenprobe_ganzes_geraet(self):
        """Gegenprobe: als GANZES Geraet gewaehlt zaehlen die RGB-Zonen."""
        self.st.set_selected_cells(["1"])
        self.v._sync_follow_selection()
        self.assertGreater(self.v._color_head_count(), 1)

    def test_kopf_umschalter_liest_nicht_die_editor_liste(self):
        from src.ui.views.programmer_view import ProgrammerView
        for name in ("_color_head_count", "_has_auto_mode_color_head_fixture",
                     "_normalize_color_heads_to_sync"):
            src = inspect.getsource(getattr(ProgrammerView, name))
            self.assertNotIn("self._selected_fixtures()", src, name)
            self.assertIn("self._kopf_fixtures()", src, name)

    def test_editor_liste_heisst_editor_fids(self):
        self.st.set_selected_cells(["1:w3"])
        self.v._sync_follow_selection()
        self.assertEqual(self.v._editor_fids, [1])

    def test_get_selected_fids_folgt_dem_appstate(self):
        self.st.set_selected_cells(["1:w3"])
        self.v._sync_follow_selection()
        self.assertEqual(self.v.get_selected_fids(), [])
        self.st.set_selected_cells(["2", "1:w3"])
        self.v._sync_follow_selection()
        self.assertEqual(self.v.get_selected_fids(), [2])

    def test_highlight_mit_abweichender_editor_liste(self):
        """Die Editor-Liste (z. B. noch nicht nachgezogen) darf kein Ziel sein."""
        self.st.set_selected_cells(["2"])
        self.v._selected_fids = [1]     # Editor-Liste (Alt-Name) weicht ab
        self.v._highlight()
        self.assertNotIn(1, self.st.programmer)
        self.assertEqual(self.prog(2).get("intensity"), 255)

    def test_kopieren_einfuegen_mit_abweichender_editor_liste(self):
        self.st.set_programmer_value(2, "color_r", 200)
        self.st.set_selected_cells(["2"])
        self.v._selected_fids = [1]     # Editor-Liste (Alt-Name) weicht ab
        self.v._copy_to_clipboard()
        self.assertEqual(list(self.v._clipboard), [2])


if __name__ == "__main__":
    unittest.main()
