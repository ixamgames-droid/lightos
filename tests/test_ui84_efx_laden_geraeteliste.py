"""UI-84: Laden einer Show im Hauptfenster darf die Geraeteliste eines EFX nicht
veraendern.

Bierpong-Durchsicht (09.10.): Im echten Hauptfenster wurde beim Laden die
Geraeteliste des ERSTEN EFX ("Kreis", zwei Moving Heads) durch die aktuelle
Auswahl bzw. "alle Mover" ersetzt. Ursache: der im Programmer eingebettete
EFX-Editor (Folgemodus) rief bei JEDER Listen-Selektion
``_assign_from_selection`` — auch wenn das Programm beim Laden/Refresh die
erste Zeile selektiert. Ohne Hauptfenster geladen blieb die Liste korrekt.

Erwartet: Laden/Refresh veraendert keine Funktionsdaten; Speichern direkt nach
dem Laden schreibt dieselbe EFX-Geraeteliste zurueck.
"""
import json
import os
import tempfile
import unittest
import uuid
import zipfile
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.core.app_state import get_state
from src.core.database.fixture_db import engine as fdb_engine, ensure_builtins
from src.core.database.models import PatchedFixture, FixtureProfile
from src.core.engine.efx import EfxFixture
from src.core.show import show_file as SF


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _profil(short: str):
    """(id, Herstellername, Profilname) — die Show-Datei prueft beim Laden,
    dass Name und Profil-ID zusammenpassen."""
    with Session(fdb_engine()) as s:
        p = s.execute(select(FixtureProfile).where(
            FixtureProfile.short_name == short)).scalar_one()
        return int(p.id), p.manufacturer.name, p.name


# XPLAT-15: Top-Level-Widgets nach jedem Test wirklich abbauen.
import pytest as _pytest_xplat15                      # noqa: E402
from _qt_lifecycle import destroy_all_top_level_widgets  # noqa: E402  XPLAT-15


@_pytest_xplat15.fixture(autouse=True)
def _xplat15_no_leaked_widgets():
    yield
    from PySide6.QtWidgets import QApplication as _QApp
    destroy_all_top_level_widgets(_QApp.instance())


def _efx_fids(fn) -> list:
    return [int(f.fid) for f in fn.fixtures]


