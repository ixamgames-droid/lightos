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


if __name__ == "__main__":
    unittest.main()
