"""FM-12 — expliziter 3D-Modell-Override am FixtureProfile + Generator-Auswahl.

Geprueft wird die ganze Kette:

- ``suggest_viz_model``: reine Heuristik (ohne DB) — identische Regeln wie
  ``viz_model_for`` (Banks/Pan/Tilt, Laser-Gate aus FLA-1).
- Migration: eine alte ``fixtures``-Tabelle OHNE ``viz_model``-Spalte bekommt
  sie per ``migrate_fixtures_db`` nachgezogen (Bestandsdaten bleiben).
- Payload/Speichern: ``build_profile_payload`` traegt ``viz_model``,
  ``create_user_profile`` persistiert es.
- Routing: ``viz_model_for`` liefert den Profil-Override VOR der Heuristik;
  ohne Override bleibt das bisherige Verhalten (par_bar aus 4 RGB-Banks).
- Generator-UI: "3D-Modell"-Combo existiert, zeigt den Automatik-Vorschlag
  der echten Heuristik und schreibt die explizite Wahl ins Modell/Payload.

Headless (QT_QPA_PLATFORM=offscreen); eigene Temp-DB pro Test — die echte
fixtures.db wird nicht beruehrt.
"""
import os
import tempfile
import types
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("LIGHTOS_SERIAL_INPROC", "1")
os.environ.setdefault("LIGHTOS_NO_OUTPUT_THREAD", "1")

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from src.core.app_state import (
    suggest_viz_model, viz_model_for, viz_model_override_for,
    clear_channel_cache,
)
from src.core.database.models import FixtureProfile, migrate_fixtures_db
from src.ui.widgets.fixture_generator import (
    GeneratorModel, GenMode, GenChannel,
    build_profile_payload, save_generated_profile,
)


def _temp_engine():
    from src.core.database.fixture_db import get_engine
    return get_engine(tempfile.mktemp(suffix=".db"))


def _rgb_bank(prefix):
    return [GenChannel(f"{prefix} Rot", "color_r"),
            GenChannel(f"{prefix} Gruen", "color_g"),
            GenChannel(f"{prefix} Blau", "color_b")]


def _par_bar_model(viz_model=""):
    """4 RGB-Banks ohne Bewegung -> Heuristik: par_bar."""
    channels = []
    for i in range(1, 5):
        channels.extend(_rgb_bank(f"Kopf {i}"))
    return GeneratorModel(
        manufacturer="TestMfr", model="ATest Bar", short_name="ATESTBAR",
        fixture_type="led_bar", viz_model=viz_model,
        modes=[GenMode("12ch", channels)],
    )


class SuggestVizModelTest(unittest.TestCase):
    """Reine Heuristik — Regeln identisch zu viz_model_for (FM-3/4/7)."""

    def test_single_head_is_none(self):
        self.assertIsNone(suggest_viz_model("par", ["color_r", "color_g", "color_b"]))

    def test_four_rgb_banks_without_movement_is_par_bar(self):
        attrs = ["color_r", "color_g", "color_b"] * 4
        self.assertEqual(suggest_viz_model("led_bar", attrs), "par_bar")

    def test_two_pan_heads_is_mover_bar(self):
        attrs = ["pan", "tilt", "color_r", "pan", "tilt", "color_r"]
        self.assertEqual(suggest_viz_model("moving_head", attrs), "mover_bar")

    def test_movement_without_per_head_pan_is_spider(self):
        attrs = ["tilt", "color_r", "color_g", "tilt", "color_r", "color_g"]
        self.assertEqual(suggest_viz_model("moving_head", attrs), "spider")

    def test_laser_never_multihead(self):
        # FLA-1: zwei color_r machen aus einem Laser keinen Spider.
        attrs = ["color_r", "color_r", "pan", "tilt"]
        self.assertIsNone(suggest_viz_model("laser", attrs))