class EfxLadenBehaeltGeraetelisteTest(unittest.TestCase):
    """Kompletter Ablauf im echten MainWindow (offscreen, gezeigt)."""

    def _baue_show(self) -> str:
        ensure_builtins()
        SF.reset_show()
        state = get_state()
        mh, mh_hst, mh_name = _profil("ZQ02001")
        sp, sp_hst, sp_name = _profil("SPIDER14")
        for fid, addr in ((31, 1), (32, 20), (33, 40), (34, 60)):
            state.add_fixture(PatchedFixture(
                fid=fid, label=f"MH {fid}", fixture_profile_id=mh,
                mode_name="11-Kanal", universe=1, address=addr,
                channel_count=11, manufacturer_name=mh_hst,
                fixture_name=mh_name, fixture_type="moving_head"),
                undoable=False)
        state.add_fixture(PatchedFixture(
            fid=40, label="Spider", fixture_profile_id=sp,
            mode_name="14-Kanal", universe=1, address=100, channel_count=14,
            manufacturer_name=sp_hst, fixture_name=sp_name,
            fixture_type="moving_head"), undoable=False)
        fm = state.function_manager
        kreis = fm.new_efx("Kreis")
        kreis.fixtures = [EfxFixture(fid=31), EfxFixture(fid=32)]
        acht = fm.new_efx("Acht")
        acht.fixtures = [EfxFixture(fid=33)]
        for f in (kreis, acht):
            f.committed = True
        pfad = os.path.join(tempfile.gettempdir(),
                            f"ui84_{uuid.uuid4().hex}.lshow")
        SF.save_show(pfad)
        self.addCleanup(lambda: os.path.exists(pfad) and os.remove(pfad))
        return pfad

    def _efx_in_datei(self, pfad) -> dict:
        with zipfile.ZipFile(pfad) as z:
            d = json.loads(z.read("show.json").decode("utf-8"))
        funcs = d["functions"]["functions"]
        return {f["name"]: [int(x["fid"]) for x in f.get("fixtures", [])]
                for f in funcs if f.get("name") in ("Kreis", "Acht")}

    def test_laden_und_speichern_veraendert_efx_nicht(self):
        app = _app()
        from src.ui import main_window as mw
        pfad = self._baue_show()
        vorher = self._efx_in_datei(pfad)
        self.assertEqual({"Kreis": [31, 32], "Acht": [33]}, vorher)

        state = get_state()
        win = mw.MainWindow()
        win.show()
        try:
            # Auswahl, die nicht zur ersten EFX passt (alle Mover + Spider).
            state.set_selected_fids([31, 32, 33, 34, 40])
            warnungen = []
            with mock.patch.object(mw.QMessageBox, "warning",
                                   lambda *a, **k: warnungen.append(a[1:])):
                win._open_show_path(pfad)
            self.assertEqual([], warnungen, "Show nicht sauber geladen")
            for _ in range(5):
                app.processEvents()
            fm = state.function_manager
            nach = {f.name: _efx_fids(f) for f in fm.all()
                    if f.name in ("Kreis", "Acht")}
            self.assertEqual(vorher, nach,
                             "Laden im Hauptfenster hat EFX-Geraetelisten veraendert")
            self.assertTrue(win._do_save(pfad))
            self.assertEqual(vorher, self._efx_in_datei(pfad),
                             "Speichern direkt nach dem Laden hat die EFX veraendert")
        finally:
            win.close()

    def test_laden_bei_offenem_efx_tab_im_programmer(self):
        """UI-84 Review: Programmer offen, EFX-Tab aktiv (Folge-Editor
        SICHTBAR). Beim Laden setzt die Live View ueber patch_changed die
        Auswahl neu (SELECTION_CHANGED) — der Folge-Editor durfte das nicht als
        Benutzer-Auswahlwechsel nehmen ('Kreis' [31, 32] -> [])."""
        app = _app()
        from src.ui import main_window as mw
        pfad = self._baue_show()
        vorher = self._efx_in_datei(pfad)
        state = get_state()
        win = mw.MainWindow()
        win.show()
        try:
            state.set_selected_fids([31, 32, 33, 34, 40])
            prog_idx = win._stack.indexOf(
                win._programmer_view.parentWidget().parentWidget())
            self.assertGreaterEqual(prog_idx, 0)
            win._switch_section(prog_idx)
            pv = win._programmer_view
            pv._main_tabs.setCurrentIndex(pv._efx_tab_index)
            for _ in range(3):
                app.processEvents()
            efx = pv._embedded_efx
            self.assertTrue(efx.isVisible(), "EFX-Editor im Test nicht sichtbar")
            warnungen = []
            with mock.patch.object(mw.QMessageBox, "warning",
                                   lambda *a, **k: warnungen.append(a[1:])):
                win._open_show_path(pfad)
            self.assertEqual([], warnungen, "Show nicht sauber geladen")
            # Auch was direkt nach dem Laden in derselben Ereignisschleife
            # auflaeuft (singleShot(0) & Co.), darf nichts zuweisen.
            for _ in range(5):
                app.processEvents()
            fm = state.function_manager
            nach = {f.name: _efx_fids(f) for f in fm.all()
                    if f.name in ("Kreis", "Acht")}
            self.assertEqual(vorher, nach,
                             "Laden bei offenem EFX-Tab hat EFX veraendert")
            self.assertTrue(win._do_save(pfad))
            self.assertEqual(vorher, self._efx_in_datei(pfad))
        finally:
            win.close()



class _Ch:
    def __init__(self, attr, num):
        self.attribute = attr
        self.channel_number = num
        self.default_value = 0
        self.highlight_value = 255
        self.ranges = []


class _Fx:
    def __init__(self, fid, address):
        self.fid = fid
        self.universe = 1
        self.address = address
        self._chans = [_Ch("pan", 1), _Ch("tilt", 2), _Ch("intensity", 3)]
        self.invert_pan = self.invert_tilt = self.swap_pan_tilt = False


