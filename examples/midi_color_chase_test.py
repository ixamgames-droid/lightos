"""APC Mini LED self-test (mk1/mk2) with full-surface animation."""
from __future__ import annotations

import argparse
import math
import os
import sys
import time
from dataclasses import dataclass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from src.core.midi.midi_manager import get_midi_manager


def pick_output(ports: list[str], hint: str) -> str | None:
    if not ports:
        return None
    for p in ports:
        if hint.lower() in p.lower():
            return p
    return ports[0]


def _uniq(seq):
    seen = set()
    out = []
    for x in seq:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


@dataclass(frozen=True)
class APCLayout:
    name: str
    grid: list[int]
    track_buttons: list[int]
    scene_buttons: list[int]
    extra_buttons: list[int]
    pad_channels: tuple[int, ...]
    button_channel: int

    def all_notes(self) -> list[int]:
        return _uniq(self.grid + self.track_buttons + self.scene_buttons + self.extra_buttons)


def mk1_layout() -> APCLayout:
    # LightOS/APC mini (original) mapping:
    # grid 0..63, track 64..71, scene 82..89, master/shift note 98.
    return APCLayout(
        name="mk1",
        grid=list(range(64)),
        track_buttons=list(range(64, 72)),
        scene_buttons=list(range(82, 90)),
        extra_buttons=[98],
        pad_channels=(1,),
        button_channel=1,
    )


def mk2_layout() -> APCLayout:
    # APC mini mk2 communication protocol:
    # grid 0..63, track 100..107 (0x64..0x6B), scene 112..119 (0x70..0x77),
    # shift is 122 (0x7A) and has no LED.
    # Pads use channel 7 for 100% brightness; periphery buttons use channel 1.
    return APCLayout(
        name="mk2",
        grid=list(range(64)),
        track_buttons=list(range(100, 108)),
        scene_buttons=list(range(112, 120)),
        extra_buttons=[],
        pad_channels=(7,),
        button_channel=1,
    )


def combined_layout() -> APCLayout:
    a = mk1_layout()
    b = mk2_layout()
    return APCLayout(
        name="both",
        grid=a.grid,
        track_buttons=_uniq(a.track_buttons + b.track_buttons),
        scene_buttons=_uniq(a.scene_buttons + b.scene_buttons),
        extra_buttons=_uniq(a.extra_buttons + b.extra_buttons),
        pad_channels=(1, 7),  # mk1 + mk2 full-brightness channel
        button_channel=1,
    )


def resolve_layout(layout: str, selected_port: str) -> APCLayout:
    mode = (layout or "auto").strip().lower()
    if mode == "mk1":
        return mk1_layout()
    if mode == "mk2":
        return mk2_layout()
    if mode == "both":
        return combined_layout()

    # auto
    p = (selected_port or "").lower()
    if "mk2" in p or "mkii" in p:
        return mk2_layout()
    return mk1_layout()


def _send_note(midi, channel: int, note: int, velocity: int):
    midi.send_note(channel, note, velocity)


def _set_pad(midi, cfg: APCLayout, note: int, velocity: int):
    for ch in cfg.pad_channels:
        _send_note(midi, ch, note, velocity)


def _set_button(midi, cfg: APCLayout, note: int, on: bool):
    # mk2 periphery: velocity 0=off, 1/3..127=on, 2=blink
    vel = 1 if on else 0
    _send_note(midi, cfg.button_channel, note, vel)


def _clear_all(midi, cfg: APCLayout):
    for n in cfg.grid:
        _set_pad(midi, cfg, n, 0)
    for n in cfg.track_buttons + cfg.scene_buttons + cfg.extra_buttons:
        _set_button(midi, cfg, n, False)


def _grid_serpentine_notes() -> list[int]:
    notes: list[int] = []
    for row in range(8):
        base = row * 8
        row_notes = list(range(base, base + 8))
        if row % 2 == 1:
            row_notes.reverse()
        notes.extend(row_notes)
    return notes


def _grid_note(x: int, y: int) -> int:
    return y * 8 + x


def _grid_rows() -> list[list[int]]:
    return [[_grid_note(x, y) for x in range(8)] for y in range(8)]


def _grid_diagonals() -> list[list[int]]:
    diags: list[list[int]] = []
    for d in range(15):  # x+y -> 0..14
        diag = []
        for y in range(8):
            x = d - y
            if 0 <= x < 8:
                diag.append(_grid_note(x, y))
        diags.append(diag)
    return diags


def _grid_rings() -> list[list[int]]:
    rings: list[list[int]] = []
    for level in range(4):
        lo = level
        hi = 7 - level
        ring: list[int] = []

        for x in range(lo, hi + 1):
            ring.append(_grid_note(x, lo))
        for y in range(lo + 1, hi + 1):
            ring.append(_grid_note(hi, y))
        for x in range(hi - 1, lo - 1, -1):
            ring.append(_grid_note(x, hi))
        for y in range(hi - 1, lo, -1):
            ring.append(_grid_note(lo, y))

        rings.append(ring)
    return rings


