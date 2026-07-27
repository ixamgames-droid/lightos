"""3D-Visualizer: echte Farbe + echte Helligkeit statt "kein RGB-Kanal = schwarz".

Der Visualizer-Payload las frueher NUR ``color_r/g/b`` (Default 0) und NUR
``intensity`` (Default 255). Zwei Folgen, beide hier festgenagelt:

  (A) **Geraete ohne RGB-Kanaele wurden schwarz gerendert.** Betroffen sind reale
      Builtins: Martin Atomic 3000 (Strobe/Blinder — nur shutter/rate/duration),
      Robe Pointe/MegaPointe (intensity + Farbrad, KEIN color_r) und jeder reine
      Dimmer-PAR. Schwarz heisst im 3D unsichtbar (additiver Kegel, SpotLight
      ohne Emission) — das Geraet blitzte auf dem echten Rig, im Visualizer
      passierte nichts.
  (B) **Geraete ohne Dimmer-Kanal galten als dauerhaft voll aufgedreht** —
      ein Xenon-Strobe mit geschlossenem Shutter leuchtete im 3D weiter.

Dazu die JS-Seite (A3D-25/A3D-28): die Sichtbarkeit von Beam/SpotLight/FloorSpot
haengt jetzt an der EFFEKTIVEN Leuchtdichte (Dimmer x hellster Farbkanal) statt
am Dimmer allein — ein Fixture mit offenem Dimmer und Farbe 0/0/0 kostete sonst
in jedem beleuchteten Fragment Shading und belegte einen Shadow-Slot, ohne
irgendetwas zu emittieren.
"""
import json
import os
import tempfile
import time
import unittest
from types import SimpleNamespace

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from src.core.color_utils import visual_intensity, visual_rgb
from src.ui.visualizer.visualizer_service import _build_fixture_payload


def _rng(lo, hi, name, kind=""):
    return SimpleNamespace(range_from=lo, range_to=hi, name=name, kind=kind)


def _ch(attribute, ranges=()):
    return SimpleNamespace(attribute=attribute, ranges=list(ranges))


def _fx(fid=1):
    return SimpleNamespace(fid=fid)


# ── (1) Farb-Ableitung ───────────────────────────────────────────────────────
class VisualRgbTest(unittest.TestCase):
    def test_rgb_path_unchanged(self):
        """Der bisherige RGB(W)-Pfad muss BYTE-identisch bleiben (Weiss additiv,
        geklemmt) — sonst faerbt sich Davids ganzes Rig um."""
        attrs = {"color_r": 200, "color_g": 0, "color_b": 0, "color_w": 100}
        self.assertEqual(visual_rgb(attrs), (255, 100, 100))

    def test_rgb_all_zero_stays_black(self):
        """RGB-Kanaele VORHANDEN und auf 0 = bewusster RGB-Blackout -> schwarz
        bleibt schwarz (nur das Fehlen der Kanaele loest den Weiss-Fallback aus)."""
        self.assertEqual(visual_rgb({"color_r": 0, "color_g": 0, "color_b": 0}),
                         (0, 0, 0))

    def test_no_color_channels_is_white(self):
        """Dimmer-PAR / Strobe / Blinder: keine Farbkanaele -> Lampenfarbe weiss."""
        self.assertEqual(visual_rgb({"intensity": 255}), (255, 255, 255))
        self.assertEqual(visual_rgb({}), (255, 255, 255))

    def test_cmy_is_subtractive(self):
        """CMY-Mover: voll Cyan filtert Rot heraus -> (0, 255, 255)."""
        self.assertEqual(visual_rgb({"cmy_c": 255, "cmy_m": 0, "cmy_y": 0}),
                         (0, 255, 255))
        # offenes CMY (alles 0) = weiss
        self.assertEqual(visual_rgb({"cmy_c": 0, "cmy_m": 0, "cmy_y": 0}),
                         (255, 255, 255))
        # Alternativ-Vokabular cyan/magenta/yellow
        self.assertEqual(visual_rgb({"cyan": 0, "magenta": 255, "yellow": 0}),
                         (255, 0, 255))

    def test_color_wheel_slot_by_name(self):
        """Farbrad: der Slot unter dem aktuellen DMX-Wert liefert die Farbe."""
        wheel = _ch("color_wheel", [
            _rng(0, 9, "Offen", "open"),
            _rng(10, 19, "Rot", "color"),
            _rng(20, 29, "Blau", "color"),
        ])
        self.assertEqual(visual_rgb({"color_wheel": 15}, [wheel]), (255, 48, 48))
        self.assertEqual(visual_rgb({"color_wheel": 25}, [wheel]), (48, 96, 255))
        self.assertEqual(visual_rgb({"color_wheel": 3}, [wheel]), (255, 255, 255))

    def test_color_wheel_unknown_slot_is_open_white(self):
        """Slot ohne erkennbares Farbwort (oder ganz ohne Range-Daten): das Rad
        steht im Zweifel auf 'offen' -> weiss, NICHT schwarz."""
        wheel = _ch("color_wheel", [_rng(0, 255, "Slot 7")])
        self.assertEqual(visual_rgb({"color_wheel": 100}, [wheel]), (255, 255, 255))
        self.assertEqual(visual_rgb({"color_wheel": 100}, None), (255, 255, 255))

    def test_rgb_wins_over_wheel(self):
        """Geraet mit BEIDEM (RGB + Farbrad): RGB gewinnt — es ist der feinere
        und vom Programmer bediente Pfad."""
        wheel = _ch("color_wheel", [_rng(0, 255, "Rot", "color")])
        self.assertEqual(visual_rgb({"color_r": 0, "color_g": 255, "color_b": 0,
                                     "color_wheel": 10}, [wheel]), (0, 255, 0))


