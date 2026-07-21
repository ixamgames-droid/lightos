"""Dimmer + Farbe frei kombinieren — EINE VC-Bank fuer Davids 8 PAR (ZQ01424 RGBW).

Zwei UNABHAENGIGE Layer auf GETRENNTEN DMX-Kanaelen des ZQ01424 (Kanal 0 = Master
Dimmer, 1-4 = R/G/B/W):

  (1) DIMMER-Effekte  — Matrix Stil=Dimmer -> schreiben NUR den Master-Dimmer.
      Helligkeit/Bewegung, Farbe bleibt unberuehrt. Alle im edit_slot "dimmer"
      = Radio-Gruppe: immer nur EIN Dimmer-Muster aktiv, killt die Farbe NICHT.
  (2) FARBE          — a) feste Farb-Kacheln (VCColor, with_intensity=False ->
                          setzen NUR R/G/B/W, kein Dimmer) ODER
                       b) Farb-Effekte (Matrix Stil=RGB, drive_intensity=False ->
                          nur Farbe, kein Dimmer), im edit_slot "farbe" = eigene
                          Radio-Gruppe.

Weil Dimmer- und Farb-Layer auf verschiedenen Kanaelen liegen, multiplizieren sie
sich sauber in der Lampe: Dimmer bestimmt Helligkeit/Bewegung, Farbe den Farbton.
Bedienung: 1 Dimmer-Effekt + 1 Farbe (fest ODER Effekt) anklicken -> fertig.

Aufruf:  venv/Scripts/python.exe tools/build_dimmer_farbe_combo.py
Erzeugt: shows/Dimmer_Farbe_Kombinieren.lshow  (selbst-verifizierend, headless)
"""
from _builder import ShowBuilder, build_and_verify   # noqa: E402

b = ShowBuilder()
PARS = b.patch("ZQ01424", count=8, channel_count=8, mode_name="8-Kanal RGBW")
BANK = 0

TOGGLE = "FunctionToggle"

# ── (1) DIMMER-Effekte — Stil=Dimmer, edit_slot="dimmer" ─────────────────────
dim_defs = [
    ("Voll An",   "Plain",        "hot_white"),
    ("Lauflicht", "Chase",        "color_chase"),
    ("Welle",     "Wave",         "vu_meter"),
    ("Puls",      "Atmen (Puls)", "pulse"),
    ("Strobe",    "Strobe",       "strobe"),
    ("Random",    "Random",       "sparkle"),
]
DIM_X = [20, 180, 340, 500, 660, 820]
for (name, algo, bg), x in zip(dim_defs, DIM_X):
    m = b.matrix(f"Dimmer: {name}", algo, style="Dimmer", fixtures=PARS)
    w = b.button(name, TOGGLE, function=m, bank=BANK, bg_image=bg, edit_slot="dimmer")
    w.setGeometry(x, 72, 150, 64)

# ── (2a) FESTE FARBEN — VCColor, nur Farbe (with_intensity=False) ────────────
col_defs = [
    ("Rot",     255,   0,   0, 0),
    ("Grün",      0, 255,   0, 0),
    ("Blau",      0,   0, 255, 0),
    ("Gelb",    255, 255,   0, 0),
    ("Cyan",      0, 255, 255, 0),
    ("Magenta", 255,   0, 255, 0),
    ("Amber",   255, 110,   0, 0),
    ("Weiß",    255, 255, 255, 255),
]
COL_X = [20, 140, 260, 380, 500, 620, 740, 860]
for (name, r, g, bl, wch), x in zip(col_defs, COL_X):
    c = b.color(name, "Alle Fixtures", bank=BANK, with_intensity=False,
                color_r=r, color_g=g, color_b=bl, color_w=wch)
    c.setGeometry(x, 176, 112, 78)

# ── (2b) FARB-Effekte — Stil=RGB, drive_intensity=False, edit_slot="farbe" ───
RGB = [(255, 0, 0), (0, 255, 0), (0, 0, 255)]
colfx_defs = [
    ("Regenbogen",     "Rainbow",    None,                       "rainbow_scroll"),
    ("Color Fade",     "Color Fade", [(255,0,0),(0,255,0),(0,0,255),(255,0,255)], "color_wheel"),
    ("Gradient",       "Gradient",   [(255,0,0),(0,0,255)],      "spectrum"),
    ("Wipe",           "Wipe",       [(0,255,255),(255,0,255)],  "beam_sweep"),
    ("Feuer",          "Feuer",      None,                       "gobo_spin"),
    ("Farb-Lauflicht", "Chase",      RGB,                        "color_chase"),
]
for (name, algo, colors, bg), x in zip(colfx_defs, DIM_X):
    m = b.matrix(f"Farbe: {name}", algo, style="RGB", fixtures=PARS,
                 colors=colors, drive_intensity=False)
    w = b.button(name, TOGGLE, function=m, bank=BANK, bg_image=bg, edit_slot="farbe")
    w.setGeometry(x, 294, 150, 64)

# ── Beschriftungen ───────────────────────────────────────────────────────────
def lbl(text, x, y, w=980, h=22):
    e = b.label(text, bank=BANK)
    e.setGeometry(x, y, w, h)

lbl("So kombinierst du:  1) EINEN Dimmer-Effekt   +   2) EINE Farbe (fest ODER Effekt)", 20, 12, 980, 24)
lbl("①  DIMMER  —  Helligkeit / Bewegung (nur EINER aktiv, Farbe bleibt)", 20, 48)
lbl("②  FARBE  —  feste Farbe anklicken (setzt nur den Farbton)", 20, 152)
lbl("…  ODER ein Farb-Effekt (nur EINER aktiv — überschreibt die feste Farbe; erneut klicken = aus)", 20, 270)

# ── Master / Panik unten ─────────────────────────────────────────────────────
gm = b.slider("Grand Master", "GrandMaster", bank=BANK)
gm.setGeometry(20, 384, 90, 120)
b_stop = b.button("Alles aus", "StopEffects", bank=BANK)
b_stop.setGeometry(130, 384, 150, 64)
b_black = b.button("BLACKOUT", "Blackout", bank=BANK)
b_black.setGeometry(300, 384, 150, 64)

build_and_verify(b, "shows/Dimmer_Farbe_Kombinieren.lshow",
                 name="Dimmer + Farbe kombinieren")