class MigrationAddsVizModelTest(unittest.TestCase):
    def test_old_db_gets_viz_model_column(self):
        eng = create_engine(f"sqlite:///{tempfile.mktemp(suffix='.db')}")
        with eng.begin() as conn:
            conn.execute(text(
                "CREATE TABLE fixtures ("
                " id INTEGER PRIMARY KEY, manufacturer_id INTEGER,"
                " name VARCHAR(120), short_name VARCHAR(40),"
                " fixture_type VARCHAR(40), power_w INTEGER,"
                " notes TEXT, source VARCHAR(20))"))
            conn.execute(text(
                "INSERT INTO fixtures (manufacturer_id, name, short_name,"
                " fixture_type, power_w, notes, source)"
                " VALUES (1, 'Alt', 'ALT', 'par', 0, '', 'user')"))
        migrate_fixtures_db(eng)
        with eng.connect() as conn:
            cols = {row[1] for row in conn.execute(text("PRAGMA table_info(fixtures)"))}
            self.assertIn("viz_model", cols)
            val = conn.execute(text("SELECT viz_model FROM fixtures")).scalar_one()
            self.assertEqual(val or "", "")   # Bestandsdaten -> Automatik


class PayloadAndSaveTest(unittest.TestCase):
    def test_payload_carries_viz_model(self):
        payload = build_profile_payload(_par_bar_model(viz_model="mover_bar"))
        self.assertEqual(payload["viz_model"], "mover_bar")

    def test_default_is_empty_automatic(self):
        payload = build_profile_payload(_par_bar_model())
        self.assertEqual(payload["viz_model"], "")

    def test_save_persists_viz_model(self):
        eng = _temp_engine()
        pid = save_generated_profile(
            build_profile_payload(_par_bar_model(viz_model="spider")), engine=eng)
        with Session(eng) as s:
            prof = s.get(FixtureProfile, pid)
            self.assertEqual(prof.viz_model, "spider")


class OverrideRoutingTest(unittest.TestCase):
    """viz_model_for: Profil-Override gewinnt; ohne Override alte Heuristik."""

    def setUp(self):
        import src.core.database.fixture_db as fdb
        self._fdb = fdb
        self._orig_engine = fdb.engine
        self._eng = _temp_engine()
        fdb.engine = lambda: self._eng
        clear_channel_cache()

    def tearDown(self):
        self._fdb.engine = self._orig_engine
        clear_channel_cache()

    def _fake_fixture(self, pid, ftype="led_bar", channels=12):
        return types.SimpleNamespace(
            fixture_profile_id=pid, fixture_type=ftype,
            mode_name="12ch", channel_count=channels,
            spider_dual_tilt=False)

    def test_without_override_heuristic_stays(self):
        pid = save_generated_profile(
            build_profile_payload(_par_bar_model()), engine=self._eng)
        f = self._fake_fixture(pid)
        self.assertEqual(viz_model_override_for(f), "")
        self.assertEqual(viz_model_for(f), "par_bar")

    def test_override_wins_even_for_single_head_model(self):
        pid = save_generated_profile(
            build_profile_payload(_par_bar_model(viz_model="moving_head")),
            engine=self._eng)
        f = self._fake_fixture(pid)
        self.assertEqual(viz_model_override_for(f), "moving_head")
        # Override schlaegt die par_bar-Heuristik.
        self.assertEqual(viz_model_for(f), "moving_head")

    def test_transient_db_error_is_not_cached(self):
        """Review-Fix (MEDIUM): Ein DB-Fehler darf nicht als '' eingefroren
        werden — der naechste Aufruf muss es erneut versuchen."""
        import src.core.app_state as APS
        pid = save_generated_profile(
            build_profile_payload(_par_bar_model(viz_model="spider")),
            engine=self._eng)
        f = self._fake_fixture(pid)

        def _boom():
            raise RuntimeError("fixtures.db gesperrt")
        self._fdb.engine = _boom
        self.assertEqual(viz_model_override_for(f), "")
        self.assertNotIn(pid, APS._viz_model_override_cache)
        # DB wieder da -> echter Wert, kein vergifteter Cache.
        self._fdb.engine = lambda: self._eng
        self.assertEqual(viz_model_override_for(f), "spider")

    def test_cache_cleared_on_clear_channel_cache(self):
        pid = save_generated_profile(
            build_profile_payload(_par_bar_model(viz_model="spider")),
            engine=self._eng)
        f = self._fake_fixture(pid)
        self.assertEqual(viz_model_override_for(f), "spider")
        with Session(self._eng) as s:
            prof = s.get(FixtureProfile, pid)
            prof.viz_model = "par"
            s.commit()
        # Noch gecached …
        self.assertEqual(viz_model_override_for(f), "spider")
        clear_channel_cache()
        # … nach Invalidierung frisch aus der DB.
        self.assertEqual(viz_model_override_for(f), "par")


