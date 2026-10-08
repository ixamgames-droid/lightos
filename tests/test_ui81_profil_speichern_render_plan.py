"""UI-81: ein bearbeitetes, gepatchtes Profil kommt beim DMX-Renderer an.

Nach dem Speichern im Profil-Editor liefen nur ``clear_channel_cache()`` und
``REFRESH_ALL``. Kein Handler baute ``_reload_patch_cache`` bzw.
``_rebuild_render_plan`` neu — der Renderer schrieb weiter auf die ALTEN
Kanaele und Defaults, bis jemand den Patch aenderte.

Jetzt ruft der Editor ``app_state.profil_geaendert(profil_id)``: Kanal-Cache
verwerfen, betroffene Geraete neu aufbauen, ``patch_changed`` senden (2D/3D,
Programmer, gezielte Blackouts ziehen mit).

Gemessen ueber den echten Editor-Dialog (eigene Fixture-DB) und den echten
``_render_frame``.
"""
from __future__ import annotations

import os
import tempfile
import threading
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication                     # noqa: E402

import src.core.app_state as A                                 # noqa: E402
from src.core.app_state import AppState, clear_channel_cache   # noqa: E402
from src.core.database import fixture_db as FDB                # noqa: E402
from src.core.database.fixture_db import get_engine            # noqa: E402
from src.core.database.models import create_all_idempotent     # noqa: E402
from src.core.dmx.output_manager import OutputManager          # noqa: E402
from src.ui.widgets import fixture_editor as editor_module     # noqa: E402

_app = QApplication.instance() or QApplication([])

import pytest as _pytest_xplat15                               # noqa: E402
from _qt_lifecycle import destroy_all_top_level_widgets        # noqa: E402


@_pytest_xplat15.fixture(autouse=True)
def _xplat15_no_leaked_widgets():
    yield
    destroy_all_top_level_widgets(QApplication.instance())


class _Fx:
    protocol = ""

    def __init__(self, fid, universe, address, profile_id, mode, count):
        self.fid = fid
        self.universe = universe
        self.address = address
        self.fixture_profile_id = profile_id
        self.mode_name = mode
        self.channel_count = count
        self.fixture_type = "par"
        self.fixture_name = f"fx{fid}"


class _FM:
    def tick(self, universes, patch_cache, dt):
        pass


_VORHER = [{"name": "Dimmer", "attribute": "dimmer", "default": 0},
           {"name": "Rot", "attribute": "color_r", "default": 0}]
# Reihenfolge getauscht und neuer Default am Rot-Kanal.
_NACHHER = [{"name": "Rot", "attribute": "color_r", "default": 77},
            {"name": "Dimmer", "attribute": "dimmer", "default": 0}]


class ProfilSpeichernRenderPlanTest(unittest.TestCase):

    def setUp(self):
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.addCleanup(lambda: os.path.exists(path) and os.remove(path))
        self.engine = get_engine(path)
        self.addCleanup(self.engine.dispose)
        create_all_idempotent(self.engine)
        for p in (mock.patch.object(editor_module, "engine", lambda: self.engine),
                  mock.patch.object(FDB, "_engine", self.engine),
                  mock.patch.object(editor_module.QMessageBox, "information"),
                  mock.patch.object(editor_module.QMessageBox, "warning",
                                    lambda *a, **k: 0)):
            p.start()
            self.addCleanup(p.stop)
        clear_channel_cache()
        self.addCleanup(clear_channel_cache)

        self.pid = self._speichern(None, _VORHER)
        om = OutputManager()
        om.add_universe(1)
        st = AppState.__new__(AppState)
        st.universes = om.universes
        st.output_manager = om
        st.programmer = {1: {"dimmer": 200}}
        st.playback_engine = None
        st.function_manager = _FM()
        st._show_engine = None
        st._patch_cache = [_Fx(1, 1, 1, self.pid, "Standard", 2)]
        st._prog_lock = threading.RLock()
        st.laser_estop_active = False
        st._laser_estop_addrs = {}
        st._laser_fids = frozenset()
        st.base_levels = {}
        st._engine_extra_prev = {}
        st._suppress_emits = True
        self.events = []
        st._emit = lambda ev, *a, **k: self.events.append(ev)
        st._rebuild_render_plan()
        self.st = st
        # Der Editor erreicht den laufenden State ueber den Singleton.
        p = mock.patch.object(A, "_state", st)
        p.start()
        self.addCleanup(p.stop)

    def _speichern(self, pid, kanaele) -> int:
        dlg = editor_module.FixtureEditorDialog(fixture_id=pid)
        self.addCleanup(dlg.deleteLater)
        if pid is None:
            dlg._cb_manufacturer.setCurrentText("Eigenbau")
            dlg._edit_name.setText("Testlampe UI81")
            dlg._edit_short.setText("UI81")
            dlg._cb_type.setCurrentText("par")
        dlg._tabs.widget(0).load_mode_data("Standard", kanaele)
        dlg._save()
        self.assertIsNotNone(dlg._saved_id)
        return dlg._saved_id

    def _frame(self):
        self.st._render_frame(0.025)
        return self.st.universes[1].get_all()

    def test_vorher_alte_belegung(self):
        d = self._frame()
        self.assertEqual((d[0], d[1]), (200, 0))

    def test_nach_speichern_neue_kanalreihenfolge_und_default(self):
        self.events.clear()
        self.assertEqual(self._speichern(self.pid, _NACHHER), self.pid)
        d = self._frame()
        self.assertEqual(d[1], 200, "Dimmer liegt jetzt auf Kanal 2")
        self.assertEqual(d[0], 77, "neuer Default des Rot-Kanals")
        self.assertIn("patch_changed", self.events)

    def test_fremdes_profil_baut_nicht_neu(self):
        self.events.clear()
        self.assertFalse(self.st.profil_geaendert(self.pid + 999))
        self.assertNotIn("patch_changed", self.events)


if __name__ == "__main__":
    unittest.main()
