# Pixel grid (`VCPixelraster`)

> Paint with a finger or the mouse directly onto an LED matrix or a head group. Every grid cell is a head (or a whole fixture); the painted colour sits with its own level on top of whatever is running, including running matrix effects.

## What it controls

The grid comes from a **fixture group**: head cells and whole fixtures; sub-group blocks (group in group) are resolved.

The drawing is its **own output layer**, not the programmer:

- It sits **above** effects, cue lists, programmer and modify effects: `result = below + (painted − below) × level`.
- **Masters, blackout, grand master and laser E-stop** stay above it.
- It writes **only red, green and blue**, never a dimmer. Colour never pulls the dimmer up.
- Unpainted cells leave the layer below untouched. Painted pixels never end up in cues or snaps.

## Operation

- **Toolbar:** **Brush**, **Eraser**, **Fill**, **Colour** (colour picker like the colour tile), **Resolution** (`1×1` → `2×2` → `4×4`), **Clear** (tap twice within 3 s), **Store**, **Recall** (cycles through stored drawings, up to 12).
- **Grid** in the middle, **level fader** on the right.
- Touch lock blocks the element; in edit mode dragging moves/resizes it. On a finger the grid is a control (swiping paints, the console does not scroll). In touch mode all buttons and the level fader are at least 44 px.

## Settings & saving

Double-click in edit mode (not in kiosk): caption and group. The inspector offers "Assign group…" and "Re-read grid". Group, drawing, stored drawings, level, colour, tool and resolution are saved with the element; painting marks the show as changed. A show with a drawing and level above 0 outputs it right after loading, like a fader its stored value. Shows without a pixel grid load unchanged.

Not yet: binding to a single matrix fixture without a group, blend modes other than crossfade.
