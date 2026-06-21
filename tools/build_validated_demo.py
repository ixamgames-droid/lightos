"""Beispiel-/Proof-Show über die ShowBuilder-DSL — baut eine kleine, ECHTE Show,
bei der jeder Baustein gegen die reflektierten echten Sätze validiert ist.

    venv/Scripts/python.exe tools/build_validated_demo.py
    -> shows/Validated_Demo.lshow  (statisch + live validiert, Render-geprüft)

Zeigt das Muster für künftige Generatoren: kurze, deklarative Bau-Schritte; jeder
fake Algo/Action/Param/Fixture würde SOFORT mit BuildError abbrechen.
"""
from __future__ import annotations

import os

from _builder import (ShowBuilder, RgbAlgorithm, ButtonAction, BuildError,
                      build_and_verify)

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(_ROOT, "shows", "Validated_Demo.lshow")

b = ShowBuilder()

# Echte PAR-Reihe patchen (Davids Rig). Fehlt das Profil, ohne Fixtures bauen —
# die Validierung greift trotzdem; Render-Smoke nur mit Fixtures.
render_targets = []
try:
    pars = b.patch("ZQ01424", count=8, channel_count=8, mode_name="8-Kanal RGBW")
except BuildError as exc:
    print(f"[info] kein Patch ({exc}); baue ohne Fixtures.")
    pars = []

# Funktionen — nur echte Algorithmen/Styles/Params.
farbe = b.matrix("PAR Farbwechsel", algorithm=RgbAlgorithm.CHASE, style="RGB",
                 fixtures=pars, colors=[(255, 0, 0), (0, 255, 0), (0, 0, 255)],
                 params={"runner_count": 2, "movement": "normal"})
voll = b.matrix("PAR Dimmer Voll", algorithm=RgbAlgorithm.PLAIN, style="Dimmer",
                fixtures=pars)
if pars:
    render_targets = [voll]

# VC-Seite 0 — jede Bindung ist bindungs-bewusst geprüft.
b.label("— FARBE —", bank=0)
b.button("Farbe an/aus", action=ButtonAction.FUNCTION_TOGGLE, function=farbe, bank=0)
b.slider("Farb-Tempo", mode="EffectSpeed", param_key="speed", function=farbe, bank=0)
b.color("Aktive Farbe", target="Effekt (aktive Farbe)", function=farbe, bank=0)
b.button("Voll an/aus", action=ButtonAction.FUNCTION_TOGGLE, function=voll, bank=0)
b.slider("Helligkeit", mode="EffectIntensity", param_key="intensity", function=voll, bank=0)

build_and_verify(b, OUT, render=render_targets, name="Validated Demo")
