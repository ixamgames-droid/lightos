# Smart-Drop & building kit (creating elements quickly)

> **English version** of [Smart-Drop & Baukasten (Elemente schnell anlegen)](21_baukasten.md). LightOS itself speaks German: every button, menu and field is quoted here **exactly as it appears on screen**, with an English translation in brackets the first time it shows up. The screenshots are the same as in the German page.

> **Note:** The former green building-kit blocks (Controller-Vorlage (controller template), Color-Chase, Chase-Bereich (chase area)) were removed from the Virtual Console in 2026-07 — live color chase now runs via the **Live-Edit-Panel** (`docs/LIVE_EDIT_FENSTER.md`, German), and a controller template via the **Controller-Browser** (section *MIDI*). The **Smart-Drop** („Effekt einrichten" (set up effect)) described here is still current.

> Instead of building and wiring up controls one by one by hand, you drag an effect from the function tree onto the console, and LightOS suggests the matching controls, already wired up.

## Two ways to create an element (toolbar button vs. dragging an effect onto the canvas)

There are two ways to get a control onto the Virtual Console:

1. **Toolbar button (empty element):** In the edit toolbar at the top, you tap a widget button (e.g. „Button", „Fader"). You get an **empty** element, which you then connect to a function yourself via right-click. Good if you know exactly what you want.

2. **Drag an effect onto the canvas (Smart-Drop):** You drag a function (matrix, EFX, chaser …) from the function tree onto the free console area. LightOS looks at **what this effect can actually do** and opens the **„Effekt einrichten"** card. Here you just tick what you want to control — the controls are created already wired up. This is the fastest way and the actual "building kit".

> Requirement for both ways: **edit mode** must be active. In play mode the build buttons are hidden.

## Effekt einrichten (Smart-Drop card)

![Effekt einrichten (set up effect) card](img/baukasten_drop_karte.png)

When you drag an effect onto a free spot, this card appears. At the top is the effect name („Matrix 1" in the picture). Below it is **one row per aspect** that this effect makes controllable — with a **checkbox** on the left and the matching **widget** on the right. You can set several checkmarks: each ticked box becomes its own, fully wired control, and everything is created in **one** step (one shared undo).

> **Important:** Smart-Drop does **not** create a **second effect**. All controls are bound directly to the existing function. For matrix effects the card also shows the channel range: **nur Farbe** (color only), **nur Dimmer** (dimmer only), **nur Shutter** (shutter only) or deliberately **Farbe + Dimmer** (color + dimmer). Unsuitable controls and actions are hidden.

**An/Aus (Toggle)** (on/off (toggle)) is ticked from the start — that is the standard case. If you change nothing else and click **„Erstellen"** (create), you get exactly one on/off button. Which rows appear depends on the effect; possible aspects are:

- **An/Aus (Toggle)** — a button that starts/stops the effect (pre-ticked).
- **Flash (nur gehalten)** (flash, only while held) — a button that runs the effect only as long as you hold it down.
- **Tempo (Geschwindigkeit)** (tempo (speed)) — the effect's speed directly. The default widget is the **Speed-Rad** (speed wheel), alternatively a fader.
- **Farb-Pegel / Dimmer-Pegel / Helligkeit** (color level / dimmer level / brightness) — matching the effect's actual channel range; a pure color effect therefore doesn't get a dimmer channel.
- **Farben ändern…** (change colors…) — opens the **Farb-Editor** (color editor) (edit the effect's color palette).
- **Bewegung (XY-Feld)…** (movement (XY field)…) — EFX only: an XY field that controls the center/size of the movement.
- **Tempo-Bus zuweisen…** (assign tempo bus…) — **Bus-Auswahl** (bus selection): attaches the effect to a shared tempo bus (A/B/C …).
- **Tempo-Multiplikator (×½ ×2)…** (tempo multiplier) — a **Speed-Rad** in multiplier mode: the effect's tempo runs relative to the tempo bus (e.g. half or twice as fast).

Rarely used individual parameters and actions are not listed directly but expanded under **„Mehr Parameter (…)"** (more parameters) at the very bottom — the number in brackets tells you how many there are.
Discrete values such as direction, mode or on/off options get a **+/− stepper** instead of an imprecise fader. Dependent parameters only appear once they are active in the effect (e.g. the color change interval only after you activate „Farbe pro Runde wechseln" (change color each round)).

At the very bottom there is also the **„Als Effekt-Box gruppieren"** (group as effect box) checkbox: with it, all selected elements end up in **one** movable container with a live preview instead of being scattered individually across the canvas.

> For an aspect with only one sensible widget, the button on the right is just a label (greyed out). If there are several options, it reads **„Widget: … ▸ ändern"** (widget: … ▸ change) — a click opens the gallery.

## Choosing a widget (graphical gallery)

![Widget gallery](img/baukasten_widget_galerie.png)

If several widget types fit an aspect (e.g. **Speed-Rad** or **Fader** for tempo), the „▸ ändern" button opens this small gallery. Each candidate is shown as a **tile with a painted preview**, so you can see at a glance what the control looks like. Tap a tile (the current one is marked in blue) and confirm with **OK** — or double-click the tile. The gallery only suggests the types that make sense for this aspect, so a wrong choice isn't even possible.

> You can reach the same gallery later at any time via the right-click menu of an existing element („↔ Widget ändern" (change widget)), e.g. to turn a fader into a Speed-Rad afterwards.

## Dropping onto a control that is already in use (conflict card)

![Conflict card](img/baukasten_konflikt_karte.png)

If you drag an effect directly onto a control that **already** controls something (e.g. a Speed-Rad that already controls „Matrix 1"), LightOS asks first instead of silently adding something. At the top, the card names what the control has been controlling so far, and it offers three clear options:

- **Ersetzen** (replace) — afterwards the control controls **only** the new effect; the old binding is dropped.
- **Dazu koppeln** (couple in addition) — both effects hang on the **same** control and form a group with **one shared tempo**. Handy for running several effects in sync.
- **Neues Widget daneben** (new widget next to it) — leaves the existing control alone and creates a **separate** control for the new effect right next to it.

**Abbrechen** (cancel) leaves everything as it was.

## Tips & pitfalls

- **Edit mode first.** The widget buttons and Smart-Drop are only available in **edit mode**; in play mode they are hidden.
- **Several checkmarks = several elements in one step.** Feel free to tick several aspects in the „Effekt einrichten" card — it saves you trips and can be undone completely with **one** undo (Strg+Z, where **Strg** = Ctrl).
- **„Erstellen" without changes** gives you exactly one on/off button — the fastest case, with one click.
- **Dazu koppeln shares the tempo.** If you choose „Dazu koppeln" on the conflict card, both effects run with **one** shared tempo. If they should stay independent, choose „Neues Widget daneben".