# ── (2) Helligkeits-Ableitung ────────────────────────────────────────────────
class VisualIntensityTest(unittest.TestCase):
    def test_intensity_channel(self):
        self.assertEqual(visual_intensity({"intensity": 77}), 77)

    def test_dimmer_and_master_are_dimmers_too(self):
        """Nicht jedes Profil nennt den Dimmer 'intensity' — 'dimmer'/'master'
        sind dieselbe Sache (attr_groups Intensity-Gruppe)."""
        self.assertEqual(visual_intensity({"dimmer": 42}), 42)
        self.assertEqual(visual_intensity({"master": 9}), 9)

    def test_no_dimmer_no_shutter_is_full(self):
        """Geraet ohne steuerbaren Dimmer leuchtet konstant."""
        self.assertEqual(visual_intensity({"pan": 128}), 255)

    def test_shutter_only_uses_range_kind(self):
        """Xenon-Strobe ohne Dimmer: der Shutter IST die Helligkeit. Ausgewertet
        ueber die maschinenlesbare ChannelRange.kind."""
        shutter = _ch("shutter", [
            _rng(0, 5, "Blackout", "closed"),
            _rng(6, 249, "Blitzrate", "strobe"),
            _rng(250, 255, "Blinder", "open"),
        ])
        self.assertEqual(visual_intensity({"shutter": 0}, [shutter]), 0)
        self.assertEqual(visual_intensity({"shutter": 3}, [shutter]), 0)
        self.assertEqual(visual_intensity({"shutter": 128}, [shutter]), 255)
        self.assertEqual(visual_intensity({"shutter": 255}, [shutter]), 255)

    def test_shutter_without_ranges_never_guesses_dark(self):
        """Ohne Range-Daten wird NICHT geraten: die Bedeutung von "Shutter 0" ist
        geraeteabhaengig (Atomic 3000 = Blackout, viele LED-PARs = offen). Ein
        falsches "zu" wuerde ein laufendes Geraet unsichtbar machen."""
        self.assertEqual(visual_intensity({"shutter": 0}, None), 255)
        self.assertEqual(visual_intensity({"shutter": 200}, None), 255)

    def test_dimmer_wins_over_shutter(self):
        """Geraet mit Dimmer UND Shutter: der Dimmer entscheidet (bisheriges
        Verhalten) — der Shutter ist nur der Notnagel fuer dimmerlose Geraete."""
        shutter = _ch("shutter", [_rng(0, 255, "Blackout", "closed")])
        self.assertEqual(visual_intensity({"intensity": 180, "shutter": 0},
                                          [shutter]), 180)


