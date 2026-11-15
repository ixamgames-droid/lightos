"""VIZ-56: einen GDTF-Typ, den die Bibliothek nicht kennt, als Profil anlegen.

Robins Vorgabe: ein unbekannter Typ bricht den Import nicht ab und
verschwindet nicht stumm — er wird mit den Kanaelen aus der GDTF angelegt und
bleibt zuordenbar. Dieses Modul baut daraus das Payload fuer
``fixture_db.create_user_profile`` (Format wie der Fixture-Generator).

* Attribute werden auf die FESTE Liste ``bibliothek_format.ATTRIBUTE``
  abgebildet (:data:`ATTRIBUT_KARTE`). Was dort nicht hinpasst, wird ``raw`` —
  ein Fader mit dem GDTF-Namen, nie weggelassen.
* 16 bit (``Offset="1,2"``): der grobe Kanal traegt das Attribut, der feine
  ist ein eigener Kanal — ``pan_fine``/``tilt_fine`` wie bei den
  eingebauten Profilen, sonst ``raw`` mit „… fein“. Ein dritter Offset (24 bit)
  wird „… ultra“.
* Luecken im Fussabdruck (kein GDTF-Kanal auf einer Adresse) werden mit
  ``raw``-Kanaelen „Kanal n“ aufgefuellt — die Kanalzahl stimmt immer.
* Herkunft: ``source="user"``, ``notes`` und der Kurzname nennen „mvr/gdtf“.
"""
from __future__ import annotations

from .lesen import GdtfKanal, GdtfModus, GdtfTyp

HERKUNFT = "mvr/gdtf"

#: GDTF-Attribut (ohne Gross/Klein) -> LightOS-Attribut.
ATTRIBUT_KARTE: dict[str, str] = {
    "dimmer": "intensity",
    "pan": "pan", "tilt": "tilt",
    "panrotate": "raw", "tiltrotate": "raw",
    "coloradd_r": "color_r", "colorrgb_red": "color_r",
    "coloradd_g": "color_g", "colorrgb_green": "color_g",
    "coloradd_b": "color_b", "colorrgb_blue": "color_b",
    "coloradd_w": "color_w", "colorrgb_white": "color_w",
    "coloradd_ww": "color_w", "coloradd_cw": "color_w",
    "colorrgb_warmwhite": "color_w", "colorrgb_coolwhite": "color_w",
    "colorrgb_neutralwhite": "color_w",
    "coloradd_a": "color_a", "colorrgb_amber": "color_a",
    "coloradd_uv": "color_uv", "colorrgb_uv": "color_uv",
    "colorsub_c": "cmy_c", "colorsub_m": "cmy_m", "colorsub_y": "cmy_y",
    "color1": "color_wheel", "color1wheelindex": "color_wheel",
    "colormacro1": "macro",
    "gobo1": "gobo_wheel", "gobo2": "gobo_wheel2",
    "gobo1pos": "gobo_rotation", "gobo1posrotate": "gobo_rotation",
    "gobo1wheelspin": "gobo_rotation", "gobo1selectspin": "gobo_rotation",
    "animationwheel1": "animation", "animationsystem1": "animation",
    "prism1": "prism", "prism1pos": "prism_rotation",
    "prism1posrotate": "prism_rotation",
    "zoom": "zoom", "focus1": "focus", "iris": "iris",
    "frost1": "frost",
    "shutter1": "shutter", "shutter1strobe": "strobe",
    "strobefrequency": "strobe", "strobeduration": "duration",
    "pantiltspeed": "speed", "pantilttime": "speed", "mspeed": "speed",
    "effects1": "effect", "effects1rate": "effect_speed",
    "effectsrate": "effect_speed",
    "fog": "raw", "fan": "fan", "fogtype": "raw",
    "control1": "macro", "devicereset": "reset", "lampcontrol": "lamp",
    "lamponoff": "lamp",
}

#: Ranges: GDTF-Attribut einer ChannelFunction -> ``ChannelRange.kind``.
_ART = {
    "shutter1": "open", "shutter1strobe": "strobe", "strobefrequency": "strobe",
    "color1": "color", "gobo1": "gobo", "gobo2": "gobo",
    "gobo1wheelspin": "rotate", "gobo1posrotate": "rotate",
    "prism1": "prism", "frost1": "frost", "devicereset": "reset",
}


