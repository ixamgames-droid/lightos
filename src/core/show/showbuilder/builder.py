"""ShowBuilder — typisierte Fassade über die de-facto Build-API, die illegale
Zustände unrepräsentierbar macht: jeder Algorithmus/Action/Param/Style/Fixture
wird AT CALL TIME gegen die reflektierten echten Sätze (capability.reflect)
geprüft und wirft bei Halluzination SOFORT ``BuildError`` — statt sie still in
eine inerte Show zu serialisieren, die der Loader dann verschluckt.

Statt rohe Ints durch den Code zu fädeln, geben die Funktions-Builder
(``matrix``/``efx``/``scene``/…) ein ``Handle`` zurück, das man direkt an die
Widget-Builder (``button``/``slider``/…) als ``function=`` übergibt — so kann ein
Widget gar nicht erst an eine nicht-existente Funktion binden.

``save()`` schreibt die Show UND validiert sie doppelt (statischer Lint +
bindungs-bewusster Live-Lint) → was der Builder ausgibt, ist garantiert „nur
echte Bausteine".

Beispiel:
    b = ShowBuilder()
    fids = b.patch("ZQ01424", count=8, channel_count=8, mode_name="8-Kanal RGBW")
    mx = b.matrix("PAR Farbe", algorithm=RgbAlgorithm.CHASE, style="RGB",
                  fixtures=fids, colors=[(255,0,0),(0,0,255)])
    b.button("Farbe an/aus", action=ButtonAction.FUNCTION_TOGGLE, function=mx, bank=0)
    b.slider("Tempo", mode="EffectSpeed", param_key="speed", function=mx, bank=0)
    b.save("shows/Mini.lshow")
"""
from __future__ import annotations

import os
from enum import Enum

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from src.core.capability.reflect import get_capabilities
from .errors import BuildError, did_you_mean


def _value_of(x):
    return x.value if isinstance(x, Enum) else x


class Handle:
    """Leichter Verweis auf eine erzeugte Funktion (statt rohe Int-IDs)."""

    def __init__(self, fn):
        self.fn = fn
        self.id = fn.id
        self.name = getattr(fn, "name", "")

    def __int__(self):
        return int(self.id)


