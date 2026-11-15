# Room pad (`VCRaumPad`)

> Tap a point in a top view of the stage. Every assigned moving head aims at exactly that point. You point at the room instead of pushing pan and tilt.

## What it is for

The XY pad works in pan/tilt. "Front right corner" means nothing there, because every head hangs somewhere else. The room pad works out for **each head separately** how it must stand so its beam hits the tapped point. It uses location and mounting from the 3D visualizer. It is the same calculation as the visualizer's **“Zielen”** (aim) tool, including the calibration offset and the fine channel (16 bit).

The values go into the **programmer** (`pan`, `tilt` and, if the fixture has them, `pan_fine`/`tilt_fine`). That is the same path the XY pad uses. Other programmer values, such as dimmer or colour, are never touched.

## Look & operation

- **Centre: the top view.** The room size comes from the placed fixtures (like the visualizer's room shell: rig plus 4 m margin, at least 12 × 12 m). The back wall (**Rückwand**) is at the top, the audience (**Publikum**) at the bottom. The grid is 1 m, the room size is shown bottom left.
- **Blue numbered dots:** the assigned moving heads at their location (number = fixture ID).
- **Yellow dashed circles at the top left:** assigned heads **without a position** in the visualizer. They do **not** move. The pad says “ohne Position – fährt nicht mit” and the tooltip lists them. Fix: place the fixture in the 3D visualizer or calibrate it.
- **Tap or drag** in the top view to set the target. The pad switches **AN** (on). Pink target mark, thin lines from each head to the target, coordinates bottom right.
- **Bottom: target height** (“Höhe”). It goes from 0 m (floor) up to the room height. Changing it while the pad is on moves the heads right away.

| Switch | Effect |
| --- | --- |
| **AN / AUS** (on/off) | On: the heads aim at the point. **Off** releases pan/tilt/fine of these heads: each value gets back what was in the programmer before. If there was nothing, it is removed and the heads return to whatever runs underneath. Output is then the same as before. A value someone else changed in the meantime is left alone. |
| **Lock AN / Lock AUS** (position lock, default on) | **Lock on:** the target stays after you let go. **Lock off:** the target only counts while the finger or mouse button is down. Letting go releases like AUS. With lock off, the AN button also only works while held, like a flash button. Switching the lock off while a target is standing releases it at once. |

The on state is **not** saved, so a loaded show never writes into the programmer by itself. Saved are the assignment, last target, target height and position lock. A target that is only **held** (lock off) never gets stuck: it is also released on a bank change, when the window loses focus, when the system cancels the touch, or when touch lock comes on while holding. Touch lock blocks the pad. In edit mode, dragging moves the widget. On a touchscreen, swiping on the pad does not scroll the console. In touch mode the switches and the height slider are at least 44 px high.

## Unfolded view (“Aufgeklappt”)

Set **Ansicht** (view) to **“Aufgeklappt”** in the inspector or the settings dialog. The pad then shows the room like an unfolded box without a ceiling, true to scale: the **floor** in the middle, the **back wall** above, the **side walls** left and right, the **front wall** (audience side) below. Every surface is labelled.

- Tapping the **floor** works like the top view (target height applies).
- Tapping a **wall** aims at a point **on that wall**: the height is the distance from the fold edge, the other direction follows the floor. The height slider is greyed out and shows the wall height (“Wand … m”).
- **Dragging across a fold edge** moves continuously onto the neighbouring surface; at the edge floor and wall give the same point (exactly so at target height 0 m, the default; with a higher target height the target drops by that height once when crossing — a dashed line on the walls shows it). Outside all surfaces the point is clamped to the nearest one; a tap into an empty corner sets nothing.
- Heads stand on the floor at their location; hanging heads show their height.
- Each wall can be switched off (the floor always stays); a hidden wall cannot be tapped.
- A head that cannot reach the target (outside its pan/tilt range, e.g. high up a wall with a 180° tilt fixture) gets a **red ring with “!”** and is named in the tooltip. Its value is still the one the visualizer's aim tool gives, clamped at the end stop.

Position lock and on/off work the same in both views. View and visible walls are saved with the show; older shows open in the top view.

## Settings

Double-click the pad in edit mode: “Raum-Pad Einstellungen”. Tick the **moving heads** (the list only shows fixtures with pan **and** tilt, so a PAR cannot be assigned), use **“Aktuelle Auswahl übernehmen”** to take over the current selection, and tick **groups** if you like. Without an assignment the pad shows “Keine Moving Heads zugeordnet” and does nothing. Unlike the XY pad, it never falls back to the selection or to all fixtures.

## Tips

- The pad is only as accurate as the positions in the visualizer. Calibrate the heads for real hits on the rig.
- Several pads on the same heads: the last one used wins. Off only releases values that still come from that pad.
- The phone console cannot operate surface widgets like the room pad yet.