class PrewarmOnPatchMutationTest(unittest.TestCase):
    """Review-Fix (MEDIUM): _rebuild_render_plan waermt den Override-Cache vor,
    damit der 20-FPS-Paint-Pfad der Live-View nach einer Patch-Aenderung keine
    synchronen DB-Sessions auf dem GUI-Thread zahlt (Muster = Channel-Cache)."""

    def setUp(self):
        from src.core.show.show_file import reset_show
        from src.core.database.fixture_db import ensure_builtins
        ensure_builtins()
        reset_show()

    def tearDown(self):
        from src.core.show.show_file import reset_show
        reset_show()

    def test_add_fixture_prewarms_override_cache(self):
        import src.core.app_state as APS
        from src.core.app_state import get_state
        from src.core.database.fixture_db import engine as fdb_engine
        from src.core.database.models import PatchedFixture, FixtureProfile
        from sqlalchemy import select
        with Session(fdb_engine()) as s:
            pid = int(s.execute(select(FixtureProfile.id).where(
                FixtureProfile.short_name == "ZQ01424")).scalar_one())
        state = get_state()
        state.add_fixture(PatchedFixture(
            fid=901, label="PAR", fixture_profile_id=pid,
            mode_name="8-Kanal RGBW", universe=1, address=400, channel_count=8,
            manufacturer_name="Generic", fixture_name="Stage Light ZQ01424",
            fixture_type="par"), undoable=False)
        # add_fixture -> _reload_patch_cache -> clear + Prewarm: der Cache
        # muss den Profil-Eintrag OHNE weiteren viz_model_for-Aufruf enthalten.
        self.assertIn(pid, APS._viz_model_override_cache)


class GeneratorDialogVizModelTest(unittest.TestCase):
    """Die "3D-Modell"-Combo im Generator: Vorschlag + explizite Wahl."""

    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def _dialog(self, model):
        from src.ui.widgets.fixture_generator import FixtureGeneratorDialog
        dlg = FixtureGeneratorDialog(model=model)
        self.addCleanup(dlg.deleteLater)
        return dlg

    def test_suggestion_shows_heuristic_result(self):
        dlg = self._dialog(_par_bar_model())
        self.assertIn("PAR-Bar", dlg._cb_vizmodel.itemText(0))
        self.assertEqual(dlg._cb_vizmodel.currentData(), "")

    def test_explicit_choice_lands_in_model_and_payload(self):
        dlg = self._dialog(_par_bar_model())
        idx = dlg._cb_vizmodel.findData("mover_bar")
        self.assertGreaterEqual(idx, 0)
        dlg._cb_vizmodel.setCurrentIndex(idx)
        dlg._sync_all()
        self.assertEqual(dlg._model.viz_model, "mover_bar")
        self.assertEqual(dlg._model.to_payload()["viz_model"], "mover_bar")

    def test_dialog_restores_saved_override(self):
        dlg = self._dialog(_par_bar_model(viz_model="spider"))
        self.assertEqual(dlg._cb_vizmodel.currentData(), "spider")


if __name__ == "__main__":
    unittest.main()
