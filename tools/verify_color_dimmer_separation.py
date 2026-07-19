r"""Verifikation: Trennung FARBE <-> DIMMER an Effekten (Color/Matrix/Chase).

Davids wiederkehrendes Problem: "Wenn ich einen Farbeffekt (Color/Matrix/Chase)
abspeichere, ist auf einmal ein Dimmer mit dabei." Dieses Skript baut reine
Farb-Effekte UND reine Dimmer-Effekte, laesst sie am ECHTEN Render-Pfad
(state._render_frame) laufen und liest dann pro Fixture exakt das aus, was der
LIVE-VIEWER anzeigt -- mit derselben Funktion, die der Live-Viewer benutzt
(LiveView._fixture_color_and_intensity, live_view.py:1069):
    * eine FARBE (color_r/g/b/w -> RGB, Weiss auf RGB addiert)
    * eine INTENSITAET (Dimmer-Kanal; ohne Dimmer-Kanal = 255)
Der Live-Viewer zeichnet beide GETRENNT: die Farbe immer als Hue, die Intensitaet
als Glow-Staerke + "X %"-Label (Label NUR wenn intensity > 0,
fixture_renderer live_view.py:193). "Farbe da, aber Intensitaet aus" ist also
direkt sichtbar.

Beweis-Ziele:
  A) Reiner Farb-Effekt  -> Farbkanal gesetzt, Dimmer-Kanal == 0  (Intensitaet AUS)
  B) Reiner Dimmer-Effekt-> Dimmer-Kanal gesetzt, ALLE Farbkanaele == 0
  C) Aufklaerung: implicit_brightness=True hebt bei reiner Farbe den Dimmer
     automatisch auf 255 (das "es kam ein Dimmer dazu"-Gefuehl) -- es ist NICHT
     im Effekt gespeichert, sondern eine Render-Komfortfunktion.
  D) Aufklaerung Chase: ein Chase erbt den Dimmer NUR, wenn seine Schritt-Snaps
     mit Intensitaet gespeichert wurden. Saubere Farb-Snaps -> kein Dimmer.

Aufruf:  venv\Scripts\python.exe tools\verify_color_dimmer_separation.py
Headless, kein Output-Thread, eigene Wegwerf-Show-DB (echte DB unberuehrt).
"""
from __future__ import annotations
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["LIGHTOS_SHOW_DB"] = os.path.join(os.environ.get("TEMP", "."),
                                             "lightos_cd_verify.db")
os.environ["LIGHTOS_NO_OUTPUT_THREAD"] = "1"
os.environ["LIGHTOS_NO_AUDIO_AUTOSTART"] = "1"

from PySide6.QtWidgets import QApplication
_app = QApplication.instance() or QApplication([])

from sqlalchemy import select
from sqlalchemy.orm import Session
from src.core.app_state import get_state, get_channels_for_patched
from src.core.database.fixture_db import engine as fdb_engine, ensure_builtins
from src.core.database.models import PatchedFixture, FixtureProfile
from src.core.dmx.universe import Universe
from src.core.engine.function_manager import get_function_manager
from src.core.engine.function import RunOrder, Direction
from src.core.engine.chaser import ChaserStep
from src.core.engine.rgb_matrix import RgbAlgorithm, MatrixStyle, ColorSequence
from src.core.show.show_file import reset_show

DT = 1.0 / 44.0


def profile_id(short: str) -> int:
    ensure_builtins()
    with Session(fdb_engine()) as s:
        pid = s.execute(select(FixtureProfile.id).where(
            FixtureProfile.short_name == short)).scalar_one_or_none()
    if pid is None:
        raise SystemExit(f"Profil '{short}' fehlt in fixtures.db.")
    return int(pid)


# ════════════════════════════════════════════════════════════════════════════
#  RIG: 4 RGBW-PAR (je color_r/g/b/w + eigener intensity/Dimmer-Kanal)
# ════════════════════════════════════════════════════════════════════════════
reset_show()
state = get_state()
fm = get_function_manager()
PAR_PID = profile_id("ZQ01424")        # 8-Kanal RGBW + Dimmer

