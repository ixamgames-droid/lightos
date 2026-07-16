# Anleitung — Test-Show „Laser Gobo Test 2026"

Eine komplette Test-Show mit **Laser + Gobo-Moving-Heads + PARs + Nebel**, gebaut am
2026-07-16, damit sich Laser-, Gobo- und Moving-Head-Steuerung + Farbe/Bewegung/Dimmer
+ Nebel alle an einem Rig prüfen lassen. Live per Computer-Use verifiziert.

## Was drin ist (18 Fixtures, 2 Universen)

| Anzahl | Gerät | Kürzel / Modus | Zweck |
|---|---|---|---|
| 8 | PAR | `ZQ01424`, 8-Kanal RGBW (U1) | Farbe/Dimmer/Matrix |
| 4 | Moving Head **mit Gobos** | `MH16`, 16-Kanal (U1) | Pan/Tilt-Bewegung, Farbrad, **Gobo-Rad (Kanal 9)** |
| 4 | Laser | `L2600LASER` (Ehaho L2600), 6-Kanal Simple DMX (U2) | Laser-Panel: Betriebsart/Muster/Farbe/Bewegung |
| 2 | Nebelmaschine | `EURON10`, 1-Kanal (U2) | Smoke/Hazer |

**Gruppen:** PARs · Moving Heads (Gobo) · Laser · Nebel.

**Effekte / Funktionen (in der Virtuellen Konsole als Buttons):**
- **MH Licht an** — Mover-Intensität voll (damit Bewegung/Gobo sichtbar ist).
- **MH Kreis** — Pan/Tilt-Kreisbewegung (EFX).
- **MH Gobo** — zyklt das Gobo-Rad durch Gobo 1/3/5/7 (Chaser).
- **MH Farbrad** — zyklt das Farb-Rad der Mover (Chaser; MH16 hat KEIN RGB → Rad, kein Matrix-Effekt).
- **PAR Rainbow / PAR Chase** — RGB-Matrix-Effekte über die PARs.
- **PAR Lauflicht** — Dimmer-Lauflicht (Chaser).
- **Nebel an** — beide Hazer voll auf.

**VC-Bedienelemente:** Master-Fader (Grand Master), MH-Speed-Fader, MH-Tempo-SpeedDial,
BLACKOUT. Solo-freundlich aufgebaut (kein globales `stop_all`).

**Rig (2D + 3D):** Front-/Back-Traverse auf 4 Stützen über einer Bühnen-Plattform.
PARs unten an der Front-Traverse, Gobo-MHs + Laser an der Back-Traverse, Nebelmaschinen
am Boden vorne links/rechts.

## Laden

1. **Datei → Öffnen** → Show `Laser Gobo Test 2026.lshow` wählen.
   - Kopie liegt in `%APPDATA%\LightOS\shows\` (erscheint direkt im Dialog).
   - Original + Generator im Repo: `shows/Laser Gobo Test 2026.lshow` bzw. `tools/build_laser_gobo_test.py`.
2. Titel zeigt „Show 'Laser Gobo Test 2026' geladen.", Statusleiste „18 Gerät(e)".

## Prüfen (was live verifiziert wurde)

- **Darstellung 2D** (Bühne-Tab, „2D"): alle Geräte mit lesbaren Labels (MH/LSR/PAR/FOG),
  Layout wie oben. „⤢ Einpassen" zoomt auf die Geräte.
- **Darstellung 3D** (Bühne-Tab, „3D"): das Rig mit **persistenten Namensschildern** an
  jedem Gerät (`#<Nr> <Name>`) und dem permanenten **Modus-Rahmen**: dezent in *Ansehen*,
  orange „BAUEN · Fixtures" mit Bau-Werkzeugen in *Bauen*.
- **Virtuelle Konsole:** plastische Buttons/Fader/SpeedDial; Effekt-Buttons triggern
  (aktive Buttons leuchten auf, oben „Aktiver Effekt: …").
- **Laser-Steuerung** (Gerät wählen → Programmer → Tab **Laser**): Klartext-Bereiche
  Betriebsart (Aus/An), Musterbank (0-223, Bänke 1-14), Farbrad (0-31, z. B. „Cyan"),
  Bewegung/Speed. Werte reagieren live.
- **Gobo-Steuerung** (Gobo-MH wählen → Programmer → Tab **Gobo**): visuelle Gobo-Kacheln
  „Kein Gobo / Gobo 1…7", Gobo-Wechsel-Slider (langsam→schnell), Gobo-Rotation. Ein Klick
  auf „Gobo 3" setzt den Kanal in den Bereich 48-63.

## Wie gebaut

Struktur per Generator (`tools/build_laser_gobo_test.py`, auf `tools/_builder.py`),
NUR echte Widgets/Params. **Show-Lint `--strict`: 0 Fehler, 0 Warnungen.**
Danach live per Computer-Use durch alle UI-Bereiche geprüft.

> Show-Datei (`.lshow`) ist git-ignoriert (lokal); reproduzierbar über den Generator.
