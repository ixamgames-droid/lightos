# Programmer basics: select fixtures and set them by hand

> **English version** of [Programmer-Grundlagen](ANLEITUNG.md). LightOS itself speaks
> German: every button, tab and field is quoted here **exactly as it appears on screen**,
> with an English translation in brackets the first time it shows up. The screenshots are
> the same as in the German guide.

> **What it is about:** In the **Programmer** you set light by hand. You select fixtures,
> bring up brightness, colour and position and see the result immediately. Whatever is in
> the Programmer takes priority over running scenes and cues until you clear it again.
> This page explains how to operate it step by step. Which extra buttons and faders a
> particular fixture gets (strobe, programmes, multi-head, fog, laser) is covered in depth
> in [Programmer: jedes Gerät richtig bedienen](../anleitung_geraete_bedienen/ANLEITUNG_GERAETE_BEDIENEN.md)
> (German).

From the Programmer state you then make scenes, snaps and cues. How that works is
described in [Szenen, Snaps & Cue-Listen](../anleitung_szenen_cues/ANLEITUNG.md) (German).

---

## What you need

- A show with patched fixtures and a few groups. How to do that is described in
  [Patchen & Fixture-Gruppen](../anleitung_patch_gruppen/ANLEITUNG_PATCH_GRUPPEN.md)
  (German).
- The pictures show a small practice show. It consists only of the built-in profiles of
  the manufacturer **Generic**. To rebuild it, patch in **Patchen → Patch** (patch) with
  **+ Gerät hinzufügen** (add fixture):

  | Fixtures | Profile (Generic) | Mode | Addresses |
  |---|---|---|---|
  | PAR 1–8 | LED PAR Dimmer+RGB 4ch | 4-Kanal Dimmer+RGB | 1, 5, 9 … 29 |
  | Wash 1–2 | Moving Head Wash RGB 7ch | 7-Kanal | 41, 48 |
  | Spot 1–2 | Moving Head Spot 8ch | 8-Kanal | 61, 69 |
  | LED-Leiste | LED Bar 12ch | 12-Kanal (4x RGB) | 81 |

  Plus the groups **Alle PAR** (all PARs), **PAR links** (PAR 1–4, left), **PAR rechts**
  (PAR 5–8, right) and **Moving Heads** (Wash 1–2, Spot 1–2) under
  **Patchen → Fixture-Gruppen** (fixture groups). LightOS does not currently ship a
  finished file of this show. Everything works the same with your own fixtures.
- Without a connected interface you see the result in the **Lampen-Vorschau** (lamp
  preview) at the bottom of the Programmer and in the **Bühne** (stage) section.

---

## 1. The Programmer at a glance

![Programmer without a selection](img/01_ueberblick.png)

Click **Programmer** in the section bar at the top, then the tab **Attribute**
(attributes). The window has three columns:

1. **Geräte** (fixtures): all patched fixtures, `[001] PAR 1` and so on.
2. **Alle** (all): selects all fixtures in the list.
3. **Keine** (none): clears the selection.
4. **Gruppen** (groups): your fixture groups, with the search field „Gruppe suchen…“
   (search group).
5. **The tab bar** in the middle: as long as nothing is selected, it says
   „Kein Gerät ausgewählt — links ein Gerät oder eine Gruppe wählen“ (no fixture selected
   — pick a fixture or a group on the left). Which tabs exist depends on the selection
   (step 6).
6. **Bibliothek** (library) on the right: saved snaps and functions (scenes, chasers,
   matrix, EFX). More on that in [Szenen, Snaps & Cue-Listen](../anleitung_szenen_cues/ANLEITUNG.md)
   (German).

Above it is the toolbar with **Hervorheben** (highlight), **Abdunkeln** (dim others),
**Löschen** (clear), **Kopieren** (copy), **Einfügen** (paste), **Rückgängig** (undo),
**Wiederholen** (redo) and the three tools **Farb-Werkzeug...** (colour tool),
**Positions-Werkzeug...** (position tool) and **Fächer...** (fan). At the top right,
**Layout: Zonen** switches to the classic layout (the button then reads
**Layout: Klassisch**). **?** starts the help mode: the next click on a button shows its
explanation instead of triggering it. **Esc** ends it.

## 2. Selecting fixtures: list and groups

![Click on the group "PAR links"](img/02_gruppe.png)

