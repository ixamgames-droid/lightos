# 23 · Live edit panel (`VCMultiLiveEditor`)

> **English version** of [23 · Live-Edit-Panel (`VCMultiLiveEditor`)](23_live_edit.md). LightOS itself speaks German: every button, menu and field is quoted here **exactly as it appears on screen**, with an English translation in brackets the first time it shows up. The screenshots are the same as in the German page.

> **Toolbar button:** „Live-Edit" (edit mode only)
> **Back to the** [widget overview](README.en.md)

A **control workstation for several effects on one surface**. You drag effects into it, page through them at the top, and below that you get exactly the controls you ticked beforehand.

![Live edit panel, freshly created](img/widget_live_edit.png)

> When freshly created, it is empty and tells you itself what to do — that is exactly how it should look. The content only appears once effects are assigned.

## What you see

| Element | Meaning |
|---|---|
| **Header** | The panel's caption. |
| **`–` / dropdown / `+`** | Pages through the assigned effects. The body always shows the **currently selected** one. |
| **Body** | The controls of the selected effect — each matching its type: floating-point values as a **slider**, integers as **–/+**, yes/no as a **switch**, a choice as a **button group**, a direction as **arrows** (`→` forward, `←` backward, `↔` ping-pong …). In addition, a preview and a tempo mode per effect. |

**Assigning effects:** drag a function (matrix, chaser, EFX …) from the function tree into the panel by drag & drop. Several effects are explicitly intended.

## The core idea: two modes, one panel

The panel depends on the **VC edit mode** — and that is not a side issue but its actual operating concept:

| VC mode | What the panel shows |
|---|---|
| **Bearbeiten ✓** (edit on) | The **checkbox selection**: all live-controllable parameters of the effect as checkboxes. Here you tick *what* you want to operate later — individually per effect. |
| **Bearbeiten aus** (edit off — i.e. operation) | Only the **ticked** controls, tidy and without the checkbox list. Ready to use. |

So if you miss a control during operation, you haven't lost it — it just isn't ticked in edit mode.

## All together („Alle gemeinsam“)

With **two or more** assigned effects, the dropdown offers an extra entry **„Alle gemeinsam (N)“** (all together). When selected, the body shows **only the parameters that all effects have** — same name and matching value range (e.g. colors, direction, brightness, fade for several matrices; for matrix + EFX brightness, direction and tempo factor). A change applies to **all at once**: numeric values are set to the **same** value everywhere (no relative shift), a color list is copied to every effect (each effect keeps its currently active color). Preview and the tempo area (off/BPM/tap) stay hidden there — they remain per effect; the **tempo factor** (¼ … 4×) is offered as a shared control „Tempo ×“. It affects effects that follow a tempo bus.

- **„gemischt“** (mixed): if the effects start with different values, the control shows „gemischt“ (slider centred, no button pressed) until you move it.
- **Direction:** matrix (forward/reverse), EFX (forward/backward/ping-pong) and chaser name „backward“ differently internally; the panel maps them with a fixed table and only offers the directions all of them support.
- **„gilt für: …“** (applies to) below the controls names the effects a change reaches.
- In **edit mode** you tick which shared controls appear during operation — a separate set, independent of the ticks of the individual effects.
- `–` / `+` leave „Alle gemeinsam“ and jump to the first or last effect.

## What is saved

The show stores: geometry and caption, **which effects** are assigned (`fids`) and **which controls are ticked** (`checked`, for „Alle gemeinsam“ `joint_checked`) and whether „Alle gemeinsam“ was selected (`joint`). Merely switching to „Alle gemeinsam“ is operation and does not count as an unsaved change. The live values you set belong to the respective effect, not to the panel.

## Related

- [18 · Effect editor box](18_effekt_editor.en.md) — the same for **one** effect
- [16 · Effect display](16_effekt_anzeige.en.md) — preview only, without controls
- [21 · Smart-Drop & building kit](21_baukasten.en.md) — set up an effect as you drag it in
- `docs/LIVE_EDIT_FENSTER.md` (German) — the standalone live edit window outside the VC
