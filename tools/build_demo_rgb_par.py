"""Demo-Show "Demo RGB PAR" — 4x RGB-PAR mit einer 4-Cue-Cueliste.

Erzeugt: shows/demo_rgb_par.lshow
Aufruf:  venv/Scripts/python.exe tools/build_demo_rgb_par.py

WARUM ES DIESEN GENERATOR GIBT (2026-07-26)
-------------------------------------------
Die committete ``shows/demo_rgb_par.lshow`` war **keine LightOS-Show**, sondern ein
hand geschriebener Entwurf eines Formats, das nie implementiert wurde: eigene
``show.json`` mit ``format_version``/``universes`` plus separate ZIP-Eintraege
``patch.json``, ``fixtures/…``, ``groups.json``, ``palettes.json``,
``sequences/seq_001.json``, ``executors.json``, ``settings.json``,
``effects.json``, ``timeline.json`` (Commit 4a90339, 2026-05-27). ``load_show``
kennt nur ``show.json`` im heutigen Schema und fand darin keinen einzigen Block →
die Datei "lud" zwei Monate lang als **leere Show**, mit ok=True und der Meldung
"Show 'Demo RGB PAR Show' geladen". Ein blindes load→save haette sie zu einer
639-Byte-Leershow plattgemacht.

Dieser Generator baut denselben INHALT als echte Show im aktuellen Format nach:

  * 4x ``PAR3`` ("LED PAR RGB 3ch", Mode "3-Kanal RGB" = R/G/B) auf Universe 1,
    Adressen 1 / 4 / 7 / 10, Labels "PAR 1".."PAR 4"  (wie ``patch.json``; das
    mitgelieferte Eigenprofil ``fixtures/fixture_rgb_par.json`` ist kanal- und
    attributgleich mit dem eingebauten ``PAR3``).
  * Gruppe "Alle PAR" als 4x1-Grid ueber die vier fids (wie ``groups.json``;
    dessen Feld ``color`` hat im heutigen ``FixtureGroup`` keine Entsprechung und
    entfaellt bewusst).
  * Cueliste "Demo-Show" mit den vier Original-Cues inkl. Fade-Zeiten
    (``loop: false`` → Modus ``single``) und den exakten RGB-Werten aus
    ``sequences/seq_001.json``.
  * Executor auf Slot 1, Label "Demo-Show" (fader=volume, Tasten go/back/flash
    sind bereits die Executor-Defaults — identisch zu ``executors.json``).
  * Farb-Palette "Warm White" (255/180/80). Die drei weiteren Paletten des
    Entwurfs (Rot/Gruen/Blau) sind in den Standard-Paletten schon vorhanden und
    werden NICHT als Namens-Dubletten angelegt; ihre genauen Werte leben in den
    Cues.

``settings.json`` (Default-Fades, Art-Net-Ziel, UI-Theme/Sprache) und die leeren
``effects.json``/``timeline.json`` sind app-weite Einstellungen bzw. leer → nichts
zu uebertragen.
"""
from __future__ import annotations

import json
import os
import sys
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from _builder import ShowBuilder, build_and_verify            # noqa: E402
from src.core.app_state import get_channels_for_patched        # noqa: E402
from src.core.engine.cue import Cue                            # noqa: E402
from src.core.engine.palette import Palette, PaletteType, get_palette_manager  # noqa: E402
from src.core.show.show_file import SHOW_VERSION, load_show    # noqa: E402

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(_ROOT, "shows", "demo_rgb_par.lshow")

# Die vier Cues aus sequences/seq_001.json des Entwurfs — 1:1 uebernommen.
CUES = [
    (1.0, "Blackout",   0.0, 0.0, (0, 0, 0)),
    (2.0, "Warm White", 3.0, 2.0, (255, 180, 80)),
    (3.0, "Rot",        2.0, 1.5, (255, 20, 0)),
    (4.0, "Blau",       2.0, 1.5, (0, 60, 255)),
]

# ── 1) Patch: 4x RGB-PAR ab Adresse 1 ───────────────────────────────────────────
b = ShowBuilder()
fids = b.patch("PAR3", count=4, channel_count=3, mode_name="3-Kanal RGB",
               universe=1, start_address=1, label="PAR")
state = b.state

# ── 2) Gruppe "Alle PAR" (4x1-Grid) ─────────────────────────────────────────────
from sqlalchemy import delete                                  # noqa: E402
from src.core.database.models import FixtureGroup              # noqa: E402

