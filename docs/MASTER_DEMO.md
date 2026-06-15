# Master-Demo-Show — „alles, was die Show kann"

> **Show:** `shows/Master_Demo.lshow` · **Generator:** `tools/build_master_demo_show.py`
> **Hardware:** Akai APC mini (mk2) + 4× PAR (ZQ01424) + 2× Moving Head (ZQ02001)

Die große Gesamt-Demo: nutzt das **Multi-Konsolen-/Bank-System** (APC-SCENE-Tasten
rechts = Seite 1–5) und führt alle neuen **Virtual-Console-Fenster-Widgets** vor
(Chase-Liste, Chase-Builder, XY-Pad), plus die neuen Live-Funktionen.

Universell: Track-Tasten **Clear · Stop All · Blackout · Tap**; Fader **F6** Dimmer
(Submaster), **F7** Speed global, **F9** Grand Master.

## Seite 1 — Farben & Gruppen
- **Reihe 1:** 8 Farb-Kacheln (Programmer) für die PARs.
- **Pads „Gr: …":** wählen eine **Gruppe** in den Programmer (PARs / MHs / Alle) — **F-24**.
- **F1 „PAR-Dim" / F2 „MH-Dim":** Gruppen-Dimmer-Fader (multiplikativ) — **F-25**.

## Seite 2 — Effekte
16 Effekte als **exklusive** Pads (nur einer läuft): Dimmer-Chaser (Lauflicht,
Ping-Pong, 2er, Strobe, Build-Up), Carousels (Pulse/Wave), Color-Chase,
RGB-Matrix (Regenbogen/Feuer/Plasma), Moving-Head-EFX (Acht, Kreis, **Dreieck**,
**Random**).

## Seite 3 — Matrix Builder
EINE Matrix; **Form −/+** blättert durch ALLE Algorithmen, **Richtung/Freeze/Commit**,
**Recolor** (color1 + Sequence-Farbe), Fader Speed/Master. **Rechts:** das
**Feedback-Fenster** (`VCColorList`) zeigt die Color-Sequence live.

## Seite 4 — Chase Builder
Das **All-in-One-Chase-Builder-Fenster** (`VCChaseBuilder`): Farb-Palette antippen =
anhängen, gebaute Liste, Aktions-Buttons (Start/Clear/C−/C+/Richtung/Freeze/Commit)
und Speed/Hold-Slider — alles in EINEM Widget.

## Seite 5 — Moving Heads
- **Links „MH zielen" (XY-Pad):** PAN/TILT live fahren.
- **„Relativ" + „MH Acht relativ":** die Acht läuft relativ um die gezielte Position (**#7**).
- **Rechts „Feld → Kreis" (XY-Pad, Feld-Modus):** ein Rechteck aufziehen → „MH Kreis
  Feld" fährt im markierten Bereich (**#8**). Nach neuem Zielen „Neustart".

---

*Self-verifizierend: `build_master_demo_show.py` assertet 5 Banks, je 1×
VCColorList/VCChaseBuilder, 2× VCXYPad, 3× SELECT_GROUP-Pads, 2× GROUP_DIMMER-Fader
und die 15 exklusiven Effekte (inkl. Dreieck/Random). Ergänzt `Feature_Test.lshow`
(gezieltes Feature-Testen) und `Profi_Modus.lshow` (Quadranten-Bedienfläche).*