class SichtbarerFolgeEditorTest(unittest.TestCase):
    """Auch bei SICHTBAREM eingebettetem Editor: Refresh/Laden (programmatische
    Zeilenwahl) laesst die Geraeteliste stehen; ein echter Klick auf eine andere
    EFX uebernimmt weiterhin die Auswahl (gewollter Folgemodus)."""

    def setUp(self):
        _app()
        import src.core.app_state as A
        from src.core.engine.efx import EfxInstance
        from src.ui.views.efx_view import EfxView
        self._sel = []
        alle = [_Fx(1, 10), _Fx(2, 20), _Fx(3, 30)]
        st = A.get_state()
        for ziel, name, wert in (
                (A, "get_channels_for_patched",
                 lambda fx: getattr(fx, "_chans", [])),
                (st, "get_patched_fixtures", lambda: list(alle)),
                (st, "get_selected_fids", lambda: list(self._sel)),
                (st, "get_selected_group_id", lambda: None)):
            p = mock.patch.object(ziel, name, wert)
            p.start()
            self.addCleanup(p.stop)
        self.v = EfxView(follow_selection=True)
        self.a = self.v._fm.add(EfxInstance("UI84-A"))
        self.b = self.v._fm.add(EfxInstance("UI84-B"))
        self.addCleanup(lambda: [self.v._fm.remove(f.id) for f in (self.a, self.b)])
        self.v.show()
        self.assertTrue(self.v.isVisible())
        # Erst NACH dem Zeigen (showEvent synct einmal) die gespeicherten Listen.
        self.a.fixtures = [EfxFixture(fid=1), EfxFixture(fid=2)]
        self.b.fixtures = [EfxFixture(fid=3)]
        self._zeile = lambda f: next(i for i, e in enumerate(
            self.v._visible_instances()) if e.id == f.id)
        self.v._list.setCurrentRow(self._zeile(self.a))
        self.a.fixtures = [EfxFixture(fid=1), EfxFixture(fid=2)]

    def test_refresh_bei_sichtbarem_editor_aendert_nichts(self):
        from src.core.sync import get_sync, SyncEvent
        self._sel = [3]                       # Auswahl passt NICHT zur EFX
        self.v._rebuild_from_state()
        get_sync().emit(SyncEvent.REFRESH_ALL, None)
        self.v._fm.remove(self.b.id)          # FUNCTION_CHANGED -> Rebuild
        self.b = self.v._fm.add(self.b)
        self.assertEqual([1, 2], _efx_fids(self.a))
        self.assertEqual([3], _efx_fids(self.b))

    def test_klick_auf_andere_efx_folgt_weiter_der_auswahl(self):
        self._sel = [1]
        self.v._list.setCurrentRow(self._zeile(self.b))   # Benutzerklick
        self.assertIs(self.b, self.v._current)
        self.assertEqual([1], _efx_fids(self.b))
        self.assertEqual([1, 2], _efx_fids(self.a))

    def test_neu_im_folgemodus_uebernimmt_auswahl(self):
        """„+ Neu" im sichtbaren Folge-Editor: der frische Entwurf bekommt
        weiter die aktuelle Auswahl (Benutzeraktion, kein Laden/Refresh)."""
        self._sel = [2, 3]
        vorher = {f.id for f in self.v._fm.all()}
        self.v._add_efx()
        neu = [f for f in self.v._fm.all() if f.id not in vorher]
        self.addCleanup(lambda: [self.v._fm.remove(f.id) for f in neu])
        self.assertEqual(1, len(neu))
        self.assertIs(neu[0], self.v._current)
        self.assertEqual([2, 3], _efx_fids(neu[0]))
        self.assertEqual([1, 2], _efx_fids(self.a))

    def test_auswahlwechsel_beim_laden_weist_nicht_zu_danach_wieder(self):
        """UI-84 Review: SELECTION_CHANGED waehrend des Lade-Kontexts (und im
        Nachlauf derselben Ereignisschleife) laesst die EFX stehen; ein
        echter Auswahlwechsel danach folgt bei sichtbarem Editor weiter."""
        from src.core.sync import get_sync, SyncEvent
        st = get_state()
        self._sel = [3]
        with st.show_wird_geladen():
            self.assertTrue(st.laedt_show())
            get_sync().emit(SyncEvent.SELECTION_CHANGED, None)
            self.v._sync_follow_selection()
        # Nachlauf: direkt nach dem Laden Aufgelaufenes zaehlt noch dazu.
        self.assertTrue(st.laedt_show())
        get_sync().emit(SyncEvent.SELECTION_CHANGED, None)
        self.assertEqual([1, 2], _efx_fids(self.a))
        for _ in range(3):
            _app().processEvents()
        self.assertFalse(st.laedt_show(), "Nachlauf endet nicht")
        self.assertIs(self.a, self.v._current)
        get_sync().emit(SyncEvent.SELECTION_CHANGED, None)   # Benutzer waehlt
        self.assertEqual([3], _efx_fids(self.a))


