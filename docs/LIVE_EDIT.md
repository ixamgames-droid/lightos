# Live-Edit-Show — vordefinierte Effekte live einmappen & bearbeiten

> **Show:** `shows/Live_Edit.lshow` · **Generator:** `tools/build_live_edit_show.py`
> **Hardware:** Akai APC mini (mk2) + 4× PAR (ZQ01424) + 2× Moving Head (ZQ02001)

Umsetzung von Davids Wunsch **„Live-Bearbeitung statt Live-Programming"**: die APC
ist in **vier 4×4-Quadranten** geteilt. In jedem Quadrant wählt man oben einen
**vordefinierten, laufenden** Effekt; die Aktionen, Farben und Fader desselben
Quadranten **bearbeiten dann genau diesen Effekt** — pro Quadrant unabhängig.

## Die Mechanik: Edit-Slots
Ein Effekt-Wahl-Pad trägt einen **Edit-Slot** (z. B. „MH" oder „MX"). Beim Drücken:
- startet es den Effekt,
- stoppt den vorher in DIESEM Slot laufenden Effekt (pro Slot exklusiv — andere
  Slots/Quadranten laufen weiter),
- macht den Effekt zum **aktiven Bearbeitungsziel** des Slots.

Fader, Farb-Kacheln und Aktions-Tasten mit demselben Edit-Slot wirken dann auf
genau dieses Slot-Ziel (statt auf den „global zuletzt gestarteten" Effekt).
Technik: `effect_live.set_edit_target/get_edit_target`; VCButton/VCSlider/VCColor
haben ein `edit_slot`-Feld.

## Quadranten
- **Oben links — MOVING HEADS (Slot „MH"):**
  Reihe 1 = Effekt wählen (Acht/Kreis/Dreieck/Random) · Reihe 2 = Aktionen
  (Richtung/Bounce/Relativ/Neustart) · Reihe 3+4 = Looks (Position + Farbrad/Gobo).
- **Oben rechts — MATRIX (Slot „MX"):**
  Reihe 1 = Effekt wählen (Chase/Color-Fade/Feuer/Plasma) · Reihe 2 = Form −/+ ·
  Freeze · Reset · Reihe 3 = **color1**-Recolor · Reihe 4 = **Sequence**-Farbe.
- **Unten links:** 8 PAR-Farben (Programmer) + Gruppe-auswählen-Pads.
- **Unten rechts:** **Strobo-Overlay** (eigene Dimmer-Ebene über die Farb-Matrix) + Blackout.

## Fader (unten)
- **F1 MH-Speed**, **F2 MH-Größe** → bearbeiten den Effekt im Slot „MH".
- **F4 MX-Speed**, **F5 MX-Master**, **F6 MX-Param (Weiß/Hold)** → Slot „MX".
- **F8 Dimmer** (Submaster), **F9 Master** (Grand Master).

## Bedien-Idee
1. Oben links einen MH-Effekt antippen → läuft, ist „MH"-Edit-Ziel.
2. Mit F1/F2 Tempo/Größe live formen, Reihe-2-Tasten für Richtung/Relativ.
3. Oben rechts eine Matrix antippen → läuft unabhängig, ist „MX"-Edit-Ziel.
4. Mit den C1/Sequence-Kacheln live umfärben, F4–F6 Tempo/Helligkeit/Parameter,
   Form −/+ blättert die Matrix-Algorithmen.
5. „Strobo-Overlay" legt ein Stroboskop über die laufende Matrix.

---

*Self-verifizierend: `build_live_edit_show.py` assertet je 4 Effekt-Wahl-Pads pro
Slot, 4+4 Aktions-Pads, 8 Recolor-Kacheln (MX), 5 Edit-Fader und das Strobe-Overlay.
Ergänzt `Feature_Test.lshow`, `Profi_Modus.lshow`, `Master_Demo.lshow`.*
