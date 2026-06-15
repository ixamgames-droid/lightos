# Profi-Modus-Show — sektioniertes Quadranten-Layout (To-Do #11)

> **Show:** `shows/Profi_Modus.lshow` · **Generator:** `tools/build_profi_show.py`
> **Hardware:** Akai APC mini (mk2) + 4× PAR (ZQ01424) + 2× Moving Head (ZQ02001)

Die 8×8-Pads sind in vier **4×4-Quadranten** aufgeteilt — „einfach für Laien,
beliebig komplex für Profis".

```
┌───────────────┬───────────────┐
│  FARBEN 4x4   │  EFFEKTE 4x4  │   oben
│ (Programmer)  │ (exklusiv:    │
│               │  nur einer)   │
├───────────────┼───────────────┤
│ ATTRIBUTE 4x4 │ SONSTIGES 4x4 │   unten
│ (aktiver Efx) │ (Clear/Stop/…)│
└───────────────┴───────────────┘
```

## Quadranten

- **Oben links — FARBEN (16):** Farb-Kacheln, die die PARs im Programmer einfärben
  (mit Helligkeit). Mit einem laufenden Dimmer-Effekt kombinierbar → farbiges Lauflicht.
- **Oben rechts — EFFEKTE (16):** Dimmer-Chaser, Carousels, Color-Chase, RGB-Matrix-Looks,
  Moving-Head-EFX (Acht, Kreis, **Dreieck**, **Random**). **Exklusiv** — es läuft immer
  nur EINER (Tippen stoppt den vorigen).
  Farb-produzierende Effekte (Matrix/Color-Chase) räumen die Programmer-Farbe weg.
- **Unten links — ATTRIBUTE (16):** wirken auf den **gerade aktiven** (zuletzt gestarteten)
  Effekt: Form −/+, Farbe −/+, Richtung, Bounce, Freeze, Neustart, Spiegeln, Relativ,
  + Farbe, Farbe an/aus, Reset Live, Commit, Loop, Tap. Jeder Effekt reagiert auf die
  Aktionen, die er kann (die anderen ignoriert er).
- **Unten rechts — SONSTIGES (16):** Clear, Stop All, Blackout, Tap, Musik-BPM,
  Strobe-Flash, Weiß/Warm-Flash + Schnell-Looks (Rot/Grün/Blau/Amber/Cyan/Magenta/Warm/Weiß).

## Fader (unten) — passen sich dem aktiven Effekt an
- **F1 FX-Speed**, **F2 FX-Master**, **F3 FX-Param** wirken auf den **zuletzt gestarteten
  Effekt** (keine feste Bindung) → wechselt man den Effekt, regeln die Fader automatisch
  den neuen.
- **F4 PAR-Dim** dimmt fest die PAR-Gruppe (ohne Vorauswahl).
- **F6 Dimmer** (Submaster), **F7 Speed** (global), **F9 Master** (Grand Master).

## Bedien-Idee
- **Laie:** oben links eine Farbe, oben rechts einen Effekt tippen → läuft.
- **Profi:** Effekt starten → unten links live formen, unten die Fader feinjustieren.

---

*Self-verifizierend: `build_profi_show.py` assertet 16 Farb-Kacheln, exklusive Effekt-
Pads, 16 Attribut-Aktionen auf den aktiven Effekt, 3 kontext-adaptive Fader und den
Gruppen-Dimmer. Ergänzt die `Feature_Test.lshow` (gezieltes Feature-Testen) um eine
realistische Profi-Bedienfläche.*