- **In the list** you click a fixture. With **Strg** (Ctrl) you add more, with
  **Umschalt** (Shift) a whole range. Fixtures with several heads have an arrow: expanded,
  you can select individual heads.
- **Clicking a group (1)**: the selection is replaced by the fixtures of the group (2), in
  the group's order. At the same time the Programmer jumps to the **Matrix** tab (3) and
  shows the matrices of that group. For colour or brightness, click **Color** or
  **Intensity** afterwards.
- **Double-clicking a group**: the fixtures of the group are added to the existing
  selection. The hint below the list says the same: „Klick = Gruppe wählen · Doppelklick
  = zur Auswahl addieren“ (click = select group · double-click = add to selection).

The order of the selection matters later, for example for the fan (step 10).

## 3. Brightness: the Intensity tab

![Intensity tab with eight PARs](img/03_intensity.png)

Select **Alle PAR**, then the **Intensity** tab.

1. The line at the top names the selection, here „8 Gerät(e): [1] PAR 1, [2] PAR 2 …“
   (8 fixtures). Below it a colour bar shows the current mixed colour.
2. **Gruppe:** (group mode) decides how one fader acts on several fixtures:
   - **Verknüpft** (linked): all fixtures get the same value.
   - **Einzeln** (individual): only the fixture in the selection box to the right
     changes.
   - **Relativ** (relative): all values move by the same amount; the differences between
     the fixtures are kept.
3. **Intensity**: the tab for brightness (and shutter/strobe, if the fixture has such a
   channel).
4. **Dimmer**: a fader from 0 to 255, next to it the value and the percentage. The small
   button at the far right of the fader (tooltip „Auf Standard zurücksetzen“ = reset to
   default) restores the profile's default value.
5. **Lampen-Vorschau** (lamp preview): one tile per selected fixture, in the colour it is
   currently putting out. An RGB PAR with a full dimmer but no colour stays dark here, just
   like the real fixture; only fixtures without a colour channel (plain dimmers) light up
   white. The arrow collapses and expands it.

As soon as a value is in the Programmer, the header at the very top shows
„● Programmer *n*“: that is how many values (fixture × channel) the Programmer currently
holds — in the picture 8 dimmer values.

## 4. Colour: the Color tab

![Color tab with eight PARs](img/04_color.png)

1. **Color Picker (Fenster)** (window) opens the colour picker as a separate window you can
   move freely. The Programmer stays usable next to it.
2. **Schnellwahl** (quick select): one click on **Weiß**, **Rot**, **Orange**, **Gelb**,
   **Grün**, **Cyan**, **Blau**, **Violett** or **Magenta** (white, red, orange, yellow,
   green, cyan, blue, violet, magenta) sets that colour on all selected fixtures. **Aus**
   (off) removes the colour (all colour channels to 0).
3. **Rot**, **Grün**, **Blau**: one fader per colour channel. More channels such as white,
   amber or UV appear when the fixtures have them.

**Fächern: Farbe...** (fan: colour; left of 1) opens the fan tool with „Rot“ preset
(step 10). Every attribute tab has such a button.

## 5. Movement: the Position tab

![Position tab with two spots](img/05_position.png)

The **Position (1)** tab only exists if the selection has pan/tilt, i.e. with moving
heads. Here you select **Spot 1** and **Spot 2**. The tab contains:

- **Ausrichtung (pro Fixture)** (orientation per fixture) with **Pan invertieren** (invert
  pan), **Tilt invertieren** (invert tilt) and **Pan/Tilt tauschen** (swap pan/tilt). These
  checkboxes change the fixture in the patch, not the Programmer. That is why they can only
  be undone via **Bearbeiten → Rückgängig** (Edit → Undo, **Strg+Z**), not with the
  **Rückgängig** button in the Programmer.
- **Pan/Tilt-Speed:** with the **Speed** fader, if the fixture has such a channel.
- **Position-Tool (XY-Pad)**: an expandable pad to drag.
- The **Pan** and **Tilt** faders.

With moving heads in the selection the tabs **Mapping** and **EFX** (movement effects, see
[EFX](../anleitung_efx/ANLEITUNG_EFX.md), German) appear as well.

## 6. The other tabs

The tab bar only shows what fits the selection. Without a selection it shows
**Intensity**, **Color**, **Weitere** (more), **Assistent** (assistant), **Matrix** and
**Paletten** (palettes).