def _periphery_order(cfg: APCLayout) -> list[int]:
    # A simple border-like order: right side top->down, then bottom left->right, then extras.
    return _uniq(cfg.scene_buttons + cfg.track_buttons + cfg.extra_buttons)


def _resolve_palette(cfg: APCLayout, color_mode: str) -> list[int]:
    safe = [1, 2, 3, 4, 5, 6]  # mk1 known palette (+ blink variants)
    mode = (color_mode or "auto").strip().lower()

    if mode == "safe":
        return safe

    if mode == "full":
        if cfg.name == "mk1":
            print("Full palette requested, but mk1 only supports limited colors. Using safe palette.")
            return safe
        return list(range(1, 128))

    # auto
    if cfg.name == "mk2":
        return list(range(1, 128))
    return safe


def _sample_palette(palette: list[int], count: int) -> list[int]:
    if not palette:
        return [1] * max(1, count)
    if count <= 1:
        return [palette[0]]
    if len(palette) <= count:
        out = palette[:]
        while len(out) < count:
            out.append(out[-1])
        return out
    step = (len(palette) - 1) / float(count - 1)
    return [palette[int(round(i * step))] for i in range(count)]


def _set_many_pads(midi, cfg: APCLayout, notes: list[int], velocity: int):
    for note in notes:
        _set_pad(midi, cfg, note, velocity)


def _pattern_snake(midi, cfg: APCLayout, palette: list[int], step: float):
    order = [n for n in _grid_serpentine_notes() if n in cfg.grid]
    trail: list[int] = []
    for idx, note in enumerate(order):
        _set_pad(midi, cfg, note, palette[idx % len(palette)])
        trail.append(note)
        if len(trail) > 6:
            old = trail.pop(0)
            _set_pad(midi, cfg, old, 0)
        time.sleep(step)
    for note in trail:
        _set_pad(midi, cfg, note, 0)


def _pattern_row_wipes(midi, cfg: APCLayout, palette: list[int], step: float):
    rows = _grid_rows()
    row_colors = _sample_palette(palette, len(rows))
    for row, color in zip(rows, row_colors):
        _set_many_pads(midi, cfg, row, color)
        time.sleep(step * 2.0)
    for row in reversed(rows):
        _set_many_pads(midi, cfg, row, 0)
        time.sleep(step * 1.5)


def _pattern_diagonal_bounce(midi, cfg: APCLayout, palette: list[int], step: float):
    diags = _grid_diagonals()
    path = diags + diags[-2:0:-1]
    prev: list[int] = []
    for idx, diag in enumerate(path):
        notes = [n for n in diag if n in cfg.grid]
        _set_many_pads(midi, cfg, prev, 0)
        _set_many_pads(midi, cfg, notes, palette[(idx * 3) % len(palette)])
        prev = notes
        time.sleep(step * 1.8)
    _set_many_pads(midi, cfg, prev, 0)


def _pattern_rings(midi, cfg: APCLayout, palette: list[int], step: float):
    rings = _grid_rings()
    colors = _sample_palette(palette, len(rings))
    for idx, ring in enumerate(rings):
        _set_many_pads(midi, cfg, [n for n in ring if n in cfg.grid], colors[idx % len(colors)])
        time.sleep(step * 2.2)
    for ring in reversed(rings):
        _set_many_pads(midi, cfg, [n for n in ring if n in cfg.grid], 0)
        time.sleep(step * 1.8)


def _pattern_checkerboard(midi, cfg: APCLayout, palette: list[int], step: float):
    c1 = palette[0]
    c2 = palette[min(1, len(palette) - 1)]
    a: list[int] = []
    b: list[int] = []
    for y in range(8):
        for x in range(8):
            note = _grid_note(x, y)
            if note not in cfg.grid:
                continue
            if (x + y) % 2 == 0:
                a.append(note)
            else:
                b.append(note)

    for _ in range(4):
        _set_many_pads(midi, cfg, a, c1)
        _set_many_pads(midi, cfg, b, c2)
        time.sleep(step * 3.0)
        _set_many_pads(midi, cfg, a, c2)
        _set_many_pads(midi, cfg, b, c1)
        time.sleep(step * 3.0)
    _set_many_pads(midi, cfg, a + b, 0)


def _pattern_button_wave(midi, cfg: APCLayout, step: float):
    order = _periphery_order(cfg)
    for note in order:
        _set_button(midi, cfg, note, True)
        time.sleep(step * 1.2)
    for note in reversed(order):
        _set_button(midi, cfg, note, False)
        time.sleep(step * 1.1)