def lightos_attribut(gdtf_attribut: str) -> str:
    """``"ColorAdd_R"`` -> ``"color_r"``; Unbekanntes -> ``"raw"``."""
    a = (gdtf_attribut or "").strip().casefold()
    if a in ATTRIBUT_KARTE:
        return ATTRIBUT_KARTE[a]
    if a.startswith("dimmer"):
        return "intensity"
    return "raw"


def _kanal_name(k: GdtfKanal, mehrere_geometrien: bool) -> str:
    basis = k.attribut or k.name or "Kanal"
    if mehrere_geometrien and k.geometrie:
        return f"{k.geometrie} {basis}"
    return basis


def _ranges(k: GdtfKanal) -> list[dict]:
    if len(k.funktionen) < 2:
        return []
    funktionen = sorted(k.funktionen, key=lambda f: f.von)
    aus = []
    for i, f in enumerate(funktionen):
        bis = funktionen[i + 1].von - 1 if i + 1 < len(funktionen) else 255
        if bis < f.von:
            continue
        aus.append({"range_from": f.von, "range_to": bis,
                    "name": f.name or f.attribut or "",
                    "kind": _ART.get((f.attribut or "").casefold(), "")})
    return aus


def modus_payload(modus: GdtfModus) -> dict:
    geometrien = {k.geometrie for k in modus.kanaele if k.geometrie}
    mehrere = len(geometrien) > 1
    belegt: dict[int, dict] = {}
    for k in modus.kanaele:
        attr = lightos_attribut(k.attribut)
        name = _kanal_name(k, mehrere)
        for stufe, offset in enumerate(k.offsets):
            if offset in belegt:
                continue        # doppelt belegter Offset: der erste gilt
            if stufe == 0:
                eintrag = {"name": name, "attribute": attr,
                           "default_value": k.default,
                           "ranges": _ranges(k)}
            elif stufe == 1:
                fein = {"pan": "pan_fine", "tilt": "tilt_fine"}.get(attr, "raw")
                eintrag = {"name": f"{name} fein", "attribute": fein,
                           "default_value": 0, "ranges": []}
            else:
                eintrag = {"name": f"{name} ultra", "attribute": "raw",
                           "default_value": 0, "ranges": []}
            belegt[offset] = eintrag
    kanalzahl = modus.kanalzahl
    kanaele = []
    for nr in range(1, kanalzahl + 1):
        e = belegt.get(nr) or {"name": f"Kanal {nr}", "attribute": "raw",
                               "default_value": 0, "ranges": []}
        kanaele.append({"channel_number": nr, "name": e["name"][:80],
                        "attribute": e["attribute"],
                        "default_value": int(e["default_value"]),
                        "highlight_value": 255, "invert": False,
                        "resolution": "8bit", "ranges": e["ranges"]})
    return {"name": modus.name, "channel_count": kanalzahl, "channels": kanaele}


def geraetetyp(typ: GdtfTyp) -> str:
    """Grobe Einordnung fuer ``fixture_type`` aus den Attributen."""
    attrs = {lightos_attribut(k.attribut) for m in typ.modi for k in m.kanaele}
    if {"pan", "tilt"} <= attrs:
        return "moving_head"
    if attrs & {"color_r", "color_g", "color_b", "color_w", "cmy_c"}:
        return "par"
    if "strobe" in attrs and "intensity" in attrs and len(attrs) <= 3:
        return "strobe"
    return "other"


def profil_payload(typ: GdtfTyp) -> dict:
    """Payload fuer ``fixture_db.create_user_profile``. Modi ohne DMX-Kanal
    werden ausgelassen (ein Modus mit 0 Kanaelen ist nicht patchbar)."""
    hersteller = typ.hersteller or "Unbekannt"
    name = typ.name or typ.langname or typ.datei
    modi = [modus_payload(m) for m in typ.modi if m.kanalzahl > 0]
    return {
        "manufacturer": hersteller,
        "short_mfr": "".join(ch for ch in hersteller if ch.isalnum())[:8].upper() or "MVR",
        "name": name,
        "short_name": name[:40],
        "fixture_type": geraetetyp(typ),
        "power_w": 0,
        "notes": (f"Angelegt beim MVR-Import aus der GDTF-Datei „{typ.datei}“ "
                  f"(Herkunft: {HERKUNFT})."),
        "source": "user",
        "viz_model": "",
        "modes": modi,
    }
