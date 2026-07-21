# 3D-Visualizer: Bühne bauen & Fixtures hängen (Session 2026-07-07)

Diese Anleitung zeigt **Schritt für Schritt**, wie im LightOS-3D-Visualizer eine Bühne
gebaut wird (Trassen, Stützen, Plattform) und wie Fixtures daran gehängt werden —
seitlich, unten und oben. Sie entstand beim Live-Durchspielen der Demo-Show
`shows/demo_komplett_2026.lshow` (Demo-Show, selbst aufzubauen — nicht mitgeliefert).

> **Wichtiger Kontext — der 3D-Bearbeiten-Fix:** Bis 2026-07-07 war das Bearbeiten im 3D
> komplett tot (Hinzufügen/Verschieben/Drehen/Kamera-Reset reagierten nicht, Fixtures
> luden nur beim Neustart). Ursache: QtWebEngine stellte Python→JS-Signale an die
> eingebettete Seite nicht zu. Fix (Branch `fix/viz3d-qwebchannel-pull-delivery`): die
> JS-Seite **pollt** jetzt periodisch `pollControl()` und wendet Zustand + Events an —
> inkl. der Fixture-Meshes (`allFixtures`/`fixtureAdded`/`fixtureRemoved`). Seither
> funktionieren Hinzufügen, Verschieben, Bearbeiten und Live-Platzieren sofort sichtbar.

## Vorbereitung
1. Show mit gepatchten Fixtures öffnen (hier: 8 PAR ZQ01424, 2 MH ZQ02001, 2 Spider
   SPIDER14, 1 Laser Ehaho L2600 = 13 Geräte).
2. Menü **Visualizer → 3D Visualizer öffnen**. Alle gepatchten Fixtures erscheinen als
   Liste rechts (Tab **Fixtures**) und werden — dank Auto-Patch aus der 2D-Live-View —
   direkt im Raum gerendert (Statuszeile unten: „N Fixture(s) in Szene").

## Teil A — Bühne/Trassen bauen (Tab „Bühne")
Der Tab **Bühne** schaltet den **Modus** automatisch auf „Bühne bearbeiten" (gelbes
Banner „BÜHNE BEARBEITEN — Tippen=Auswählen | Ziehen=Verschieben"). Unter
**„Element hinzufügen"** stehen: Boden/Floor · Plattform · Truss (horizontal) ·
Truss/Stütze (vertikal) · Wand · LED-Wand · Lautsprecher · Publikumsfläche · DJ-Booth.

1. **Plattform (Bühnenboden):** „**+ Plattform**" → eine Bühnenfläche erscheint mittig
   (Default 6×0,4×4 m). Sie ist sofort in der Szene sichtbar und in der Tabelle
   „Bühnen-Elemente" gelistet.
2. **Trasse:** „**+ Truss (horizontal)**" legt eine Trasse an (Default 4 m breit, Höhe
   Y=8). Auswählen → im **„Eigenschaften (Selektion)"**-Panel positionieren.
3. **Positionieren (zuverlässig über Zahlenfelder):** Feld anklicken → `Strg+A` → Wert
   tippen → **TAB** (committet + springt ins nächste Feld). Beispiel Front-Trasse:
   `X=0`, `Y=6`, `Z=-2`, `Breite=8`. Zweite Trasse für hinten analog mit `Z=+2`.
   > **Fallen (siehe BACKLOG VIZ-STAGE-PANEL):** ENTER committet NICHT — immer **TAB**
   > benutzen. Der „Größe anpassen"-Modus sperrt die Größen-Felder (dann klemmen
   > Breite/Höhe) → vor dem Tippen ausschalten. Weicht die Panel-Auswahl von der Szene
   > ab, das Element **in der Szene anklicken** — das re-synchronisiert.
4. **Verschieben per Maus:** Trasse in der Szene anfassen und ziehen — sie bewegt sich in
   der Bodenebene (X/Z ändern sich, Panel aktualisiert live). Präzise Höhe (Y) besser
   über das Zahlenfeld.
