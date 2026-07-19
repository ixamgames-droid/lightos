"""Prueft shows/Demo_Show_Full.lshow headless und rendert echte Bilder:
  * die 5 VC-Baenke (VCCanvas.grab) — exakt das Konsolen-Layout,
  * Licht-Ausgabe (Top-Down) mehrerer Looks aus dem ECHTEN DMX-Render,
  * die 3D-Anordnung (Top + Seite) aus visualizer_positions.
Erzeugt PNGs unter docs/check_demo_show_full/. Nicht-destruktiv, offscreen.
"""
from __future__ import annotations
import os
import sys
import math

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("LIGHTOS_SHOW_DB", os.path.join(os.environ.get("TEMP", "."), "lightos_check.db"))
# Restliche Isolations-Schalter (offscreen, kein Output-Thread/Audio, SERIAL_INPROC
# gegen den __mp_main__-Doppellauf) zentral aus _gen_env — DEMO-02/STAB-CURSHOW.
import _gen_env  # noqa: F401,E402

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QImage, QPainter, QColor, QPen, QFont
from PySide6.QtCore import Qt, QRectF
_app = QApplication.instance() or QApplication([])

from src.core.app_state import get_state, get_channels_for_patched
from src.core.engine.function_manager import get_function_manager
from src.core.engine.bpm_manager import get_bpm_manager
from src.core.show.show_file import load_show

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTDIR = os.path.join(_ROOT, "docs", "check_demo_show_full")
os.makedirs(OUTDIR, exist_ok=True)
SHOW = os.path.join(_ROOT, "shows", "Demo_Show_Full.lshow")

ok, msg = load_show(SHOW)
print("Load:", ok, msg)
assert ok
state = get_state()
fm = get_function_manager()
byname = {f.name: f for f in fm.all()}
fixtures = state.get_patched_fixtures()
chans = {f.fid: get_channels_for_patched(f) for f in fixtures}


def abs_ch(fid, attr):
    f = next(x for x in fixtures if x.fid == fid)
    out = []
    for c in chans[fid]:
        if (c.attribute or "").lower() == attr:
            out.append(f.address + (c.channel_number - 1))
    return out


# ── 1) VC-BAENKE rendern ─────────────────────────────────────────────────────
def render_banks():
    from src.ui.virtualconsole.vc_canvas import VCCanvas
    canvas = VCCanvas()
    canvas.resize(1000, 760)
    try:
        canvas.from_dict(state._vc_layout)
    except Exception as e:
        print("  Canvas from_dict Fehler:", e)
        return
    names = ["0_Farbe", "1_Dimmer", "2_Strobe", "3_Bewegung", "4_Uebersicht"]
    for bank, nm in enumerate(names):
        try:
            canvas.set_active_bank(bank)
        except Exception:
            canvas._active_bank = bank
            canvas._apply_bank_visibility()
        _app.processEvents()
        pm = canvas.grab()
        p = os.path.join(OUTDIR, f"console_bank_{nm}.png")
        pm.save(p)
        print("  geschrieben:", os.path.basename(p))


# ── 2) LICHT-AUSGABE (Top-Down) aus echtem DMX ───────────────────────────────
W, H = 1000, 680


def fixture_rgb(fid):
    u = state.universes.get(1)
    if u is None:
        return (0, 0, 0), 0
    def rd(attr):
        cs = abs_ch(fid, attr)
        return max((int(u.get_channel(a)) for a in cs), default=0)
    inten = rd("intensity")
    r, g, b, w = rd("color_r"), rd("color_g"), rd("color_b"), rd("color_w")
    if r or g or b or w:
        col = (min(255, r + w), min(255, g + w), min(255, b + w))
    else:
        col = (255, 200, 120)            # Mover ohne RGB -> warmweiss (Farbrad)
    if inten <= 0 and any(abs_ch(fid, "intensity")):
        scale = 0.0
    else:
        scale = (inten / 255.0) if any(abs_ch(fid, "intensity")) else 1.0
    return tuple(int(c * (0.15 + 0.85 * scale)) for c in col), inten


def pan_angle(fid):
    u = state.universes.get(1)
    cs = abs_ch(fid, "pan")
    if not cs or u is None:
        return None
    return (int(u.get_channel(cs[0])) / 255.0) * 270.0 - 135.0   # -135..135 deg