PARS = [1, 2, 3, 4]
addr = 1
for fid in PARS:
    state.add_fixture(PatchedFixture(
        fid=fid, label=f"PAR {fid}", fixture_profile_id=PAR_PID,
        mode_name="8-Kanal RGBW", universe=1, address=addr, channel_count=8,
        manufacturer_name="Generic", fixture_name="Stage Light ZQ01424",
        fixture_type="par"), undoable=False)
    addr += 8

# COM-Port nicht verfuegbar -> Universe manuell anlegen, Render-Plan bauen.
state.universes = {1: Universe(1)}
state._rebuild_render_plan()

fixtures = {f.fid: f for f in state.get_patched_fixtures()}
chans = {fid: get_channels_for_patched(f) for fid, f in fixtures.items()}
chan_of = {fid: {(c.attribute or "").lower(): c.channel_number
                 for c in chans[fid]} for fid in PARS}

# Sanity: jede PAR hat color_r/g/b/w + intensity?
for fid in PARS:
    need = {"color_r", "color_g", "color_b", "color_w", "intensity"}
    missing = need - set(chan_of[fid])
    if missing:
        raise SystemExit(f"PAR {fid} fehlen Kanaele {missing}: {chan_of[fid]}")


def abs_addr(fid: int, attr: str) -> int:
    return fixtures[fid].address + chan_of[fid][attr] - 1


def raw(fid: int, attr: str) -> int:
    return int(state.universes[1].get_channel(abs_addr(fid, attr)))


# ── Live-Viewer-Berechnung (Kopie von LiveView._fixture_color_and_intensity,
#    src/ui/views/live_view.py:1069 ff.) -- so sehen wir 1:1 was der Viewer anzeigt.
#    Abweichung zum Original: das Original hat inzwischen ein seen-Set ("erster
#    Kopf gewinnt") fuer Mehrkopf-Geraete; fuer die hier benutzten Einkopf-PARs
#    ist das Ergebnis identisch. Dauerhafter Regressionsschutz liegt in
#    tests/test_strict_dimmer_render.py — dieses Skript ist Doku/Aufklaerung. ──
def live_view_shows(fid: int) -> tuple[tuple[int, int, int], int]:
    """Gibt ((r,g,b), intensity) zurueck -- genau wie der Live-Viewer."""
    fx = fixtures[fid]
    universe = state.universes[fx.universe]
    r = g = b = w = 0
    intensity = 255
    for ch in get_channels_for_patched(fx):
        a = fx.address + ch.channel_number - 1
        if 1 <= a <= 512:
            val = universe.get_channel(a)
            if ch.attribute == "color_r": r = val
            elif ch.attribute == "color_g": g = val
            elif ch.attribute == "color_b": b = val
            elif ch.attribute == "color_w": w = val
            elif ch.attribute == "intensity": intensity = val
    r = min(255, r + w); g = min(255, g + w); b = min(255, b + w)
    return (r, g, b), intensity


def render(frames: int = 3):
    for _ in range(frames):
        state._render_frame(DT)


def stop_all():
    for f in list(fm.all()):
        try:
            fm.stop(f.id)
        except Exception:
            pass
    render(2)


# ════════════════════════════════════════════════════════════════════════════
#  Effekt-Builder
# ════════════════════════════════════════════════════════════════════════════
def color_matrix(name, color, style=MatrixStyle.RGB):
    m = fm.new_rgb_matrix(name)
    m.algorithm = RgbAlgorithm.PLAIN
    m.fixture_grid = list(PARS)
    m.cols, m.rows = len(PARS), 1
    m.colors = ColorSequence([tuple(color)])
    m.style = style
    m.drive_intensity = False        # NUR Farbe -- Dimmer in Ruhe lassen
    return m


def dimmer_matrix(name):
    m = fm.new_rgb_matrix(name)
    m.algorithm = RgbAlgorithm.PLAIN
    m.fixture_grid = list(PARS)
    m.cols, m.rows = len(PARS), 1
    m.colors = ColorSequence([(255, 255, 255)])
    m.style = MatrixStyle.DIMMER     # NUR Dimmer -- Farbe in Ruhe lassen
    m.drive_intensity = False
    m.intensity_min, m.intensity_max = 0, 255
    return m