class ShowBuilder:
    def __init__(self, reset: bool = True):
        # VC-Widgets sind QWidgets -> headless QApplication wie in den Build-Skripten.
        try:
            from PySide6.QtWidgets import QApplication
            self._app = QApplication.instance() or QApplication([])
        except Exception:
            self._app = None
        from src.core.app_state import get_state
        from src.core.engine.function_manager import get_function_manager
        if reset:
            from src.core.show.show_file import reset_show
            reset_show()
        self.state = get_state()
        self.fm = get_function_manager()
        self.caps = get_capabilities()
        self._widgets: list = []

    # ── interne Prüf-Helfer ─────────────────────────────────────────────────────
    def _check(self, value, valid, label):
        v = _value_of(value)
        if valid and v not in valid:
            raise BuildError(f"{label} '{v}' existiert nicht{did_you_mean(v, valid)}")
        return v

    @staticmethod
    def _bind_id(function):
        if function is None:
            return None
        return int(function.id) if hasattr(function, "id") else int(function)

    def _live_params(self, fid):
        from src.core.engine import effect_live
        keys = {getattr(s, "key", None) for s in effect_live.list_params(fid)}
        keys.discard(None)
        return keys

    def _live_actions(self, fid):
        from src.core.engine import effect_live
        return {k for k, _ in effect_live.list_actions(fid)}

    # ── Fixtures / Patch ────────────────────────────────────────────────────────
    def profile_id(self, short_name: str) -> int:
        """Fixture-Profil-ID per short_name — wirft BuildError, wenn es das Profil
        nicht gibt (statt eine inerte Fixture zu patchen)."""
        try:
            from sqlalchemy import select
            from sqlalchemy.orm import Session
            from src.core.database.fixture_db import engine as fdb_engine
            from src.core.database.models import FixtureProfile
            with Session(fdb_engine()) as s:
                pid = s.execute(select(FixtureProfile.id).where(
                    FixtureProfile.short_name == short_name)).scalar_one_or_none()
        except Exception as exc:
            raise BuildError(f"Fixture-DB nicht lesbar: {exc}")
        if pid is None:
            raise BuildError(
                f"Fixture-Profil '{short_name}' existiert nicht in der Bibliothek "
                "(short_name) — App einmal starten (ensure_builtins) oder Profil importieren.")
        return int(pid)

    def patch(self, short_name: str, *, count: int = 1, channel_count: int,
              mode_name: str = "", universe: int = 1, start_address: int | None = None,
              label: str = "") -> list[int]:
        """Patcht ``count`` Fixtures eines Profils fortlaufend. Liefert die fids.
        Validiert das Profil (BuildError, wenn nicht vorhanden)."""
        from src.core.database.models import PatchedFixture
        pid = self.profile_id(short_name)
        addr = int(start_address if start_address is not None else
                   self.state.suggest_address(universe, channel_count))
        fids: list[int] = []
        existing = [pf.fid for pf in self.state.get_patched_fixtures()]
        next_fid = (max(existing) + 1) if existing else 1
        for i in range(count):
            fid = next_fid + i
            self.state.add_fixture(PatchedFixture(
                fid=fid, label=(label or short_name) + (f" {i + 1}" if count > 1 else ""),
                fixture_profile_id=pid, mode_name=mode_name, universe=universe,
                address=addr, channel_count=channel_count), undoable=False)
            fids.append(fid)
            addr += channel_count
        return fids

    # ── Funktionen ──────────────────────────────────────────────────────────────
    def matrix(self, name, algorithm, *, style="RGB", fixtures=None, colors=None,
               params=None, **attrs) -> Handle:
        from src.core.engine.rgb_matrix import RgbAlgorithm, MatrixStyle, ColorSequence
        algo = self._check(algorithm, self.caps.matrix_algorithms, "Matrix-Algorithmus")
        sty = self._check(style, self.caps.matrix_styles, "Matrix-Style")
        if params:
            for k in params:
                if k not in self.caps.matrix_all_param_keys:
                    raise BuildError(f"Matrix-Param '{k}' existiert nicht"
                                     f"{did_you_mean(k, self.caps.matrix_all_param_keys)}")
        m = self.fm.new_rgb_matrix(name)
        m.algorithm = RgbAlgorithm(algo)
        m.style = MatrixStyle(sty)
        if fixtures:
            # fixture_grid ist FLACH (Liste von fids), cols=N rows=1 — wie die
            # Build-Skripte (build_demo_show_full.py:196).
            flat: list[int] = []
            for f in fixtures:
                if isinstance(f, (list, tuple)):
                    flat.extend(int(x) for x in f)
                else:
                    flat.append(int(f))
            m.fixture_grid = flat
            m.cols, m.rows = len(flat), 1
        if colors:
            m.colors = ColorSequence([tuple(c) for c in colors])
        if params:
            try:
                m.params.update(dict(params))
            except Exception:
                m.params = dict(params)
        for k, v in attrs.items():
            setattr(m, k, v)
        return Handle(m)

    def efx(self, name, algorithm, *, fixtures=None, **attrs) -> Handle:
        from src.core.engine.efx import EfxAlgorithm, EfxFixture
        algo = self._check(algorithm, self.caps.efx_algorithms, "EFX-Algorithmus")
        e = self.fm.new_efx(name)
        e.algorithm = EfxAlgorithm(algo)
        if fixtures:
            e.fixtures = [f if isinstance(f, EfxFixture) else EfxFixture(fid=int(f))
                          for f in fixtures]
        for k, v in attrs.items():
            setattr(e, k, v)
        return Handle(e)

    def scene(self, name="Szene") -> Handle:
        return Handle(self.fm.new_scene(name))

    def chaser(self, name="Chaser") -> Handle:
        return Handle(self.fm.new_chaser(name))

    # ── Widgets (bauen ECHTE VC-Objekte -> vollständige, gültige Serialisierung) ─
    def _add(self, w, bank):
        w.caption = w.caption  # noqa (caption schon im Konstruktor gesetzt)
        try:
            w.bank = int(bank)
        except (TypeError, ValueError):
            w.bank = -1
        self._widgets.append(w)
        return w

    def button(self, caption, action, *, function=None, effect_action_key=None,
               bank=-1, **attrs):
        from src.ui.virtualconsole.vc_button import VCButton, ButtonAction
        av = self._check(action, self.caps.button_actions, "ButtonAction")
        fid = self._bind_id(function)
        if effect_action_key and fid:
            acts = self._live_actions(fid)
            if acts and effect_action_key not in acts:
                raise BuildError(
                    f"effect_action_key '{effect_action_key}' ist an Funktion {fid} "
                    f"keine gültige Aktion{did_you_mean(effect_action_key, acts)}")
        w = VCButton(caption)
        w.action = ButtonAction(av)
        if fid:
            w.function_id = fid
        if effect_action_key:
            w.effect_action_key = effect_action_key
        for k, v in attrs.items():
            setattr(w, k, v)
        return self._add(w, bank)

    def slider(self, caption, mode, *, param_key=None, function=None, bank=-1, **attrs):
        from src.ui.virtualconsole.vc_slider import VCSlider
        mv = self._check(mode, self.caps.slider_modes, "SliderMode")  # plain-str
        fid = self._bind_id(function)
        if param_key and fid:
            keys = self._live_params(fid)
            if keys and param_key not in keys:
                raise BuildError(
                    f"param_key '{param_key}' existiert nicht an Funktion {fid}"
                    f"{did_you_mean(param_key, keys)}")
        w = VCSlider(caption)
        w.mode = mv
        if fid:
            w.function_id = fid
        if param_key:
            w.param_key = param_key
        for k, v in attrs.items():
            setattr(w, k, v)
        return self._add(w, bank)

    def color(self, caption, target, *, function=None, bank=-1, **attrs):
        from src.ui.virtualconsole.vc_color import VCColor
        tv = self._check(target, self.caps.color_targets, "ColorTarget")  # plain-str (dt.)
        w = VCColor(caption)
        w.target = tv
        fid = self._bind_id(function)
        if fid:
            w.function_id = fid
        for k, v in attrs.items():
            setattr(w, k, v)
        return self._add(w, bank)

    def speed_dial(self, caption, target_mode, *, function=None, tempo_bus_id="",
                   bank=-1, **attrs):
        from src.ui.virtualconsole.vc_speedial import VCSpeedDial
        tv = self._check(target_mode, self.caps.speed_targets, "SpeedTarget")  # plain-str
        w = VCSpeedDial(caption)
        w.target_mode = tv
        if tempo_bus_id:
            w.tempo_bus_id = tempo_bus_id
        fid = self._bind_id(function)
        if fid:
            w.function_id = fid
        for k, v in attrs.items():
            setattr(w, k, v)
        return self._add(w, bank)

    def label(self, caption, *, bank=-1, **attrs):
        from src.ui.virtualconsole.vc_label import VCLabel
        w = VCLabel(caption)
        for k, v in attrs.items():
            setattr(w, k, v)
        return self._add(w, bank)

    # ── Speichern + Verifizieren ────────────────────────────────────────────────
    def vc_layout(self) -> dict:
        return {"widgets": [w.to_dict() for w in self._widgets]}

    def save(self, path, *, verify: bool = True, name: str | None = None):
        """Setzt das VC-Layout, speichert die Show und validiert sie doppelt
        (statisch + live). Wirft bei einem ECHTEN Fehler ``ShowValidationError``."""
        from src.core.show.show_file import save_show
        if name is not None:
            self.state.show_name = name
        self.state._vc_layout = self.vc_layout()
        save_show(path)
        if verify:
            from src.core.capability.validate import (
                assert_lshow, validate_show_live, ERROR, ShowValidationError)
            assert_lshow(path)
            live = validate_show_live(self.state)
            if any(f.severity == ERROR for f in live):
                raise ShowValidationError(live)
        return path

    def verify_render(self, functions, *, channels=None, **kw):
        """Render-Smoke über die genannten Funktionen/Handles."""
        from src.core.capability.render_probe import render_diff
        fids = [int(f) for f in functions]
        return render_diff(self.state, fids, channels=channels, **kw)
