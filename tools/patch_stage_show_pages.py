"""In-Place-Patch der Buehnen-Show: macht aus dem Single-Page-Layout ein
Zwei-Seiten-Layout (VC-Banks), OHNE die uebrige Show (Library/Funktionen/
base_levels/Patch) anzufassen.

Hintergrund: Die globale data/midi_mappings.json hatte die Fader-CCs 48-51 ein
ZWEITES Mal als Programmer-Farbe (R/G/B/W) belegt -> beim Effekt-Speed-Fader
aenderte sich die Farbe mit (Doppelbelegung). Die globalen Fader-Mappings sind
jetzt entfernt; die Faerber-Funktion gibt es weiterhin -> aber sauber auf einer
eigenen VC-Seite (Bank 2), per Bank-Umschaltung statt Doppelbelegung.

Seite 1 (Bank 1 / index 0) = EFFEKTE: Effekt-Pads + Fader F1-F4 = Effekt-Speed.
Seite 2 (Bank 2 / index 1) = FARBE/RGBW: Fader 1-4 = Rot/Gruen/Blau/Weiss (Programmer).
Immer sichtbar (Bank "Alle"): Farb-Presets oben, Clear/Stop/Blackout, Dimmer, Master.

Aufruf:  python tools/patch_stage_show_pages.py
"""
from __future__ import annotations
import io
import json
import os
import zipfile

SHOW = os.path.join(os.path.dirname(__file__), "..", "shows", "Buehnen_Show.lshow")
SHOW = os.path.abspath(SHOW)

BANK_ALL = -1
BANK_FX = 0      # Seite 1 = Effekte
BANK_RGBW = 1    # Seite 2 = Farbe/RGBW

# Universelle Buttons (auf allen Seiten sichtbar): Note-Nummern
UNIVERSAL_BUTTON_NOTES = {8, 9, 10}   # Clear, Stop All, Blackout
# Slider-CCs, die auf allen Seiten sichtbar bleiben
UNIVERSAL_SLIDER_CCS = {53, 56}       # Dimmer (Submaster), Master (GrandMaster)


def _set_bank(widgets):
    """Setzt die Bank-Zugehoerigkeit der bestehenden Widgets (Seite 1 = Effekte)."""
    for w in widgets:
        t = w.get("type")
        if t == "VCColor":
            w["bank"] = BANK_ALL                      # Farb-Presets immer da
        elif t == "VCButton":
            note = w.get("midi_data1", -1)
            w["bank"] = BANK_ALL if note in UNIVERSAL_BUTTON_NOTES else BANK_FX
        elif t == "VCSlider":
            cc = w.get("midi_cc", -1)
            w["bank"] = BANK_ALL if cc in UNIVERSAL_SLIDER_CCS else BANK_FX
        # VCLabel werden komplett neu gesetzt (s.u.)


def _label(caption, x, y, w, bank, h=26, fg="#cccccc", bg="#111111", font_size=10):
    return {"type": "VCLabel", "caption": caption, "bank": bank,
            "x": x, "y": y, "w": w, "h": h, "bg": bg, "fg": fg, "font_size": font_size}