def color_scene(name, rgb, with_intensity=False):
    """Eine Szene, die nur Farbkanaele setzt (Snap 'reine Farbe'). Mit
    with_intensity=True wird zusaetzlich der Dimmer mitgespeichert -- genau der
    Fehler, ueber den David stolpert (Snap mit angefasstem Dimmer)."""
    sc = fm.new_scene(name)
    for fid in PARS:
        sc.set_value(fid, chan_of[fid]["color_r"], rgb[0])
        sc.set_value(fid, chan_of[fid]["color_g"], rgb[1])
        sc.set_value(fid, chan_of[fid]["color_b"], rgb[2])
        if with_intensity:
            sc.set_value(fid, chan_of[fid]["intensity"], 255)
    return sc


def dimmer_scene(name, level=255):
    sc = fm.new_scene(name)
    for fid in PARS:
        sc.set_value(fid, chan_of[fid]["intensity"], level)
    return sc


def chaser(name, scene_ids, hold=0.4):
    c = fm.new_chaser(name)
    c.run_order, c.direction = RunOrder.Loop, Direction.Forward
    for sid in scene_ids:
        c.steps.append(ChaserStep(function_id=sid, fade_in=0.0, hold=hold, fade_out=0.0))
    return c


# ════════════════════════════════════════════════════════════════════════════
#  Report-Helfer
# ════════════════════════════════════════════════════════════════════════════
RESULTS: list[tuple[str, bool, str]] = []
COLNAMES = {"color_r": "R", "color_g": "G", "color_b": "B", "color_w": "W"}


def show_par_row(fid: int) -> str:
    cols = " ".join(f"{COLNAMES[a]}={raw(fid, a):3d}"
                    for a in ("color_r", "color_g", "color_b", "color_w"))
    inten = raw(fid, "intensity")
    (lr, lg, lb), li = live_view_shows(fid)
    lbl = "100%" if li >= 250 else (f"{int(li/255*100)}%" if li > 0 else "AUS")
    return (f"    PAR {fid}: [{cols}  DIMMER={inten:3d}]   "
            f"Live-Viewer: Farbe=rgb({lr:3d},{lg:3d},{lb:3d}) Intensitaet={lbl}")


def check_color_effect(title: str):
    """Pro PAR: mind. ein Farbkanal > 0  UND  Dimmer == 0."""
    print(f"\n  [{title}]")
    ok = True
    for fid in PARS:
        print(show_par_row(fid))
        color_on = any(raw(fid, a) > 0 for a in ("color_r", "color_g", "color_b", "color_w"))
        dim = raw(fid, "intensity")
        if not color_on or dim != 0:
            ok = False
    verdict = ("Farbe gesetzt, Dimmer == 0 -> Intensitaet AUS"
               if ok else "!! Dimmer NICHT 0 oder keine Farbe -> Leck!")
    print(f"    => {'OK ' if ok else 'FAIL'}: {verdict}")
    RESULTS.append((title, ok, verdict))
    return ok


def check_dimmer_effect(title: str):
    """Pro PAR: Dimmer > 0  UND  alle Farbkanaele == 0."""
    print(f"\n  [{title}]")
    ok = True
    for fid in PARS:
        print(show_par_row(fid))
        color_on = any(raw(fid, a) > 0 for a in ("color_r", "color_g", "color_b", "color_w"))
        dim = raw(fid, "intensity")
        if dim == 0 or color_on:
            ok = False
    verdict = ("Dimmer gesetzt, alle Farbkanaele == 0 -> keine Farbe"
               if ok else "!! Farbkanal NICHT 0 oder kein Dimmer -> Leck!")
    print(f"    => {'OK ' if ok else 'FAIL'}: {verdict}")
    RESULTS.append((title, ok, verdict))
    return ok