5. **Trassen verbinden / Stützen:** „**+ Truss/Stütze (vertikal)**" für senkrechte
   Stützen (Default 4 m hoch). Über `X`/`Z` an eine Trassen-Ecke setzen (z. B. `X=-4`,
   `Z=-2`) → ergibt ein „Goalpost"-Gerüst.

## Teil B — Fixtures an die Trassen hängen (Tab „Fixtures")
Der Tab **Fixtures** schaltet den Modus auf „Fixtures bearbeiten". Jede Zeile hat einen
Status: `[ ]` = nicht in Szene, `[X]` = platziert.

1. **Platzieren:** Fixture in der Liste wählen → **„Im Raum platzieren"** → der Mesh
   erscheint **sofort** in der Szene (dank Fix). Mit **„Entfernen"** verschwindet er
   sofort wieder.
2. **Hängen (unten/oben/seitlich)** über „Position & Ausrichtung":
   - **Unten an die Trasse (bottom-hung):** `Y` knapp unter die Trassen-Höhe (Trasse
     Y=6 → Fixture `Y=5`), `Z` = Trassen-Z, `X` entlang der Trasse verteilen.
   - **Oben auf die Trasse (top-mount):** `Y` knapp über die Trasse (z. B. `Y=6.5`).
   - **Seitlich:** an eine vertikale Stütze setzen (Stützen-`X`/`Z`, mittlere `Y`) und
     mit **Drehen (Hochachse Y)** zur Seite ausrichten.
   > **Hinweis (Fix VIZ-FIX-DECIMAL erledigt):** Die Positions-/Ausrichtungsfelder akzeptieren
   > Punkt UND Komma — „5.7" und „5,7" werden beide korrekt als 5,7 übernommen.
3. **Ausrichten:** **Drehen (Hochachse Y)** / **Kippen (auf/ab X)** / **Roll (seitlich Z)**
   je Fixture; Moving Heads folgen zusätzlich ihren Pan/Tilt-DMX-Werten live.

## Teil C — Speichern
- **Bühne** (Trassen/Plattform) über den **„Speichern"**-Button in der Visualizer-Toolbar
  (fragt beim Schließen „Bühne speichern?" nach).
- **Show** (Fixtures, Positionen, Gruppen, Effekte, VC) im Hauptfenster über
  **Datei → Speichern** bzw. **Speichern unter…**.

## Verifikation
- **Lint-Gate:** `./venv/Scripts/python.exe tools/lint_show.py --strict <show>.lshow`
  muss „0 Fehler, 0 Warnungen" melden (nur echte Widgets/Enums/Params). ✅ für
  `demo_komplett_2026.lshow`.
- **Live geprüft:** Stage-Elemente hinzufügen/verschieben/bearbeiten, Modus-Wechsel,
  Kamera-Reset und Fixture-Platzieren/-Entfernen sind sofort in der Szene sichtbar.

## Bekannte offene Punkte (im BACKLOG erfasst)
- **VIZ-TRUSS-ADD:** „+ Truss" legt bei bereits geladenen Fixtures manchmal kein Element
  an (Plattform/Boden gehen; Truss lädt async ein OBJ-Modell). Workaround: erneut
  versuchen / Szene neu laden; Nagelung per CDP offen.
- **VIZ-STAGE-PANEL:** ENTER committet nicht (TAB nutzen); Größen-Felder unter „Größe
  anpassen" gesperrt; gelegentliche Panel↔Szene-Selektions-Desync.
- **VC-WIDGET-DRAG:** VC-Widgets lassen sich (noch) nicht per Drag umplatzieren.

Die überlappenden Grundschritte (Patch, Gruppen, Farb-/Dimmer-/EFX-Effekte, Virtuelle
Konsole) sind bereits bebildert in
[`../anleitung_komplettshow_2026/ANLEITUNGEN.md`](../anleitung_komplettshow_2026/ANLEITUNGEN.md).