def _new_labels():
    """Saubere Labels (UTF-8, korrekte Umlaute) fuer beide Seiten."""
    out = []
    # Kopfzeile: auf allen Seiten
    out.append(_label(
        "LightOS Bühnen-Show  -  oben: FARB-PRESETS (immer da)  -  "
        "Bank ◀ ▶ oben schaltet:  Seite 1 = EFFEKTE   /   Seite 2 = FARBE/RGBW",
        20, 12, 1100, BANK_ALL, fg="#9DFF52"))
    # --- Effekt-Seite (Bank 1) ---
    out.append(_label(
        "EFFEKT-SEITE:  1) Farbe oben wählen   2) Dimmer-Effekt unten starten   "
        "3) Speed mit Fader F1-F4 regeln    -    'Clear' gibt die Farbe wieder frei",
        20, 44, 1100, BANK_FX))
    out.append(_label(
        "Matrix-Effekte (gold) bringen eigene Farben mit -> vorher 'Clear' drücken.   "
        "F6 = Dimmer (bis 0), F7 = Speed global, F8 = Matrix-Master, F9 = Master.",
        20, 66, 1100, BANK_FX))
    out.append(_label(
        "Fader unter dem Grid:  F1-F4 = Effekt-Speed (Lauf/Pulse/Wave/Strobe) - "
        "F5 = FX-Level - F6 = Dimmer - F7 = Speed global - F8 = Matrix - F9 = Master",
        20, 88, 1100, BANK_FX))
    # --- Farb-/RGBW-Seite (Bank 2) ---
    out.append(_label(
        "FARB-SEITE (RGBW):  Fader 1-4 mischen von Hand   Rot - Grün - Blau - Weiß.   "
        "Wirkt auf alle Strahler.",
        20, 44, 1100, BANK_RGBW, fg="#ffd0d0"))
    out.append(_label(
        "Zurück zur Effekt-Seite: Bank ◀ oben.   'Clear' (oben) setzt die Farbe "
        "zurück.   Helligkeit über F6 (Dimmer) oder F9 (Master).",
        20, 66, 1100, BANK_RGBW, fg="#ffd0d0"))
    out.append(_label(
        "↓  RGBW von Hand mischen  ↓",
        24, 712, 320, BANK_RGBW, h=24, fg="#ffffff", bg="#222222"))
    return out


def _rgbw_fader(caption, x, attr, cc, bg):
    return {
        "type": "VCSlider", "caption": caption, "bank": BANK_RGBW,
        "x": x, "y": 740, "w": 62, "h": 200, "bg": bg, "fg": "#ffffff",
        "mode": "Programmer", "function_id": None, "function_ids": [],
        "dmx_channel": 1, "dmx_universe": 1, "programmer_attr": attr,
        "value": 0, "midi_cc": cc, "midi_ch": 0,
    }


def _new_rgbw_faders():
    # Gleiche Positionen wie F1-F4 (Bank 1) -> ersetzen sie optisch auf Seite 2.
    return [
        _rgbw_fader("Rot",   24,  "color_r", 48, "#5a0000"),
        _rgbw_fader("Grün", 100, "color_g", 49, "#005a00"),
        _rgbw_fader("Blau",  176, "color_b", 50, "#00205a"),
        _rgbw_fader("Weiß", 252, "color_w", 51, "#404040"),
    ]


def main():
    with zipfile.ZipFile(SHOW, "r") as zf:
        data = json.loads(zf.read("show.json").decode("utf-8"))

    widgets = data["virtual_console"]["widgets"]

    # 1) Bestehende (Nicht-Label-)Widgets auf Banks verteilen.
    _set_bank(widgets)

    # 2) Alte (teils kaputte) Labels entfernen, neue saubere setzen.
    widgets = [w for w in widgets if w.get("type") != "VCLabel"]
    widgets.extend(_new_labels())

    # 3) RGBW-Fader fuer Seite 2 ergaenzen.
    widgets.extend(_new_rgbw_faders())

    data["virtual_console"]["widgets"] = widgets

    # 4) Zurueckschreiben (gleiche .lshow-Struktur: nur show.json im Zip).
    payload = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("show.json", payload)
    with open(SHOW, "wb") as f:
        f.write(buf.getvalue())

    # Kurzbericht
    from collections import Counter
    by_bank = Counter()
    for w in widgets:
        by_bank[w.get("bank")] += 1
    print(f"OK: {SHOW}")
    print(f"Widgets gesamt: {len(widgets)}")
    print(f"Bank-Verteilung (-1=alle, 0=Effekte, 1=RGBW): {dict(by_bank)}")
    sliders = [w for w in widgets if w.get("type") == "VCSlider"]
    print("Slider:")
    for s in sorted(sliders, key=lambda w: (w.get("bank"), w.get("midi_cc"))):
        print(f"  bank={s['bank']:>2}  cc={s.get('midi_cc')}  {s.get('mode'):<14} "
              f"{s.get('caption'):<10} attr={s.get('programmer_attr')}")


if __name__ == "__main__":
    main()