# ════════════════════════════════════════════════════════════════════════════
#  TEIL 1 -- FARB-EFFEKTE  (strikte Trennung: implicit_brightness = False)
# ════════════════════════════════════════════════════════════════════════════
state.implicit_brightness = False
state._rebuild_render_plan()

print("=" * 78)
print(" TEIL 1  FARB-EFFEKTE  (implicit_brightness=False = strikte Trennung)")
print("         Erwartung: Farbe sichtbar, DIMMER == 0 (Intensitaet AUS)")
print("=" * 78)

# 1a) RGB-Matrix  Rot / Gruen / Blau
for cname, col in (("Rot", (255, 0, 0)), ("Gruen", (0, 255, 0)), ("Blau", (0, 0, 255))):
    stop_all()
    m = color_matrix(f"RGB-Matrix {cname}", col, MatrixStyle.RGB)
    fm.start(m.id)
    render(4)
    check_color_effect(f"RGB-Matrix {cname}  (style=RGB)")

# 1b) RGBW-Matrix  Rot (RGB) + Weiss (echter W-Kanal)
stop_all()
m = color_matrix("RGBW-Matrix Rot", (255, 0, 0), MatrixStyle.RGBW)
fm.start(m.id); render(4)
check_color_effect("RGBW-Matrix Rot  (style=RGBW, R-Kanal)")

stop_all()
m = color_matrix("RGBW-Matrix Weiss", (255, 255, 255), MatrixStyle.RGBW)
fm.start(m.id); render(4)
check_color_effect("RGBW-Matrix Weiss (style=RGBW, echter W-Kanal, RGB=0)")

# 1c) FARB-CHASE aus sauberen Farb-Snaps (Rot -> Gruen -> Blau, KEIN Dimmer im Snap)
stop_all()
sc_r = color_scene("Snap Rot", (255, 0, 0))
sc_g = color_scene("Snap Gruen", (0, 255, 0))
sc_b = color_scene("Snap Blau", (0, 0, 255))
ch = chaser("Farb-Chase (saubere Snaps)", [sc_r.id, sc_g.id, sc_b.id], hold=0.4)
fm.start(ch.id)
print("\n  [Farb-Chase (saubere Snaps Rot->Gruen->Blau)] -- ueber mehrere Schritte:")
chase_ok = True
for t in range(0, 60):                 # ~1.4 s -> deckt mehrere Schritte ab
    state._render_frame(DT)
    if t in (3, 25, 47):               # je ein Sample pro Schritt
        snap_ok = True
        for fid in PARS:
            color_on = any(raw(fid, a) > 0 for a in ("color_r", "color_g", "color_b"))
            if raw(fid, "intensity") != 0 or not color_on:
                snap_ok = False
        (lr, lg, lb), li = live_view_shows(1)
        print(f"    Frame {t:2d}: PAR1 Live-Viewer Farbe=rgb({lr},{lg},{lb}) "
              f"Intensitaet={'AUS' if li == 0 else li}  "
              f"-> {'OK' if snap_ok else 'FAIL'}")
        chase_ok = chase_ok and snap_ok
RESULTS.append(("Farb-Chase (saubere Snaps)", chase_ok,
                "Dimmer ueber alle Schritte 0" if chase_ok else "Dimmer-Leck im Chase!"))
print(f"    => {'OK ' if chase_ok else 'FAIL'}: reiner Farb-Chase laesst den Dimmer in Ruhe")

# ════════════════════════════════════════════════════════════════════════════
#  TEIL 2 -- DIMMER-EFFEKTE  (Erwartung: Dimmer an, ALLE Farbkanaele == 0)
# ════════════════════════════════════════════════════════════════════════════
print("\n" + "=" * 78)
print(" TEIL 2  DIMMER-EFFEKTE")
print("         Erwartung: DIMMER gesetzt, alle Farbkanaele == 0 (keine Farbe)")
print("=" * 78)

# 2a) Dimmer-Matrix
stop_all()
m = dimmer_matrix("Dimmer-Matrix Voll")
fm.start(m.id); render(4)
check_dimmer_effect("Dimmer-Matrix Voll (style=DIMMER)")

