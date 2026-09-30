"""DOC-16: Doku-Demo-Show — reproduzierbar, NUR aus eingebauten Generic-Profilen.

Die Show ist fuer Anleitungsbilder gedacht und bildet bewusst kein echtes Rig
nach: keine Markenprofile, keine Nutzershow als Quelle, feste Labels, feste
Adressen und feste Buehnenpositionen. Zwei Laeufe liefern dieselbe Show.

Inhalt (Universum 1):

* ``PAR 1…8``           Generic ``PARD`` (Dimmer+RGB, 4 Kanaele), Adresse 1…29
* ``Wash 1/2``          Generic ``MHW7`` (Moving Head Wash RGB, 7 Kanaele)
* ``Spot 1/2``          Generic ``MH8`` (Moving Head Spot, Pan/Tilt, 8 Kanaele)
* ``LED-Leiste``        Generic ``BAR12`` (4 x RGB, 12 Kanaele)
* Gruppen: „Alle PAR", „PAR links", „PAR rechts", „Moving Heads"
* Funktionen: drei Farb-Szenen, ein Farb-Lauflicht (Chaser), eine
  Regenbogen-Matrix und ein Kreis-EFX
* Cue-Liste „Doku-Cues" mit drei Cues
* VC-Seite 1 mit sechs Knoepfen, vier Fadern und einer Beschriftung

Muss NACH :func:`sandbox.einrichten` importiert werden.
"""
from __future__ import annotations

import json
import os

DATEINAME = "Doku_Demo.lshow"
SHOW_NAME = "Doku-Demo"

# Feste Buehnenpositionen fuer die 2D-Ansicht (Weltkoordinaten 1200 x 800).
_PAR_X = [270.0 + i * 95.0 for i in range(8)]


def bauen(ziel_ordner: str) -> tuple[str, dict]:
    """Baut die Show, speichert sie nach ``ziel_ordner`` und gibt
    ``(pfad, info)`` zurueck; ``info`` haelt die fids je Rolle."""
    from sqlalchemy import delete
    from src.core.show.showbuilder import ShowBuilder
    from src.core.engine.rgb_matrix import RgbAlgorithm
    from src.core.engine.efx import EfxAlgorithm
    from src.core.engine.chaser import ChaserStep
    from src.core.engine.cue import Cue
    from src.core.database.models import FixtureGroup
    from src.ui.virtualconsole.vc_button import ButtonAction

    b = ShowBuilder()
    st = b.state
    pars = b.patch("PARD", count=8, channel_count=4,
                   mode_name="4-Kanal Dimmer+RGB", label="PAR", start_address=1)
    washes = b.patch("MHW7", count=2, channel_count=7,
                     mode_name="7-Kanal", label="Wash", start_address=41)
    spots = b.patch("MH8", count=2, channel_count=8,
                    mode_name="8-Kanal", label="Spot", start_address=61)
    leiste = b.patch("BAR12", count=1, channel_count=12,
                     mode_name="12-Kanal (4x RGB)", label="LED-Leiste",
                     start_address=81)
    mover = washes + spots

    # ── Buehne: PARs in einer Reihe, Mover dahinter, Leiste vorne ────────────
    lv = {fid: (_PAR_X[i], 430.0) for i, fid in enumerate(pars)}
    lv[washes[0]] = (_PAR_X[1], 250.0)
    lv[washes[1]] = (_PAR_X[6], 250.0)
    lv[spots[0]] = (_PAR_X[3], 220.0)
    lv[spots[1]] = (_PAR_X[4], 220.0)
    lv[leiste[0]] = ((_PAR_X[3] + _PAR_X[4]) / 2.0, 600.0)
    st.live_view_positions = {fid: list(p) for fid, p in lv.items()}
    st.live_view_meta = {"zoom": 1.0, "grid_size": 20, "snap": True,
                         "grid_visible": True, "world_w": 1200, "world_h": 800}
    # Bewusst KEINE visualizer_positions: der Szenengraph leitet die 2D-Lage
    # sonst aus den 3D-Koordinaten ab und ueberschreibt die Werte oben.

    # ── Gruppen ─────────────────────────────────────────────────────────────
    def _gruppe(name, fids):
        return FixtureGroup(name=name, cols=len(fids), rows=1, positions_json=json.dumps(
            {f"{i},0": fid for i, fid in enumerate(fids)}))
    with st._session() as s:
        s.execute(delete(FixtureGroup))
        s.add(_gruppe("Alle PAR", pars))
        s.add(_gruppe("PAR links", pars[:4]))
        s.add(_gruppe("PAR rechts", pars[4:]))
        s.add(_gruppe("Moving Heads", mover))
        s.commit()

    # ── Funktionen ──────────────────────────────────────────────────────────
    farben = [("Rot", (255, 0, 0)), ("Grün", (0, 255, 0)), ("Blau", (0, 0, 255))]
    szenen = []
    for name, (r, g, bl) in farben:
        sc = b.scene(f"Alle PAR {name}")
        for f in pars:
            for kanal, wert in enumerate((255, r, g, bl)):
                sc.fn.set_value(f, kanal, wert)
        szenen.append(sc)
    lauf = b.chaser("Farb-Lauflicht")
    for sc in szenen:
        lauf.fn.steps.append(ChaserStep(function_id=sc.id, fade_in=0.2, hold=1.0))
    regen = b.matrix("Regenbogen", RgbAlgorithm.RAINBOW, style="RGB", fixtures=pars)
    kreis = b.efx("Kreis", EfxAlgorithm.CIRCLE, fixtures=mover)

    # ── Cue-Liste (ShowBuilder kennt keine Cue-Listen -> ueber den State) ────
    stack = st.new_cue_stack("Doku-Cues")
    for nr, (name, (r, g, bl)) in enumerate(farben, 1):
        stack.add_cue(Cue(number=nr, label=f"Alles {name}", fade_in=2.0, values={
            f: {"intensity": 255, "color_r": r, "color_g": g, "color_b": bl}
            for f in pars}))

    # ── VC-Seite 1 ──────────────────────────────────────────────────────────
    b.label("Doku-Demo", bank=0)
    for sc, (name, _rgb) in zip(szenen, farben):
        b.button(name, ButtonAction.FUNCTION_TOGGLE, function=sc, bank=0)
    b.button("Lauflicht", ButtonAction.FUNCTION_TOGGLE, function=lauf, bank=0)
    b.button("Regenbogen", ButtonAction.FUNCTION_TOGGLE, function=regen, bank=0)
    b.button("Kreis", ButtonAction.FUNCTION_TOGGLE, function=kreis, bank=0)
    b.slider("Gesamt", "GrandMaster", bank=0)
    # Gruppen-Dimmer multiplizieren: auf 0 stuenden die Gruppen dunkel.
    b.slider("PAR", "GroupDimmer", programmer_group="Alle PAR", bank=0, value=255)
    b.slider("Mover", "GroupDimmer", programmer_group="Moving Heads", bank=0, value=255)
    b.slider("Tempo", "EffectSpeed", function=regen, bank=0, value=128)

    pfad = os.path.join(ziel_ordner, DATEINAME)
    b.save(pfad, name=SHOW_NAME)
    info = {"pars": pars, "washes": washes, "spots": spots, "leiste": leiste,
            "mover": mover, "stack": "Doku-Cues"}
    return pfad, info