# ── (3) Payload-Verdrahtung ──────────────────────────────────────────────────
class PayloadWiringTest(unittest.TestCase):
    def test_colorless_payload_is_white_and_keeps_dimmer(self):
        p = _build_fixture_payload(_fx(), {"intensity": 128})
        self.assertEqual((p["r"], p["g"], p["b"]), (255, 255, 255))
        self.assertEqual(p["intensity"], 128)

    def test_rgb_payload_unchanged(self):
        p = _build_fixture_payload(_fx(), {"color_r": 10, "color_g": 20,
                                           "color_b": 30, "color_w": 5,
                                           "intensity": 200})
        self.assertEqual((p["r"], p["g"], p["b"]), (15, 25, 35))
        self.assertEqual(p["intensity"], 200)

    def test_head_without_own_color_inherits_device_color(self):
        """Mover-Bar ohne Farbkanaele: die Koepfe erben die Geraetefarbe (weiss),
        statt als schwarze Einzel-Beams zu verschwinden."""
        attrs = {"intensity": 255, "pan": 10, "tilt": 20,
                 "pan#1": 11, "tilt#1": 21}
        p = _build_fixture_payload(_fx(), attrs)
        heads = p["heads"]
        self.assertEqual(len(heads), 2)
        for h in heads:
            self.assertEqual((h["r"], h["g"], h["b"]), (255, 255, 255))
            self.assertEqual((h["cr"], h["cg"], h["cb"]), (255, 255, 255))

    def test_head_with_own_color_unchanged(self):
        """Regression: Koepfe MIT eigenen Farbkanaelen bleiben exakt wie bisher
        (auch der bewusst dunkle Kopf)."""
        attrs = {"intensity": 255, "tilt": 40, "tilt#1": 210,
                 "color_r": 255, "color_g": 0, "color_b": 0, "color_w": 0,
                 "color_r#1": 0, "color_g#1": 0, "color_b#1": 0, "color_w#1": 0}
        heads = _build_fixture_payload(_fx(), attrs)["heads"]
        self.assertEqual((heads[0]["r"], heads[0]["g"], heads[0]["b"]), (255, 0, 0))
        self.assertEqual((heads[1]["r"], heads[1]["g"], heads[1]["b"]), (0, 0, 0))


# ── (4) Echte Builtins aus der Fixture-DB ────────────────────────────────────
def _temp_seeded_engine():
    from src.core.database import fixture_db as FDB
    from src.core.database.fixture_db import get_engine, _seed
    saved = FDB._engine
    eng = get_engine(tempfile.mktemp(suffix=".db"))
    with Session(eng) as s:
        _seed(s)
        s.commit()
    FDB._engine = eng
    return FDB, eng, saved


def _load(session, short):
    from src.core.database.models import (
        FixtureChannel, FixtureMode, FixtureProfile,
    )
    return session.execute(
        select(FixtureProfile)
        .options(
            selectinload(FixtureProfile.manufacturer),
            selectinload(FixtureProfile.modes)
            .selectinload(FixtureMode.channels)
            .selectinload(FixtureChannel.ranges),
        )
        .where(FixtureProfile.short_name == short)
    ).scalars().first()


class RealBuiltinsTest(unittest.TestCase):
    """Der eigentliche Bug-Beweis: zwei ECHTE Builtins, die bisher schwarz waren."""

    @classmethod
    def setUpClass(cls):
        cls._FDB, cls._eng, cls._saved = _temp_seeded_engine()

    @classmethod
    def tearDownClass(cls):
        cls._FDB._engine = cls._saved

    def _channels_of(self, short, mode_name=None):
        with Session(self._eng) as s:
            prof = _load(s, short)
            self.assertIsNotNone(prof, f"Builtin {short} fehlt in der DB")
            modes = list(prof.modes)
            mode = next((m for m in modes if m.name == mode_name), None) if mode_name else None
            mode = mode or modes[-1]
            return [SimpleNamespace(attribute=c.attribute,
                                    ranges=[_rng(r.range_from, r.range_to, r.name,
                                                 r.kind or "")
                                            for r in c.ranges])
                    for c in mode.channels]

    def test_atomic3000_blinder_is_visible_white(self):
        """Martin Atomic 3000 (Xenon-Strobe/Blinder): KEINE Farb- und KEINE
        Dimmer-Kanaele. Vorher: Farbe schwarz + Helligkeit hart 255 (unsichtbar
        UND dauerhaft an). Jetzt: weiss, und der Shutter steuert die Helligkeit."""
        chans = self._channels_of("ATOMIC3000")
        attrs = {c.attribute: 0 for c in chans}
        self.assertNotIn("color_r", attrs, "Profil-Annahme: Atomic hat kein RGB")
        self.assertIn("shutter", attrs, "Profil-Annahme: Atomic hat einen Shutter")

        # Shutter zu -> dunkel (vorher: dauerhaft hell)
        p = _build_fixture_payload(_fx(), dict(attrs), chans)
        self.assertEqual(p["intensity"], 0)

        # Blinder-Dauerlicht -> hell UND weiss (vorher: schwarz)
        attrs["shutter"] = 255
        p = _build_fixture_payload(_fx(), dict(attrs), chans)
        self.assertEqual(p["intensity"], 255)
        self.assertEqual((p["r"], p["g"], p["b"]), (255, 255, 255))

    def test_robe_pointe_dimmer_and_wheel_are_visible(self):
        """Robe Pointe: Dimmer + Farbrad, KEIN color_r. Vorher schwarz bei jedem
        Dimmerwert; jetzt traegt der Payload eine sichtbare Farbe."""
        chans = self._channels_of("POINTE")
        attrs = {c.attribute: 0 for c in chans}
        self.assertNotIn("color_r", attrs, "Profil-Annahme: Pointe hat kein RGB")
        self.assertIn("intensity", attrs, "Profil-Annahme: Pointe hat einen Dimmer")
        attrs["intensity"] = 255
        p = _build_fixture_payload(_fx(), attrs, chans)
        self.assertGreater(max(p["r"], p["g"], p["b"]), 0,
                           "Pointe darf im 3D nicht schwarz sein")


