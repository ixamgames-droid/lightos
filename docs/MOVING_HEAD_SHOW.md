# Moving-Head-Demo-Show

`shows/MovingHead_Demo.lshow` — Leit-Demo der Moving-Head-Initiative.
Generator: `tools/build_movinghead_show.py` (self-verifizierend, headless).

## Bühnenbild / Patch

| FID | Gerät | Profil / Mode | Universe / DMX |
|-----|-------|---------------|----------------|
| 1–4 | PAR (Mitte) | Generic ZQ01424, 8-Kanal RGBW | U1 / 1, 9, 17, 25 |
| 5 | MH Links | U King ZQ02001, 11-Kanal | U1 / 33 |
| 6 | MH Rechts | U King ZQ02001, 11-Kanal | U1 / 44 |

Gruppen (in der `.lshow` persistiert): **PAR-Reihe** (4×1), **Moving Heads** (2×1).

## APC mini / Virtual Console (5 Seiten, Scene-Tasten rechts)

1. **PAR-Farben** — Farb-Kacheln (sofort sichtbar via base_levels) + Looks.
2. **Dimmer/Matrix** — PAR-Lauflicht + RGB-Matrix (Regenbogen/Chase) auf der PAR-Reihe.
3. **MH-Bewegung** — Pan/Tilt-EFX auf der MH-Gruppe: Kreis (Fan), Acht, Sweep gespiegelt, Bounce. `open_beam` öffnet Dimmer+Shutter automatisch → Strahler sichtbar. EFX-Speed-Fader.
4. **MH Gobo/Farbe** — Gobo-Schnellwahl (Offen/1–3/Rotation) + Farbrad (Weiß/Rot/Grün/Blau/Gelb).
5. **MH Position** — Position-Presets (Center/Publikum/Hoch/Cross) + Shutter Auf/Strobe.

Universell auf jeder Seite: Clear / Stop / Blackout / Tap, Dimmer-/Speed-/Master-Fader.

## Verifiziert (headless, im Build + Render)

- EFX bewegt **beide** Moving Heads (Fan-Versatz: linker/rechter Kopf in unterschiedlicher Phase), Dimmer=255, Shutter im Open-Bereich.
- Gobo-/Farbrad-/Shutter-Szenen setzen exakt die ZQ02001-Kanäle (color_wheel/gobo_wheel/shutter) — d. h. die VC-Tasten geben sie korrekt wieder.
- Save→Load-Roundtrip erhält EFX-Felder (`open_beam`/`spread`/`mirror`) und die Fixture-Gruppen.

## Selbst testen

```
venv\Scripts\python.exe tools\build_movinghead_show.py
```
Dann in LightOS laden, im Programmer die Gruppe **Moving Heads** wählen → Reiter **EFX** (folgt der Auswahl) → eine Bewegung starten; **Gobo**-Tab erscheint automatisch; **Position**-Tab hat Pan/Tilt-Pad (Live) + Invert/Swap-Toggles.
