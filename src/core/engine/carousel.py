"""Carousel: BPM-/Beat-synchronisierte Pattern.

Ein Carousel laeuft synchron zu Beats und erzeugt ein Bewegungs-/Lichtmuster
ueber eine Liste von Fixtures.
"""
from __future__ import annotations
from enum import Enum
import math
from .function import Function, FunctionType


class CarouselPattern(Enum):
    CIRCLE = "Circle"      # Pan/Tilt fahren Kreis
    SWEEP  = "Sweep"       # Sweep links/rechts
    PULSE  = "Pulse"       # Intensity puls auf Beat
    WAVE   = "Wave"        # Wellenmuster ueber Fixtures
    CHASE  = "Chase"       # Lauflicht auf Beat


class Carousel(Function):
    function_type = FunctionType.EFX  # nutzt EFX-Typ-Tag

    def __init__(self, name: str = "Neues Carousel", fid: int | None = None):
        super().__init__(name, fid)
        self.pattern: CarouselPattern = CarouselPattern.PULSE
        self.fixture_ids: list[int] = []
        self.sync_to_beat: bool = True
        self.beats_per_cycle: int = 4
        self.intensity_max: int = 255
        self.color_r: int = 255
        self.color_g: int = 255
        self.color_b: int = 255
        self._beat_count: int = 0
        # Marker fuer FunctionManager.from_dict-Routing
        self.is_carousel = True

    def _on_start(self):
        self._beat_count = 0
        try:
            from .bpm_manager import get_bpm_manager
            bm = get_bpm_manager()
            bm.subscribe_beat(self._on_beat)
        except Exception as exc:
            print(f"[Carousel] subscribe_beat error: {exc}")

    def _on_stop(self):
        try:
            from .bpm_manager import get_bpm_manager
            bm = get_bpm_manager()
            if hasattr(bm, "unsubscribe_beat"):
                bm.unsubscribe_beat(self._on_beat)
        except Exception as exc:
            print(f"[Carousel] unsubscribe_beat error: {exc}")

    def _on_beat(self, beat_index: int = 0):
        # BPMManager ruft cb(beat_index). Wir zaehlen lokal hoch.
        self._beat_count += 1

    def write(self, universes, patch_cache, dt, function_registry=None):
        if not self._running or not self.fixture_ids:
            return
        self._elapsed += dt

        # Phase berechnen
        bpc = max(1, int(self.beats_per_cycle))
        if self.sync_to_beat:
            phase = (self._beat_count % bpc) / bpc
            # Smooth zwischen Beats interpolieren via dt
            try:
                from .bpm_manager import get_bpm_manager
                bm = get_bpm_manager()
                if bm.bpm > 0:
                    beat_dur = 60.0 / bm.bpm
                    sub_phase = (self._elapsed % beat_dur) / beat_dur
                    phase = ((self._beat_count % bpc) + sub_phase) / bpc
            except Exception:
                pass
        else:
            phase = (self._elapsed % 2.0) / 2.0

        try:
            patch = {f.fid: f for f in patch_cache}
        except Exception as exc:
            print(f"[Carousel] patch_cache error: {exc}")
            return

        n = len(self.fixture_ids)

        for idx, fid in enumerate(self.fixture_ids):
            fixture = patch.get(fid)
            if fixture is None:
                continue
            universe = universes.get(fixture.universe)
            if universe is None:
                continue

            local_phase = (phase + idx / max(1, n)) % 1.0

            try:
                # Pattern berechnen
                if self.pattern == CarouselPattern.PULSE:
                    intensity = int(self.intensity_max * abs(math.sin(local_phase * math.pi)))
                    self._set_attr(universe, fixture, "intensity", intensity)
                elif self.pattern == CarouselPattern.CHASE:
                    # Nur ein Fixture leuchtet zur Zeit
                    active = int(phase * n) % max(1, n)
                    intensity = self.intensity_max if idx == active else 0
                    self._set_attr(universe, fixture, "intensity", intensity)
                elif self.pattern == CarouselPattern.WAVE:
                    wave = math.sin(local_phase * 2 * math.pi)
                    intensity = int(self.intensity_max * (0.5 + 0.5 * wave))
                    self._set_attr(universe, fixture, "intensity", intensity)
                elif self.pattern == CarouselPattern.CIRCLE:
                    pan = int(127 + 127 * math.cos(local_phase * 2 * math.pi))
                    tilt = int(127 + 127 * math.sin(local_phase * 2 * math.pi))
                    self._set_attr(universe, fixture, "pan", pan)
                    self._set_attr(universe, fixture, "tilt", tilt)
                    self._set_attr(universe, fixture, "intensity", self.intensity_max)
                elif self.pattern == CarouselPattern.SWEEP:
                    pan = int(127 + 127 * math.sin(local_phase * 2 * math.pi))
                    self._set_attr(universe, fixture, "pan", pan)
                    self._set_attr(universe, fixture, "intensity", self.intensity_max)

                # Farbe
                for attr, col in [("color_r", self.color_r),
                                  ("color_g", self.color_g),
                                  ("color_b", self.color_b)]:
                    self._set_attr(universe, fixture, attr, col)
            except Exception as exc:
                print(f"[Carousel] write error: {exc}")

    def _set_attr(self, universe, fixture, attr, val):
        try:
            from src.core.app_state import get_channels_for_patched
            channels = get_channels_for_patched(fixture)
        except Exception as exc:
            print(f"[Carousel] channel lookup error: {exc}")
            return
        for ch in channels:
            if ch.attribute == attr:
                try:
                    addr = fixture.address + ch.channel_number - 1
                    if 1 <= addr <= 512:
                        universe.set_channel(addr, max(0, min(255, int(val))))
                except Exception as exc:
                    print(f"[Carousel] set_channel error: {exc}")
                break

    def to_dict(self):
        d = super().to_dict()
        d.update({
            "pattern": self.pattern.value,
            "fixture_ids": list(self.fixture_ids),
            "sync_to_beat": self.sync_to_beat,
            "beats_per_cycle": self.beats_per_cycle,
            "intensity_max": self.intensity_max,
            "color_r": self.color_r,
            "color_g": self.color_g,
            "color_b": self.color_b,
        })
        return d

    @classmethod
    def from_dict(cls, d):
        c = cls(d.get("name", "Carousel"), fid=d.get("id"))
        try:
            c.pattern = CarouselPattern(d.get("pattern", "Pulse"))
        except ValueError:
            c.pattern = CarouselPattern.PULSE
        c.fixture_ids = list(d.get("fixture_ids", []))
        c.sync_to_beat = bool(d.get("sync_to_beat", True))
        try:
            c.beats_per_cycle = int(d.get("beats_per_cycle", 4))
        except (TypeError, ValueError):
            c.beats_per_cycle = 4
        try:
            c.intensity_max = int(d.get("intensity_max", 255))
        except (TypeError, ValueError):
            c.intensity_max = 255
        try:
            c.color_r = int(d.get("color_r", 255))
            c.color_g = int(d.get("color_g", 255))
            c.color_b = int(d.get("color_b", 255))
        except (TypeError, ValueError):
            c.color_r = c.color_g = c.color_b = 255
        return c