class LadeKontextTest(unittest.TestCase):
    """AppState.show_wird_geladen / laedt_show (UI-84)."""

    def test_verschachtelt_und_frist_ohne_ereignisschleife(self):
        st = get_state()
        self.assertFalse(st.laedt_show())
        with st.show_wird_geladen():
            with st.show_wird_geladen():
                pass
            self.assertTrue(st.laedt_show(), "inneres Ende beendet aeusseres")
        self.assertTrue(st.laedt_show())
        # Laeuft keine Ereignisschleife, endet der Nachlauf spaetestens per Frist.
        st._show_lade_nachlauf_bis = 1e-9
        self.assertFalse(st.laedt_show())

    def test_load_show_setzt_kontext(self):
        st = get_state()
        gesehen = []
        with mock.patch.object(SF, "_load_show_impl",
                               lambda p: gesehen.append(st.laedt_show()) or (True, "")):
            SF.load_show("egal.lshow")
        self.assertEqual([True], gesehen)
        for _ in range(3):
            _app().processEvents()
        self.assertFalse(st.laedt_show())


class MatrixFolgeEditorLadenTest(unittest.TestCase):
    """rgb_matrix_view._assign_from_selection schreibt das Grid live in die
    gespeicherte Matrix — beim Laden darf das nicht passieren."""

    def setUp(self):
        _app()
        from src.core.engine.function_manager import get_function_manager
        from src.ui.views.rgb_matrix_view import RgbMatrixView
        self._sel = []
        st = get_state()
        for name, wert in (("get_selected_group_id", lambda: None),
                           ("get_selected_fids", lambda: list(self._sel))):
            p = mock.patch.object(st, name, wert)
            p.start()
            self.addCleanup(p.stop)
        self.fm = get_function_manager()
        self.view = RgbMatrixView(follow_selection=True)
        self.m = self.fm.new_rgb_matrix(name="UI84-Matrix")
        self.addCleanup(lambda: self.fm.remove(self.m.id))
        self.view.show()
        self.m.cols, self.m.rows = 3, 1
        self.m.fixture_grid = [10, 20, 30]
        self.view._saved = self.m
        self.view._current = self.m

    def test_laden_laesst_grid_stehen_danach_folgt_es(self):
        st = get_state()
        self._sel = [7, 8]
        with st.show_wird_geladen():
            self.view._sync_follow_selection()
        self.assertEqual([10, 20, 30], self.m.fixture_grid)
        for _ in range(3):
            _app().processEvents()
        self.view._saved = self.m
        self.view._current = self.m
        self.view._sync_follow_selection()        # echter Auswahlwechsel
        self.assertEqual([7, 8], self.m.fixture_grid)


if __name__ == "__main__":
    unittest.main()


# ── Doku: „folgt der Auswahl“ nennt die Ausnahme beim Laden ──────────────────

@_pytest_xplat15.mark.parametrize("pfad", [
    "docs/anleitung_komplettshow_2026/05_matrix_dimmer/ANLEITUNG.md",
    "docs/anleitung_vc_widgets/19_matrix_editor.md",
    "docs/anleitung_vc_widgets/19_matrix_editor.en.md",
    "docs/anleitung_efx/ANLEITUNG_EFX.md",
])
def test_doku_folgt_der_auswahl_nennt_laden(pfad):
    """Wer „folgt der Auswahl“ verspricht, sagt auch: nicht beim Laden."""
    from pathlib import Path
    text = (Path(__file__).resolve().parent.parent / pfad).read_text(
        encoding="utf-8")
    zeilen = [z for z in text.split("\n")
              if "Laden einer Show" in z or "loading a show" in z]
    assert zeilen, pfad
    assert any(("Auswahl" in z or "selection" in z) for z in zeilen), pfad