# 2b) Dimmer-Chase aus reinen Dimmer-Snaps
stop_all()
d1 = dimmer_scene("Snap Dim 100%", 255)
d2 = dimmer_scene("Snap Dim 40%", 102)
dch = chaser("Dimmer-Chase", [d1.id, d2.id], hold=0.4)
fm.start(dch.id); render(4)
check_dimmer_effect("Dimmer-Chase (reine Dimmer-Snaps)")

# ════════════════════════════════════════════════════════════════════════════
#  TEIL 3 -- AUFKLAERUNG: woher das "es kam ein Dimmer dazu"-Gefuehl kommt
# ════════════════════════════════════════════════════════════════════════════
print("\n" + "=" * 78)
print(" TEIL 3  AUFKLAERUNG  (zwei Wege, wie ein Dimmer 'mitkommt')")
print("=" * 78)

# 3a) DERSELBE reine Farb-Effekt, aber implicit_brightness = True (Default!):
#     der RENDERER hebt den Dimmer automatisch auf 255, damit die Farbe leuchtet.
stop_all()
state.implicit_brightness = True
state._rebuild_render_plan()
m = color_matrix("RGB-Matrix Rot (impl. Helligkeit AN)", (255, 0, 0), MatrixStyle.RGB)
fm.start(m.id); render(4)
print("\n  [3a] Reiner RGB-Farbeffekt, aber implicit_brightness=TRUE (Standard):")
for fid in PARS:
    print(show_par_row(fid))
auto = all(raw(fid, "intensity") == 255 for fid in PARS)
print(f"    => Der EFFEKT schreibt KEINEN Dimmer; der RENDERER hebt ihn automatisch "
      f"auf 255 (auto-voll={auto}).")
print("       -> Das sieht aus wie 'Dimmer kam mit', ist aber NICHT im Effekt "
      "gespeichert. implicit_brightness=False schaltet es ab (siehe Teil 1).")
RESULTS.append(("Aufklaerung implicit_brightness", auto,
                "Render-Auto-Voll erklaert das Phaenomen" if auto else "unerwartet"))

# 3b) Chase aus einem Snap, der MIT Dimmer gespeichert wurde (Davids echter Fehler):
stop_all()
state.implicit_brightness = False
state._rebuild_render_plan()
dirty = color_scene("Snap Rot MIT Dimmer", (255, 0, 0), with_intensity=True)
dch2 = chaser("Chase aus 'schmutzigem' Snap", [dirty.id], hold=0.5)
fm.start(dch2.id); render(4)
print("\n  [3b] Farb-Chase, dessen Snap MIT angefasstem Dimmer gespeichert wurde:")
for fid in PARS:
    print(show_par_row(fid))
leaked = any(raw(fid, "intensity") > 0 for fid in PARS)
print(f"    => Dimmer kommt mit (intensity>0={leaked}) -- WEIL der Snap ihn enthaelt, "
      "nicht wegen des Chase-Mechanismus.")
print("       Fix: Snap mit 'Clear' frisch + im Speicher-Dialog 'Kanaele auswaehlen' "
      "die Gruppe Intensity/Dimmer ABWAEHLEN (snap_file_panel.py).")
RESULTS.append(("Aufklaerung schmutziger Snap", leaked,
                "Dimmer-Leck stammt aus dem Snap-Inhalt" if leaked else "unerwartet"))

# ════════════════════════════════════════════════════════════════════════════
#  ZUSAMMENFASSUNG
# ════════════════════════════════════════════════════════════════════════════
print("\n" + "=" * 78)
print(" ZUSAMMENFASSUNG")
print("=" * 78)
core = [r for r in RESULTS if not r[0].startswith("Aufklaerung")]
core_ok = all(ok for _, ok, _ in core)
for title, ok, verdict in RESULTS:
    print(f"  [{'OK ' if ok else 'FAIL'}] {title}: {verdict}")
print("-" * 78)
print(f"  Kern-Trennung Farbe<->Dimmer: "
      f"{'ALLE BESTANDEN' if core_ok else 'ABWEICHUNG GEFUNDEN'}")
print("=" * 78)
sys.exit(0 if core_ok else 1)
