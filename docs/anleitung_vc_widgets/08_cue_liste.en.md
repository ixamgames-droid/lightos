# Cue list (`VCCueList`)

> **English version** of [Cue-Liste (`VCCueList`)](08_cue_liste.md). LightOS itself speaks German: every button, menu and field is quoted here **exactly as it appears on screen**, with an English translation in brackets the first time it shows up. The screenshots are the same as in the German page.

> Shows the cue list of an executor slot (cuestack) and controls it with GO / BACK / STOP — the standard way to run through a prepared sequence of scenes live.

![Cue list](img/VCCueList.png)

## What it is for & what it controls

The cue list is bound to **one executor** (a place in the playback's executor bar, with its cuestack). It shows the cues of this slot as a list and highlights the cue that is currently running. With the three transport buttons at the bottom edge you step through the list during operation — forward, back or stop.

The element continuously mirrors the slot's state: it polls the executor about **5 times per second** (every 200 ms), picks up changes to the cue list automatically and marks the currently active cue. So you are always controlling the same cuestack that the playback itself uses — the widget is a remote control for it.

## What it looks like & how to use it during operation

From top to bottom, the element consists of three parts:

1. **Title bar** (blue, bold, centered) — shows the widget's label („Cueliste" (cue list) in the picture). It is set in the settings.
2. **Cue list** (dark box) — one line per cue in the format `Nummer  Beschriftung` (number  label), e.g. `1.0  Rot`, `2.0  Gruen`, `3.0  Blau` (red, green, blue). If a cue has no label, `---` is shown there. The **currently running cue** is marked with a colored background.
3. **Row of transport buttons** (three buttons side by side):

| Button | Label in the picture | Function |
|---|---|---|
| BACK | `◄◄` | Jumps to the **previous** cue (sends `back` to the executor slot). |
| GO | `GO ►` (highlighted, blue/green) | Starts or jumps to the **next** cue (sends `go` to the executor slot). The main button, clearly set apart. |
| STOP | `■` | **Stops** the slot's playback (sends `stop` to the executor slot). |

**How to use it:** during operation (Bearbeiten (edit) OFF), clicks on the buttons act immediately on the bound slot. The list itself only displays the current cue; clicking a line does not trigger a jump — switching happens exclusively via the three transport buttons.

**In edit mode** the list and all three buttons are disabled (no accidental triggering); the widget can then only be moved/resized. A double-click opens the settings (see the overview in [README.en.md](README.en.md)).

## Settings

![Settings](img/dialog_VCCueList.png)

| Setting | Meaning | Values/options |
|---|---|---|
| **Beschriftung** (label) | Text in the blue title bar above the list. Display only. | Free text. If the field is left empty, the previous label is kept. |
| **Executor-Slot** | Which executor the widget remote-controls and displays. **Ex N** is executor N in the executor bar of the **currently active playback page** – not playback page N. | **Ex 1 to Ex 10** (default: Ex 1). The show file stores the 0-based index (`stack_slot`: 0 = Ex 1, 9 = Ex 10). |

## Tips & pitfalls

- **The slot must be occupied:** if the list shows nothing, no cuestack is loaded on the configured executor slot. First put a cuestack on the matching slot, or set **Executor-Slot** to the right number.
- **Executor, not page:** „Ex 3" means “third executor of the executor bar”, not “playback page 3”. The cue list always follows the **currently active page**: if you change the page (e.g. with a bank button on the APC), the same widget controls Ex 3 of the new page. If a different cuestack appears than expected, either the Ex number or the active page is wrong.
- **The list is display only:** clicking in the cue list does not jump to that cue. Always use GO / BACK / STOP to switch.
- **Automatic update:** the display follows the real playback state (about every 200 ms). What you see marked in the list is the cue that is really running — even if it was triggered from elsewhere (hardware, another widget).
- **GO ► moves on:** GO is not just “start” — every press advances one cue. Pressing repeatedly runs through the list step by step; BACK goes back accordingly.