# ── (5) JS: Culling nach effektiver Leuchtdichte (A3D-25/A3D-28) ─────────────
from PySide6.QtCore import QObject, QUrl, Signal, Slot          # noqa: E402
from PySide6.QtWebChannel import QWebChannel                     # noqa: E402
from PySide6.QtWebEngineCore import (QWebEngineProfile,          # noqa: E402
                                     QWebEngineSettings)
from PySide6.QtWebEngineWidgets import QWebEngineView            # noqa: E402
from PySide6.QtWidgets import QApplication                       # noqa: E402

_app = QApplication.instance() or QApplication([])

_HTML_PATH = os.path.normpath(os.path.join(
    os.path.dirname(__file__), "..", "src", "ui", "visualizer", "stage_scene.html"))

_LOAD_TIMEOUT_S = 40.0
_POLL_TIMEOUT_S = 10.0
_POLL_INTERVAL_S = 0.05

# 1:1 aus visualizer_window.py::VisualizerBridge (bridge.js guardet jeden
# Connect mit ``if (bridge.X)``) — gleiche Liste wie test_viz13c1_topdown_polish.
_SIGNAL_SPECS = [
    ("fixtureAdded", (str,)), ("fixtureRemoved", (int,)), ("dmxBatch", (str,)),
    ("allFixtures", (str,)), ("settingsChanged", (str,)),
    ("viewModeChanged", (str,)), ("editModeChanged", (str,)),
    ("stageLoaded", (str,)), ("addStageObject", (str,)),
    ("removeStageObject", (str,)), ("selectStageObject", (str,)),
    ("applyFixtureTransform", (str,)), ("alignSelected", (str,)),
    ("distributeSelected", (str,)), ("cameraReset", ()),
    ("brightnessSignal", (float,)), ("brightnessAutoSignal", ()),
    ("updateStageObject", (str,)), ("resizeModeSignal", (bool,)),
    ("pixelRatioSignal", (float,)),
]


def _make_mock_bridge_class():
    attrs = {name: Signal(*types) for name, types in _SIGNAL_SPECS}

    @Slot()
    def requestFixtures(self):
        self._request_fixtures_calls = getattr(self, "_request_fixtures_calls", 0) + 1

    attrs["requestFixtures"] = requestFixtures
    attrs["requestFullResync"] = Signal()
    return type("MockVisualizerBridge", (QObject,), attrs)


_MockVisualizerBridge = _make_mock_bridge_class()

_FIXTURES_PAYLOAD = json.dumps([
    {"fid": 21, "type": "par", "x": 0, "y": 2, "z": 0,
     "r": 0, "g": 0, "b": 0, "intensity": 0},
])