def draw_lights(path, title):
    img = QImage(W, H, QImage.Format.Format_RGB32)
    img.fill(QColor("#0a0a12"))
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.fillRect(0, 0, W, 40, QColor("#161b22"))
    p.setPen(QColor("#e6edf3")); p.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
    p.drawText(16, 27, title)
    p.setPen(QColor("#6e7681")); p.setFont(QFont("Segoe UI", 8))
    p.drawText(16, H - 10, "Buehne oben · Publikum unten   |   MH (Trasse, hinten/oben) · Spider (Boden, vorne)")
    lv = {int(k): v for k, v in state.live_view_positions.items()}
    sx = W / 1200.0; sy = (H - 70) / 800.0
    for f in fixtures:
        if f.fid not in lv:
            continue
        x = 20 + lv[f.fid][0] * sx; y = 50 + lv[f.fid][1] * sy
        (r, g, b), inten = fixture_rgb(f.fid)
        is_mover = f.fixture_type == "moving_head"
        rad = 26 if is_mover else 30
        # Glow
        for k, a in ((2.2, 26), (1.5, 60), (1.0, 230)):
            p.setPen(Qt.PenStyle.NoPen)
            col = QColor(r, g, b); col.setAlpha(a)
            p.setBrush(col)
            p.drawEllipse(QRectF(x - rad * k / 2, y - rad * k / 2, rad * k, rad * k))
        p.setPen(QPen(QColor("#30363d"), 1)); p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QRectF(x - rad / 2, y - rad / 2, rad, rad))
        # Mover-Strahlrichtung (pan)
        ang = pan_angle(f.fid)
        if ang is not None and inten > 0:
            a = math.radians(ang - 90)
            p.setPen(QPen(QColor(r, g, b), 3))
            p.drawLine(int(x), int(y), int(x + 46 * math.cos(a)), int(y + 46 * math.sin(a)))
        p.setPen(QColor("#8b949e")); p.setFont(QFont("Segoe UI", 7))
        p.drawText(int(x - 22), int(y + rad / 2 + 12), f.label)
    p.end()
    img.save(path)
    print("  geschrieben:", os.path.basename(path))


def look(path, title, names, frames=1):
    for f in list(fm.all()):
        if fm.is_running(f.id):
            fm.stop(f.id)
    get_bpm_manager().request_bpm(150.0, "diag")
    for nm in names:
        if nm in byname:
            fm.start(byname[nm].id)
    for _ in range(8):
        state._render_frame(1 / 44.0)
    draw_lights(path, title)


# ── 3) 3D-ANORDNUNG (Top + Seite) aus visualizer_positions ───────────────────
def render_stage():
    vp = {int(k): tuple(v) for k, v in state.visualizer_positions.items()}
    img = QImage(W, 420, QImage.Format.Format_RGB32)
    img.fill(QColor("#0a0a12"))
    p = QPainter(img); p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(QColor("#e6edf3")); p.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
    p.drawText(16, 24, "3D-Anordnung (aus der Show) — links: Seitenansicht (Hoehe) · rechts: Top-Down")
    cx_side, cx_top = 250, 740
    # Boden-Linien
    p.setPen(QPen(QColor("#30363d"), 1))
    p.drawLine(40, 360, 460, 360); p.drawLine(540, 360, 960, 360)
    p.setPen(QColor("#6e7681")); p.setFont(QFont("Segoe UI", 8))
    p.drawText(40, 378, "Boden"); p.drawText(540, 378, "Boden (Top-Down)")
    for f in fixtures:
        if f.fid not in vp:
            continue
        x3, y3, z3 = vp[f.fid]
        col = {"par": "#3fb950", "moving_head": "#d29922"}.get(f.fixture_type, "#888")
        # Seite: x->horiz, y(Hoehe)->vertikal
        sx = cx_side + x3 * 26; sy = 360 - y3 * 42
        p.setBrush(QColor(col)); p.setPen(QPen(QColor("#0d1117"), 1))
        p.drawEllipse(QRectF(sx - 8, sy - 8, 16, 16))
        # Top: x->horiz, z(Tiefe)->vertikal
        tx = cx_top + x3 * 26; ty = 250 + z3 * 36
        p.drawEllipse(QRectF(tx - 8, ty - 8, 16, 16))
    p.setPen(QColor("#8b949e")); p.setFont(QFont("Segoe UI", 8))
    p.drawText(40, 400, "Gruen=PAR (Boden)  ·  Gelb=Mover: MH y=6m (Trasse, hinten) / Spider y=0.6m (vorne)")
    p.end()
    path = os.path.join(OUTDIR, "stage_3d_layout.png")
    img.save(path); print("  geschrieben:", os.path.basename(path))


print("\n[1] VC-Baenke:")
render_banks()
print("\n[2] Licht-Looks:")
look(os.path.join(OUTDIR, "light_1_farbe_voll.png"),
     "Look 1: Farbe (Farbwechsel) + Licht An — PAR & Spider farbig, MH warm",
     ["PAR Farbwechsel", "PAR Dimmer Voll", "Spider Farbwechsel", "Spider Dimmer Voll",
      "MH Rot", "MH Dimmer Voll"])
look(os.path.join(OUTDIR, "light_2_bewegung.png"),
     "Look 2: Lauflicht + MH Kreis + Spider Schere (gelayert)",
     ["PAR Lauflicht", "PAR Dimmer Voll", "MH Kreis", "MH Dimmer Voll",
      "Spider Schere", "Spider Dimmer Voll", "Spider Solid"])
look(os.path.join(OUTDIR, "light_3_strobe.png"),
     "Look 3: Strobe Alle (Moment-Blitz)", ["Strobe Alle", "All White"])
print("\n[3] 3D-Anordnung:")
render_stage()
print("\nFERTIG — Bilder unter:", OUTDIR)
print("Dateien:", sorted(os.listdir(OUTDIR)))
