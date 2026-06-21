# Komplettshow 2026 — Bebilderte Einzelanleitungen

Diese Sammlung zeigt **Schritt für Schritt**, wie die komplette Show
[`shows/Komplettshow_2026.lshow`](../../shows/Komplettshow_2026.lshow) von Grund auf in LightOS
gebaut wurde — jeweils mit echten Screenshots (und einem GIF des laufenden Effekts). Jede
Anleitung steht für sich und hat ein klares Lernziel.

## Das Rig dieser Show
- **8 PAR** (Generic Stage Light **ZQ01424**, 8ch RGBW) — Adressen 1, 9, 17, 25, 33, 41, 49, 57
- **2 Moving Heads** (U King **ZQ02001**, 11ch) — MH 1 @65, MH 2 @76
- **2 Spider** (U King **Spider 14ch** / „SPIDER14", Flower mit 2 Tilt-Bars + RGBW) — @87, @101
- **Layout (Top-Down):** PAR-Reihe mittig · MH hinter PAR 1 und PAR 8 · Spider vor PAR 2 und PAR 6

## Die Anleitungen (in Reihenfolge)
1. [Neue Show anlegen & benennen](00_grundlagen/ANLEITUNG.md)
2. [Fixtures anlegen (Patchen)](01_fixtures/ANLEITUNG.md)
3. [Positionen in 2D-Live-View & 3D-Visualizer](02_positionen_3d/ANLEITUNG.md)
4. [Fixture-Gruppen anlegen (PAR/MH/Spider)](03_gruppen/ANLEITUNG.md)
5. [Coloreffekte über den Color-Tab — **nur die Farbe speichern**](04_coloreffekt/ANLEITUNG.md) ⭐
6. [Matrix-/Dimmereffekte — **Farbe + Dimmer mischen**](05_matrix_dimmer/ANLEITUNG.md) ⭐ (mit GIF)
7. [EFX-Bewegung für Moving Heads (und warum Spider anders sind)](06_efx_bewegung/ANLEITUNG.md)
8. [Virtuelle Konsole bauen & Effekte/MH steuern (+ APC Mini)](07_virtuelle_konsole/ANLEITUNG.md)

## Zwei zentrale Lehren (deine Fragen)
- **„Color speichert meine Dimmer-Schnitte mit"** → gelöst in Anleitung 5: Der Programmer merkt
  sich jeden angefassten Kanal; im Speicher-Dialog **„Kanäle auswählen"** die Gruppe
  **Intensity/Dimmer abhaken** → es wird nur die Farbe gespeichert. Vorher **Clear** drücken.
- **„Alles rot + Dimmer-Matrix soll ablaufen"** → Anleitung 6: Farbe als eigene **RGB-Matrix**
  und Helligkeit als eigene **Dimmer-Matrix** über dieselben Geräte legen — beide schreiben
  unterschiedliche Kanäle und überlagern sich sauber (rotes Lauflicht).

## Stand / noch offen
- ✅ Patch, Positionen, Gruppen, Color-Looks, PAR-Mix (Farbe×Dimmer), MH-Bewegung+Steuerung,
  Virtuelle Konsole (live getestet) — alle gebaut & gespeichert.
- ⏳ **Spider Auto-Tilt-Chase** (die Spider sind Tilt-Flower ohne Pan → keine EFX-Figuren;
  Bewegung = Tilt-Bars per Chaser/Position) und **APC-Mini-Pad-Belegung** (das Drücken der Pads
  beim „MIDI Lernen" erfolgt an der Hardware) — als nächster Schritt vorgesehen.
