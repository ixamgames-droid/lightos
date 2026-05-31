"""Executor — bindet Cueliste an Fader-Slot."""
from __future__ import annotations
import threading
import time
from .cue_stack import CueStack, TICK


class Executor:
    FADER_FUNCTIONS = ("volume", "rate", "crossfade", "master")
    BTN_FUNCTIONS = ("go", "back", "flash", "solo", "pause", "latch")

    def __init__(self, slot: int):
        self.slot = slot
        self.label = f"Exec {slot}"
        self.stack: CueStack | None = None
        self.fader_value: float = 1.0       # 0.0 – 1.0
        self.fader_function: str = "volume"
        self.btn1: str = "go"
        self.btn2: str = "back"
        self.btn3: str = "flash"
        self._flash_active = False
        self._latch_active = False

    def press_btn(self, btn: int | str):
        """Accept either a slot index (0/1/2) or a function name string."""
        if isinstance(btn, int):
            fn = [self.btn1, self.btn2, self.btn3][btn]
        else:
            fn = btn
        if fn == "go":
            if self.stack:
                self.stack.go()
        elif fn == "back":
            if self.stack:
                self.stack.back()
        elif fn == "stop":
            if self.stack:
                self.stack.stop()
        elif fn == "flash":
            self._flash_active = True
        elif fn == "latch":
            self._latch_active = not self._latch_active

    def release_btn(self, btn: int | str):
        fn = [self.btn1, self.btn2, self.btn3][btn] if isinstance(btn, int) else btn
        if fn == "flash":
            self._flash_active = False

    def get_output(self) -> dict[int, dict[str, int]]:
        if self.stack is None:
            return {}
        raw = self.stack.get_output()
        if not raw:
            return {}
        vol = self.fader_value if self.fader_function == "volume" else 1.0
        if self._flash_active:
            vol = 1.0
        if abs(vol - 1.0) < 0.001:
            return raw
        # Skaliere Intensitäts-Attribute mit Fader
        scaled = {}
        for fid, attrs in raw.items():
            new_attrs = {}
            for attr, val in attrs.items():
                if attr in ("intensity", "color_r", "color_g", "color_b",
                            "color_w", "color_a", "color_uv"):
                    new_attrs[attr] = int(val * vol)
                else:
                    new_attrs[attr] = val
            scaled[fid] = new_attrs
        return scaled


class PlaybackEngine:
    """Verwaltet alle Executoren mit Multi-Page-Unterstuetzung, laeuft in eigenem Thread."""

    MAX_EXECUTORS = 20
    MAX_PAGES = 10

    def __init__(self, app_state):
        # pages[page_idx] -> list[Executor] (jede Page hat eigene Executoren mit eigenen Stacks)
        self.pages: list[list[Executor]] = [
            [Executor(slot + 1) for slot in range(self.MAX_EXECUTORS)]
            for _ in range(self.MAX_PAGES)
        ]
        self.current_page: int = 0
        self.page_names: list[str] = [f"Page {i+1}" for i in range(self.MAX_PAGES)]
        self._page_callbacks: list = []
        self._state = app_state
        self._thread: threading.Thread | None = None
        self._running = False
        self._on_output: list = []

    @property
    def executors(self) -> list[Executor]:
        """Backwards-compat: liefert Executoren der aktuell aktiven Page."""
        return self.pages[self.current_page]

    def set_page(self, page_idx: int):
        """Wechselt aktive Page (0-basiert)."""
        page_idx = max(0, min(self.MAX_PAGES - 1, page_idx))
        if page_idx == self.current_page:
            return
        self.current_page = page_idx
        for cb in self._page_callbacks:
            try:
                cb(page_idx)
            except Exception:
                pass

    def subscribe_page(self, cb):
        if cb not in self._page_callbacks:
            self._page_callbacks.append(cb)

    def start(self):
        # Kein eigener Thread mehr: das Rendern erfolgt zentral im einen
        # Output-Frame (AppState._render_frame), um Tearing durch zwei
        # konkurrierende Render-Loops zu vermeiden. start()/stop() bleiben fuer
        # API-Kompatibilitaet erhalten.
        self._running = True

    def stop(self):
        self._running = False

    def compute_merged(self) -> dict[int, dict[str, int]]:
        """Tickt alle Cue-Stacks (Echtzeit-Fades) und liefert den gemergten
        Output aller Executoren ALLER Pages als {fid: {attr: val}}.
        Schreibt NICHT direkt ins Universe — das macht der zentrale Renderer."""
        merged: dict[int, dict[str, int]] = {}
        for page in self.pages:
            for ex in page:
                if ex.stack:
                    ex.stack.tick()
                output = ex.get_output()
                for fid, attrs in output.items():
                    if fid not in merged:
                        merged[fid] = {}
                    merged[fid].update(attrs)
        for cb in self._on_output:
            try:
                cb(merged)
            except Exception:
                pass
        return merged

    def _loop(self):
        while self._running:
            t0 = time.monotonic()
            self._tick()
            elapsed = time.monotonic() - t0
            sleep = max(0.0, TICK - elapsed)
            time.sleep(sleep)

    def _tick(self):
        # Legacy-Pfad (nicht mehr aus einem Thread getrieben). Beibehalten, falls
        # extern/Tests aufgerufen: nutzt denselben Merge wie der zentrale Renderer.
        self._flush_to_dmx(self.compute_merged())

    def _flush_to_dmx(self, merged: dict[int, dict[str, int]]):
        from src.core.app_state import get_channels_for_patched
        for fixture in self._state.get_patched_fixtures():
            fid = fixture.fid
            if fid not in merged:
                continue
            attrs = merged[fid]
            # Programmer hat Priorität (LTP)
            prog = self._state.programmer.get(fid, {})
            final = {**attrs, **prog}
            if fixture.universe not in self._state.universes:
                continue
            universe = self._state.universes[fixture.universe]
            channels = get_channels_for_patched(fixture)
            for ch in channels:
                val = final.get(ch.attribute, ch.default_value)
                dmx_addr = fixture.address + ch.channel_number - 1
                if 1 <= dmx_addr <= 512:
                    # Klemmen + None-Default abfangen: set_channel hat ein hartes
                    # assert 0<=val<=255, das sonst den Playback-Thread killt.
                    try:
                        v = int(val) if val is not None else 0
                    except (TypeError, ValueError):
                        v = 0
                    universe.set_channel(dmx_addr, max(0, min(255, v)))

    def stop_all(self):
        # Stoppt Stacks auf ALLEN Pages
        for page in self.pages:
            for ex in page:
                if ex.stack:
                    ex.stack.stop()

    def subscribe(self, cb):
        self._on_output.append(cb)

    def get_executor(self, slot: int, page: int | None = None) -> Executor:
        """Liefert Executor von angegebener Page (default = aktuelle)."""
        p = self.current_page if page is None else max(0, min(self.MAX_PAGES - 1, page))
        return self.pages[p][slot - 1]