class LuminanceCullingJsTest(unittest.TestCase):
    """Gegen die ECHTE stage_scene.html (Harness wie test_viz13c1_topdown_polish)."""

    def setUp(self):
        self.assertTrue(os.path.isfile(_HTML_PATH), f"stage_scene.html fehlt: {_HTML_PATH}")
        self._view = QWebEngineView()
        try:
            profile = self._view.page().profile()
            profile.setHttpCacheType(QWebEngineProfile.HttpCacheType.NoCache)
            profile.setPersistentCookiesPolicy(
                QWebEngineProfile.PersistentCookiesPolicy.NoPersistentCookies)
        except Exception:
            pass
        s = self._view.settings()
        s.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
        s.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
        self._bridge_obj = _MockVisualizerBridge()
        self._channel = QWebChannel(self._view)
        self._channel.registerObject("bridge", self._bridge_obj)
        self._view.page().setWebChannel(self._channel)
        self._loaded_ok = []
        self._view.loadFinished.connect(self._loaded_ok.append)

    def tearDown(self):
        try:
            self._view.deleteLater()
        except Exception:
            pass
        self._pump(0.2)

    @staticmethod
    def _pump(seconds):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            _app.processEvents()
            time.sleep(_POLL_INTERVAL_S)

    def _eval(self, js_expr):
        box = []
        self._view.page().runJavaScript(js_expr, lambda result: box.append(result))
        deadline = time.monotonic() + _POLL_TIMEOUT_S
        while not box and time.monotonic() < deadline:
            _app.processEvents()
            time.sleep(_POLL_INTERVAL_S)
        self.assertTrue(box, f"runJavaScript-Callback nie ausgeloest fuer: {js_expr}")
        return box[0]

    def _poll_until_true(self, js_expr, timeout_s=_POLL_TIMEOUT_S):
        deadline = time.monotonic() + timeout_s
        last = None
        while time.monotonic() < deadline:
            last = self._eval(js_expr)
            if last:
                return last
            time.sleep(_POLL_INTERVAL_S)
        self.fail(f"Timeout beim Warten auf truthy '{js_expr}' (letzter: {last!r})")

    def _emit_until_true(self, emit_fn, js_expr, timeout_s=_POLL_TIMEOUT_S):
        deadline = time.monotonic() + timeout_s
        last = None
        while time.monotonic() < deadline:
            emit_fn()
            last = self._eval(js_expr)
            if last:
                return last
            time.sleep(_POLL_INTERVAL_S)
        self.fail(f"Timeout nach wiederholtem Emit fuer '{js_expr}' (letzter: {last!r})")

    def _load_and_wait(self):
        self._loaded_ok.clear()
        url = QUrl.fromLocalFile(_HTML_PATH)
        url.setQuery(f"v={int(time.time() * 1000)}")
        self._view.load(url)
        deadline = time.monotonic() + _LOAD_TIMEOUT_S
        while not self._loaded_ok and time.monotonic() < deadline:
            _app.processEvents()
            time.sleep(_POLL_INTERVAL_S)
        self.assertTrue(self._loaded_ok, "loadFinished nie ausgeloest (Timeout)")
        self.assertTrue(self._loaded_ok[-1], "loadFinished(ok=False)")
        self.assertTrue(self._poll_until_true("!!window.__lightosAppReady"))

    def _push_dmx(self, r, g, b, intensity):
        payload = json.dumps([{"fid": 21, "r": r, "g": g, "b": b,
                               "intensity": intensity, "pan": 128, "tilt": 128}])
        self._bridge_obj.dmxBatch.emit(payload)

    def test_black_at_full_dimmer_is_culled_bright_color_is_visible(self):
        self._load_and_wait()
        self._emit_until_true(
            lambda: self._bridge_obj.allFixtures.emit(_FIXTURES_PAYLOAD),
            "typeof window.__lightos.fixtures['21'] === 'object'", timeout_s=8.0)

        # (a) Dimmer voll offen, Farbe schwarz -> nichts wird emittiert, also
        #     darf auch kein SpotLight/Beam sichtbar bleiben (A3D-25/A3D-28).
        self._emit_until_true(
            lambda: self._push_dmx(0, 0, 0, 255),
            "window.__lightos.fixtures['21'].spot.visible === false")
        self.assertFalse(self._eval("window.__lightos.fixtures['21'].beam.visible"))

        # (b) Gegenprobe: helle Farbe bei gleichem Dimmer -> sichtbar.
        self._emit_until_true(
            lambda: self._push_dmx(255, 255, 255, 255),
            "window.__lightos.fixtures['21'].spot.visible === true")

        # (c) Farbe hell, Dimmer zu -> weiterhin unsichtbar (Alt-Verhalten).
        self._emit_until_true(
            lambda: self._push_dmx(255, 255, 255, 0),
            "window.__lightos.fixtures['21'].spot.visible === false")


if __name__ == "__main__":
    unittest.main()