def _pattern_full_palette_pages(midi, cfg: APCLayout, palette: list[int], step: float):
    if len(palette) <= 6:
        # mk1-safe fallback: short color block presentation
        for color in palette:
            _set_many_pads(midi, cfg, cfg.grid, color)
            time.sleep(step * 3.0)
        _set_many_pads(midi, cfg, cfg.grid, 0)
        return

    # mk2 showcase: display all available colors across the 8x8 grid in pages.
    page_size = len(cfg.grid)
    pages = int(math.ceil(len(palette) / float(page_size)))
    for page in range(pages):
        start = page * page_size
        chunk = palette[start:start + page_size]
        if len(chunk) < page_size:
            chunk = chunk + [chunk[-1]] * (page_size - len(chunk))

        for idx, note in enumerate(cfg.grid):
            _set_pad(midi, cfg, note, chunk[idx])

        # page indicator on right buttons if available
        for i, btn in enumerate(cfg.scene_buttons):
            _set_button(midi, cfg, btn, i == (page % max(1, len(cfg.scene_buttons))))

        print(f"  Color page {page + 1}/{pages} ({start + 1}-{min(len(palette), start + page_size)})")
        time.sleep(step * 8.0)

    for btn in cfg.scene_buttons:
        _set_button(midi, cfg, btn, False)
    _set_many_pads(midi, cfg, cfg.grid, 0)


def _pattern_center_breath(midi, cfg: APCLayout, palette: list[int], step: float):
    # Soft in/out from center based on chessboard distance.
    layers: list[list[int]] = [[] for _ in range(4)]
    for y in range(8):
        for x in range(8):
            note = _grid_note(x, y)
            if note not in cfg.grid:
                continue
            dist = max(abs(x - 3.5), abs(y - 3.5))
            layer = int(round(dist - 0.5))  # 0..3
            layer = max(0, min(3, layer))
            layers[layer].append(note)

    colors = _sample_palette(palette, 4)
    for idx in range(4):
        _set_many_pads(midi, cfg, layers[idx], colors[idx])
        time.sleep(step * 2.0)
    for idx in range(3, -1, -1):
        _set_many_pads(midi, cfg, layers[idx], 0)
        time.sleep(step * 1.8)


def run_selftest(port_hint: str, loops: int, step_ms: int, layout: str, color_mode: str):
    midi = get_midi_manager()
    outputs = midi.list_outputs()
    print(f"Available MIDI outputs: {outputs}")
    port = pick_output(outputs, port_hint)
    if not port:
        raise RuntimeError("No MIDI output port found.")

    midi.open_output(port)
    cfg = resolve_layout(layout, port)

    print(f"Using output: {port}")
    print(f"Detected layout mode: {cfg.name}")
    print(
        f"Grid={len(cfg.grid)} | Track={len(cfg.track_buttons)} | "
        f"Scene={len(cfg.scene_buttons)} | Extra={len(cfg.extra_buttons)}"
    )

    step = max(1, int(step_ms)) / 1000.0
    loops = max(1, int(loops))
    palette = _resolve_palette(cfg, color_mode)
    print(f"Palette mode: {color_mode} ({len(palette)} colors)")

    _clear_all(midi, cfg)

    try:
        for loop_idx in range(loops):
            print(f"Loop {loop_idx + 1}/{loops}")
            _pattern_snake(midi, cfg, palette, step)
            _pattern_diagonal_bounce(midi, cfg, palette, step)
            _pattern_rings(midi, cfg, palette, step)
            _pattern_center_breath(midi, cfg, palette, step)
            _pattern_checkerboard(midi, cfg, _sample_palette(palette, 2), step)
            _pattern_row_wipes(midi, cfg, _sample_palette(palette, 8), step)
            _pattern_button_wave(midi, cfg, step)
            _pattern_full_palette_pages(midi, cfg, palette, step)
            _clear_all(midi, cfg)
            time.sleep(step * 2.0)

        print("Self-test finished.")
    finally:
        _clear_all(midi, cfg)
        print("LEDs cleared.")


def main():
    ap = argparse.ArgumentParser(description="Run an APC Mini full LED self-test.")
    ap.add_argument("--port-hint", default="APC", help="Substring to match output port name.")
    ap.add_argument("--loops", type=int, default=2, help="How many full test cycles to run.")
    ap.add_argument("--step-ms", type=int, default=35, help="Delay between steps in milliseconds.")
    ap.add_argument(
        "--layout",
        default="auto",
        choices=("auto", "mk1", "mk2", "both"),
        help="Controller mapping profile (auto detection from port name by default).",
    )
    ap.add_argument(
        "--color-mode",
        default="auto",
        choices=("auto", "safe", "full"),
        help="Pad palette mode: auto=mk2 full palette, mk1 safe palette.",
    )
    args = ap.parse_args()
    run_selftest(args.port_hint, args.loops, args.step_ms, args.layout, args.color_mode)


if __name__ == "__main__":
    main()