| Tab | When visible | Contents |
|---|---|---|
| **Intensity** | always | dimmer, shutter/strobe |
| **Color** | selection has colour channels | quick select, colour faders |
| **Position** | selection has pan/tilt | see step 5 |
| **Gobo** | selection has a gobo wheel | gobo tiles, rotation |
| **Weitere** | selection has further channels | optics (zoom, focus, prism, iris), effects, programmes, everything else |
| **Mapping** | selection has pan/tilt | map one position onto other channels |
| **Assistent** | always | effect assistant, **+ Szene** (scene), **+ Chaser**, **Programmer → Szene**, list of all functions with **Start**/**Stop** |
| **EFX** | selection has pan/tilt | movement effects |
| **Matrix** | always | colour and dimmer matrices of the selection ([Matrix-Effekte](../anleitung_matrix_effekte/ANLEITUNG_MATRIX_EFFEKTE.md), German) |
| **Laser** | selection contains a laser | see [Laser bedienen](../anleitung_laser/ANLEITUNG_LASER.md) (German) |
| **Paletten** | always | stored colours, positions … to recall |

![Palettes tab with a recorded colour](img/06_paletten.png)

**Paletten (1)** (palettes) are stored values for quick recall, separated into
**Farben** (colours), **Position**, **Beam**, **Effekte** (effects) and **Laser**. To
create one:

1. Select fixtures and set the colour you want (here pink on the PARs).
2. In the sub-tab **Farben** click **+ Neu aufzeichnen (2)** (record new) and enter a
   name.
3. The palette appears as a tile **(3)**. A click on it applies its values to the current
   selection. If nothing is selected, nothing happens apart from the hint
   „Keine Geräte ausgewählt“ (no fixtures selected). Right-clicking the tile opens a menu
   with **Anwenden** (apply), **Überschreiben (Programmer)** (overwrite from Programmer),
   **In Ordner verschieben…** (move to folder) and **Löschen** (delete).

Recording without a selection takes the whole content of the Programmer.

Palettes are saved with the show.

## 7. Highlight and dim others

![Highlight and dim others with the wash lights selected](img/07_hervorheben.png)

This helps you find fixtures on stage:

1. **Hervorheben** (highlight) sets the selected fixtures to full brightness, white and
   pan/tilt to the centre (shortcut **H**).
2. **Abdunkeln** (dim others) dims all *unselected* fixtures to about 30 %
   (shortcut **Umschalt+H**, Shift+H).
3. In the **Lampen-Vorschau** the selected wash lights shine white.

Both buttons write real values into the Programmer — not just temporarily. They stay until
you clear them (step 11) or press **Rückgängig** (undo). **Abdunkeln** affects *all other*
fixtures: to tidy up, first press **Keine** (none) and then **Alles löschen** (clear all).

## 8. Colour tool

![Colour tool](img/08_farbwerkzeug.png)

**Farb-Werkzeug...** opens the **Color Tool** window with three tabs: **Einfach** (simple:
colour wheel and **Helligkeit**, brightness), **Vollständig** (complete: RGB, HSB, CMY,
white/UV/amber) and **Filter** (Lee/Rosco colour filters to click).

1. **Auf Auswahl anwenden** (apply to selection) writes the chosen colour onto the selected
   fixtures.
2. **Live AUS** / **Live EIN** (live off/on): with „Live EIN“ every change takes effect
   immediately.
3. **Als Palette…** (as palette) stores the colour as a colour palette (see step 6).

**Schwarz** and **Weiß** (black, white) set the colour picker to those colours.
**Schließen** (close) closes the window. If nothing is selected, the tool only acts on
fixtures that already have values in the Programmer, never on the whole rig.

## 9. Position tool

![Position tool](img/09_positionswerkzeug.png)

**Positions-Werkzeug...** opens the **Position Tool** window: on the left a pad (pan to the
right, tilt downwards), below it the faders **Pan (fein)** and **Tilt (fein)** for the fine
channels, on the right **Voreinstellungen** (presets) such as „Mitte (127/127)“ (centre) or
„Publikum M“ (audience centre).

1. **Auf Auswahl anwenden** writes pan, tilt and the fine values onto the selection.
2. **Live**: when ticked, every movement on the pad takes effect immediately.
3. **Mitte** (centre) sets the pad to 127/127, **Zurücksetzen** (reset) to 0/0. Without
   **Live** you then still have to press **Auf Auswahl anwenden**.

**Preset übernehmen** (take preset) puts the marked preset on the pad. If nothing is
selected, the tool takes the fixtures that already have values in the Programmer, and if
there are none, all fixtures.

## 10. Fan

![Fan tool with eight PARs](img/10_faecher.png)

**Fächer...** (fan) spreads a value as a gradient across the selection, for example a
brightness ramp over eight PARs or a pan fan over moving heads.

- **Modus:** (mode) **Symmetrisch** (symmetric: centre = min, outside = max),
  **Asymmetrisch** (asymmetric: centre = max), **Start** (rises from the first to the last
  fixture), **Ende** (end: falls).
- **Attribut:** (attribute) e.g. **Intensität**, **Pan**, **Tilt**, **Rot**.
- **Kurve:** (curve) **Linear**, **Sinus**, **Rechteck** (square), **Dreieck** (triangle),
  **Exponential**.
- **Werte-Bereich** (value range) with **Min:** and **Max:**.
- The table shows in advance which value goes onto which fixture. The order is the order
  of your selection.

1. **Fächer anwenden** (apply fan) writes the values. **Auswahl neu laden** (reload
   selection) takes over a selection that has changed in the meantime.

## 11. Clear, undo, copy

![Clear selection](img/11_loeschen.png)

1. **Löschen** (clear) changes its label with the selection:
   - **Auswahl löschen (4)** (clear selection): with a selection the button only empties
     the values of these four fixtures. The others stay.
   - **Alles löschen** (clear all): without a selection it empties the whole Programmer.

   Saved scenes, cues and snapshots are untouched in both cases. **Esc** always empties the
   whole Programmer (menu **Programmer → Programmer leeren**). The **✖ Clear ▾** menu in
   the header at the top also clears Simple Desk values.
2. **Rückgängig** (undo) and 3. **Wiederholen** (redo) have their **own Programmer
   history**. It records every change to Programmer values, wherever it comes from: fader,
   quick-select tile, palette, **Hervorheben**, **Abdunkeln**, **Einfügen**, **Löschen** or
   the command line. One fader move from press to release is **one** step, and so is one
   button press, even if it hits many fixtures. **Rückgängig** restores the state before
   that step, **Wiederholen** brings it back. Both buttons are only active when there is
   something to undo or redo; the tooltip names the step.

   Changes to the patch and to fixture settings, such as the orientation checkboxes from
   step 5 (**Pan invertieren** …), are **not** in this history. You undo them via
   **Bearbeiten → Rückgängig** (**Strg+Z**) and redo them via
   **Bearbeiten → Wiederherstellen**. **Neue Show** (new show) and **Show öffnen** (open
   show) empty both histories.

**Kopieren** (copy) remembers the Programmer values of the selected fixtures, **Einfügen**
(paste) puts them onto the current selection. With several fixtures this goes in turn: the
first copied value onto the first selected fixture and so on (shortcuts **Strg+C** /
**Strg+V**).

---

## If something does not fit

| Observation | Cause | What to do |
|---|---|---|
| A scene or cue has no effect | The Programmer has priority and covers it | **Keine**, then **Alles löschen** (or **Esc**) |
| No faders are visible after clicking a group | Clicking a group jumps to the **Matrix** tab | Click the **Intensity** or **Color** tab |
| The **Position** tab is missing | No fixture with pan/tilt is in the selection | Select moving heads as well |
| **Rückgängig** in the Programmer does not undo a **Pan invertieren** checkbox | Fixture and patch settings are in the **Bearbeiten** history, not in the Programmer history | **Bearbeiten → Rückgängig** (**Strg+Z**) |
| Other fixtures stay dark after **Abdunkeln** | The 30 % are in the Programmer | **Keine**, then **Alles löschen** |
| A fixture shows buttons that are not explained here | Fixture-specific controls | [Programmer: jedes Gerät richtig bedienen](../anleitung_geraete_bedienen/ANLEITUNG_GERAETE_BEDIENEN.md) (German) |

---

*Pictures: the same as the German guide, created with
`venv/bin/python tools/anleitungsbilder.py programmer_grundlagen` from the practice show
above (see [Anleitungsbilder aus dem Code erzeugen](../ANLEITUNGSBILDER.md), German).*