with state._session() as s:
    s.execute(delete(FixtureGroup))
    s.add(FixtureGroup(
        name="Alle PAR", cols=4, rows=1,
        positions_json=json.dumps({f"{i},0": fid for i, fid in enumerate(fids)})))
    s.commit()
try:
    state.notify_groups_changed()
except Exception:
    pass

# ── 3) Palette "Warm White" ─────────────────────────────────────────────────────
get_palette_manager().add(Palette(
    name="Warm White", type=PaletteType.COLOR,
    values={"color_r": 255, "color_g": 180, "color_b": 80}))

# ── 4) Cueliste + Executor ──────────────────────────────────────────────────────
stack = state.new_cue_stack("Demo-Show")
stack.mode = "single"                       # seq_001.json: "loop": false
for number, label, fade_in, fade_out, (r, g, b_) in CUES:
    stack.add_cue(Cue(
        number=number, label=label, fade_in=fade_in, fade_out=fade_out,
        values={fid: {"color_r": r, "color_g": g, "color_b": b_} for fid in fids}))

ex = state.playback_engine.get_executor(1, page=0)
ex.stack = stack
ex.label = stack.name

# ── 5) Speichern + validieren ───────────────────────────────────────────────────
build_and_verify(b, OUT, name="Demo RGB PAR Show")

# ── 6) Selbst-Verifikation: laedt die Datei wirklich mit Inhalt? ────────────────
ok, msg = load_show(OUT)
assert ok, msg
state = b.state
patched = state.get_patched_fixtures()
assert len(patched) == 4, f"Fixtures nach dem Laden: {len(patched)}"
assert [pf.label for pf in sorted(patched, key=lambda p: p.fid)] == \
    ["PAR 1", "PAR 2", "PAR 3", "PAR 4"], [pf.label for pf in patched]
assert [pf.address for pf in sorted(patched, key=lambda p: p.fid)] == [1, 4, 7, 10], \
    [pf.address for pf in patched]

assert len(state.cue_stacks) == 1, f"Cuelisten: {len(state.cue_stacks)}"
loaded = state.cue_stacks[0]
assert loaded.name == "Demo-Show" and loaded.mode == "single", (loaded.name, loaded.mode)
assert len(loaded.cues) == 4, f"Cues: {len(loaded.cues)}"
assert [(c.label, c.fade_in, c.fade_out) for c in loaded.cues] == \
    [(lbl, fi, fo) for _, lbl, fi, fo, _ in CUES], [c.label for c in loaded.cues]

ex = state.playback_engine.get_executor(1, page=0)
assert ex.stack is loaded, "Executor 1 nicht an die Cueliste gebunden"
assert (ex.fader_function, ex.btn1, ex.btn2, ex.btn3) == ("volume", "go", "back", "flash")

# Die Cue-Werte muessen echte DMX-Kanaele treffen (sonst waere die Show stumm):
# jedes Cue-Attribut existiert im Profil des Geraets, und PAR 1 liegt so, dass
# sein roter Kanal die DMX-Adresse 1 belegt.
first = sorted(patched, key=lambda p: p.fid)[0]
chan_of = {c.attribute: c.channel_number for c in get_channels_for_patched(first)}
assert {"color_r", "color_g", "color_b"} <= set(chan_of), sorted(chan_of)
cue_attrs = {a for c in loaded.cues for vals in c.values.values() for a in vals}
assert cue_attrs <= set(chan_of), f"Cue-Attribute ohne Kanal: {cue_attrs - set(chan_of)}"
assert first.address + chan_of["color_r"] - 1 == 1, (first.address, chan_of)

# Die Gruppe muss in der DATEI stehen (fixture_groups-Block), nicht nur in der DB.
with zipfile.ZipFile(OUT, "r") as _zf:
    saved = json.loads(_zf.read("show.json").decode("utf-8"))
assert saved.get("version") == SHOW_VERSION, saved.get("version")
assert [g.get("name") for g in saved.get("fixture_groups") or []] == ["Alle PAR"], \
    saved.get("fixture_groups")

print(f"OK: demo_rgb_par.lshow — v{SHOW_VERSION}, 4 PAR (Adr. 1/4/7/10), "
      f"Cueliste '{loaded.name}' mit {len(loaded.cues)} Cues, Executor 1 gebunden")
