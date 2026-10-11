# Anleitung — Test-Show „Laser Gobo Test 2026"

> ⚠️ **Laser-Sicherheit — zuerst lesen.** Diese Show steuert **vier echte Laser**.
>
> - **Nie in den Strahl sehen und nie ins Publikum strahlen** — auch nicht „nur
>   kurz zum Testen". Laser so aufhängen und ausrichten, dass kein Strahl und
>   keine Reflexion (Spiegel, Glas, Chrom) in Augenhöhe von Menschen landet.
> - **Laserklasse prüfen:** Showlaser sind meist Klasse 3B oder 4 — schon ein
>   kurzer direkter Treffer kann das Auge dauerhaft schädigen. Die Klasse steht
>   auf dem Typenschild und im Handbuch des Geräts.
> - **Anmelde- und Abnahmepflicht:** Je nach Land und Laserklasse muss der
>   Betrieb vor Publikum angemeldet, von einer sachkundigen Person
>   (Laserschutzbeauftragte) betreut oder abgenommen werden. Das klärst du
>   **vor** der Veranstaltung mit der zuständigen Stelle — LightOS ersetzt
>   weder die Abnahme noch die Schutzeinrichtungen am Gerät (Schlüsselschalter,
>   Interlock).
> - **Erst den NOT-AUS anlegen, dann testen:** In der Virtuellen Konsole eine
>   Taste mit der Aktion **„Laser NOT-AUS"** anlegen (am besten zusätzlich auf
>   ein Controller-Pad legen) und **einmal auslösen**, bevor der erste Laser
>   läuft. So weißt du, dass sie wirkt und wo sie liegt.

### Was macht den Laser sicher aus?

Alle vier Wege senden an den Laser den **Aus-Wert aus dem Geräteprofil** (z. B.
Betriebsart „Laser aus") — nicht einfach DMX 0, denn bei manchen Lasern bedeutet
0 „Automatik".

| Weg | Wirkt auf | Besonderheit |
|---|---|---|
| **Blackout** | alle Laser (und alles andere Licht) | Aus-Wert des Profils an jeden Laser. |
| **Grand Master 0 %** | alle Laser | Laser ohne Dimmer lassen sich nicht stufenlos dimmen — bei 0 % bekommen sie den Aus-Wert, darüber laufen sie unverändert. |
| **Ziel-Blackout** (Blackout-Taste mit Ziel) | nur die Laser im Ziel | Alle anderen Laser laufen weiter. |
| **Laser-NOT-AUS** | alle Laser | Gewinnt immer — auch gegen Grand Master, Blackout und Kanal-Modifier. Schreibt zusätzlich 0 an Laser-Adressen, für die das Profil keinen Aus-Wert kennt. |

Kennt ein Geräteprofil **keinen** Aus-Wert, kann der Laser bei Blackout und
Grand Master 0 % weiterstrahlen — **verlässlich ist nur der Laser-NOT-AUS** (und
der Schalter am Gerät). Einzelheiten:
[Laser bedienen → Blackout, Ziel-Blackout und NOT-AUS](anleitung_laser/ANLEITUNG_LASER.md#blackout-ziel-blackout-und-not-aus).

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
   - Kopie liegt im App-Datenordner unter `shows/` (Windows `%APPDATA%\LightOS\shows\`,
     Linux `~/.local/share/LightOS/shows/`) und erscheint direkt im Dialog.
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
  Betriebsart (Aus/An), Musterbank (0-223, Bänke 1-14), Farbrad (0-31 = „Vollfarbe"; „Cyan" liegt bei 128-159),
  Bewegung/Speed. Werte reagieren live.
- **Gobo-Steuerung** (Gobo-MH wählen → Programmer → Tab **Gobo**): visuelle Gobo-Kacheln
  „Kein Gobo / Gobo 1…7", Gobo-Wechsel-Slider (langsam→schnell), Gobo-Rotation. Ein Klick
  auf „Gobo 3" setzt den Kanal in den Bereich 48-63.

## Wie gebaut

Struktur per Generator (`tools/build_laser_gobo_test.py`, auf `tools/_builder.py`),
NUR echte Widgets/Params. **Show-Lint `--strict`: 0 Fehler, 0 Warnungen.**
Danach live per Computer-Use durch alle UI-Bereiche geprüft.

> Show-Datei (`.lshow`) ist git-ignoriert (lokal); reproduzierbar über den Generator.
