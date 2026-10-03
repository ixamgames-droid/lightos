# BPM manager (tempo detection & management)

> **English version** of [BPM-Manager (Tempo-Erkennung & -Verwaltung)](20_bpm_manager.md). LightOS itself speaks German: every button, menu and field is quoted here **exactly as it appears on screen**, with an English translation in brackets the first time it shows up. The screenshots are the same as in the German page.

> The dedicated **BPM** tab in which LightOS detects, displays and manages the global tempo — the central place from which all tempo-bound effects take their beat.

![Sub-tab Erkennung (detection) in normal operation: large BPM number 127,6, source PC-Audio: Lautsprecher (speakers), beat dot with bar 1 2 3 4, state word EINGERASTET (locked in), confidence 100 %, level −19 dBFS in the green zone; below that TAP, Auto | Manuell, ×½, ×2, the green status line and the collapsed Erweitert (advanced) section](../anleitung_bpm_manager/img/erkennung_eingerastet.png)

## What it is for

A great many things in LightOS run "on the beat": pulsing colors, strobe, chaser steps, EFX speed, BPM-coupled faders in the Virtual Console. For this to work, there has to be **one** reliable, global BPM number. The BPM manager is exactly this one source:

- It **detects** the tempo automatically from the music (audio analysis) — or
- you **set it manually** (Tap, Nudge, Lock) when the automatic detection is off for once, and
- it **manages** additional tempo buses (e.g. "bass runs half as fast as drums") to which you can couple individual effects.

In short: the manager is the show's **tempo leader**. Everything that should run "on the beat" listens to it.

## Where to find it (tab „BPM"; sub-tabs „Erkennung" (detection) / „Tempo-Buses" / „Generator")

Click **BPM** in the top tab bar. The tab has three sub-tabs:

| Sub-tab | Content |
|---|---|
| **Erkennung** | Live detection — that is this page (called „Manager" until 2026-09-14). |
| **Tempo-Buses** | Tempo speeds, grand master, effects per bus (a sub-tab of its own since 2026-09-14). |
| **Generator** | Analyze a whole song in advance and generate a beatgrid (see below). |

In the global header (top right) you also always see the current **BPM number**, the mode (**AUTO**) and a **TAP** button — they mirror the same state as this tab.

## Displays (BPM number, beat dot, state word, confidence)

At the top, the sub-tab shows live what the detection is doing right now:

| Element | Meaning |
|---|---|
| **Large BPM number** (e.g. „98,3") | The currently valid global tempo. Yellow = Auto, green = Manuell (manual); `--` (grey) = no BPM active at the moment. |
| **Beat dot** (circle) | Flashes on every beat — gold on the **one** (downbeat), green on the other beats. A visual check of whether the beat sits right; if it flashes out of time with the music: one **TAP**. |
| **Takt: 1 2 3 4 …** (bar: 1 2 3 4 …) | The cells light up in turn; the yellow cell is the **one**. The number of cells follows *Beats/Takt* (beats per bar), found under Erweitert (advanced). With very many beats per bar (>16), the exact position is also shown on the right as „n / N". |
| **State word** | **KEIN SIGNAL** (no signal — nothing to hear), **SUCHT** (searching — the analysis window is filling, ~4 s), **EINGERASTET** (locked in — beats are running), **PAUSE · hält N** (pause · holding N — silence, the tempo is held), **MANUELL** (manual), **OS2L · wartet auf DJ-Software** (OS2L · waiting for DJ software), **LIED-ANALYSE** (song analysis), **AUS** (off). Next to it: who set the BPM last („· Audio", „· Tap", „· Lied-Analyse" (song analysis), „· OS2L (extern)" (external)) and whether it is frozen (**🔒**). |
| **Konfidenz** (confidence) (bar) | How certain the detection is, in percent. High = stable beat; low = uncertain (quiet/complex track, pause, speech). |
| **Pegel** (level) (wide bar + dBFS number) | How loud the source arrives; green target zone −30…−6 dBFS. Next to it, the chips CLIP/BRUMM (hum)/LEISE (quiet)/AUSSETZER (dropout)/DC on disturbances. |
| **Status line** | Never empty: „Problem — Ursache" (problem — cause), below it „→ Abhilfe" (→ remedy) (underlined = clickable). Green = OK, yellow = hint, red = problem. Illustrated in the [BPM-Manager-Anleitung](../anleitung_bpm_manager/ANLEITUNG_BPM_MANAGER.md) (German). |
| **Spektrum** (spectrum) (bar graph, in **Erweitert**) | Live frequency display of the input signal — useful to see whether any audio is arriving at all and where the energy is. |

## Quelle (source), TAP, Auto | Manuell, ×½ / ×2 (sub-tab „Erkennung", since 2026-09-14)

Without any click, the **Erkennung** sub-tab shows exactly **six controls**; everything else is behind **▸ Erweitert**.

| Element | Effect |
|---|---|
| **Quelle** (list) | Where the tempo comes from: **PC-Audio** (loopback — LightOS listens to whatever is playing on the PC: player, Spotify, browser), **Eingang: <Gerät>** (input: *device* — one entry per microphone/line-in/interface; the list re-reads the devices when opened), **OS2L (DJ-Software)** (DJ software — tempo & beats come from VirtualDJ/Mixxx; LightOS starts its OS2L server and switches off its own audio analysis), **Lied-Analyse (Player)** (song analysis — follows the beatgrid of the analyzed title loaded in the player; the generator button „Im Player laden & als BPM-Quelle nutzen" (load in player & use as BPM source) selects this entry itself), **Aus** (off). When the generator button switches the source, the list follows. |
| **TAP** (large button) | Tap *once* = beat dot to "now" (tempo stays). Tap *three or four times in time* = set the tempo; the detection searches around this tempo. The same button as **TAP** in the header. |
| **Auto \| Manuell** | **Auto:** the tempo follows the source. **Manuell:** the tempo stays as you set it with TAP/Nudge; the source keeps running in the background. The **AUTO/MANUAL** badge in the header mirrors the same state. |
| **×½ / ×2** | Half/double tempo with one click — in Auto as an octave hint to the detection, in Manuell directly on the tempo. |
| **▸ Erweitert** | Tempo-Bereich von/bis (tempo range from/to) + **Vorlage ▾** (template — genre ranges), Beats/Takt, Beat-Latenz (beat latency) (ms), **🔒 Tempo einfrieren** (freeze tempo), Nudge −5/−1/+1/+5, Taktgenau (beat-accurate), plus the diagnostic line and spectrum. |

> **State word** next to the beat dot: **KEIN SIGNAL** / **SUCHT** / **EINGERASTET** / **PAUSE · hält N** / **MANUELL** — plus the **Konfidenz** bar. When you change the source, LightOS stops the other live source (audio ↔ OS2L) so that the two don't compete for the BPM; a change is always just ONE switching operation.

**Precedence (who wins):**

1. **Manuell** (also reached via TAP from the third tap in time, or via Nudge) and **🔒 Tempo einfrieren** override everything: as long as either of them applies, no source changes the tempo.
2. **PC-Audio / Eingang:** if LightOS is listening live, the detection alone leads. The song analysis and the player's nominal BPM don't get through then.
3. **Lied-Analyse (Player):** in **Auto**, a song playing in the player that has been **analyzed** in the generator leads with its BPM curve. A song without analysis sets its nominal BPM when it starts — this requires the **BPM koppeln** (couple BPM) checkbox in the **Musik** (music) tab.
4. **Aus** and **OS2L:** the song does **not** lead. With **OS2L** the tempo comes solely from the DJ program; with **Aus** no source changes the BPM at all.

So the **Quelle** list decides **who is allowed to lead** — not just whether LightOS listens. The generator button switches exactly like a selection in the list.

> **Changed since 2026-09-28 (BPM-17):** previously an analyzed song also led with **Aus** and **OS2L**. With „Aus", the status line and state word then said „Erkennung aus" (detection off) while the BPM followed the song; with OS2L, the DJ program and the song curve both wrote to the tempo. If you want a song to drive the light, the source must now be set to **Lied-Analyse (Player)**.

## Erweitert — advanced (Tempo-Bereich, Vorlage, Beats/Takt, Beat-Latenz, Einfrieren, Nudge, Taktgenau)

| Control | Effect | Tip |
|---|---|---|
| **Tempo-Bereich — von / bis** | Lower and upper BPM limit of the detection (20–400). Values outside are doubled/halved. | Setting it narrow is a lasting cure for "half/double tempo". For 4-on-the-floor e.g. ~120–135. |
| **Vorlage ▾** | Menu with genre ranges (House, Techno, Hardstyle, …) — sets **only** the tempo range + beats per bar. | Choose once before the set. |
| **Beats/Takt** | Beats per bar; every N beats there is a downbeat (the "one"). | 4 = four-four time. Does **not** change the beat rate. |
| **Beat-Latenz** (ms) | Report beats earlier (+) / later (−). | If the light audibly lags behind → go into the plus in 5 ms steps. |
| **🔒 Tempo einfrieren** | Freezes the BPM; no source changes it until you release it. | Press it before a break/an announcement. |
| **Nudge (−5 … +5)** | Corrects the BPM in fixed steps (switches to Manuell). | For fine trimming when the value is almost right. |
| **Taktgenau** | Beats hit the beatgrid of the analyzed song exactly (only when an analyzed song in the player leads — in Auto, without PC-Audio/Eingang, see precedence). | Leave it on. |

All settings are saved and loaded again at the next start (section `bpm_settings`, v3).


## Tempo buses & grand master (Master/Sub, Folgt, Faktor — how to couple effect tempos)

The **Tempo-Speeds & Grand-Master** box in the **Tempo-Buses** sub-tab manages **several** named tempo tracks ("buses") to which you can attach individual effects — instead of everything running rigidly on the one sound BPM.

**Terms:**

- **Default (Sound-BPM)** — the base bus. Carries the detected/set main tempo. Cannot be deleted.
- **Master** — a separate, named tempo bus (e.g. "Bass", "Drums") that you can name freely.
- **Sub** — a derived bus that **follows another one** and multiplies its tempo by a **factor** (e.g. "½×" = half as fast).

### The table

| Column | Meaning |
|---|---|
| **Bus** | Name of the bus („Default (Sound-BPM)" at the top). |
| **Rolle** (role) | Master or Sub. |
| **Folgt** (follows) | For subs: which bus it follows (or „Sound-BPM"). For masters „—". |
| **Faktor** (factor) | For subs, the multiplier (¼ · ½ · 1× · 2× · 4× …). For masters „—". |
| **BPM** | The resulting current tempo of the bus. |

### Creating / editing / deleting

1. At the bottom, enter a name in the **„Neuer Master-Name"** (new master name) field and click **Master anlegen** (create master).
2. Click a bus in the table — the editor row below it fills in. There:
   - set **Rolle** to *Master* or *Sub*,
   - for a sub, choose the parent bus under **Folgt** and the multiplier under **Faktor**,
   - save with **Übernehmen** (apply).
3. **Löschen** (delete) removes the selected bus (except Default). **Aktualisieren** (refresh) reloads the table.

### Grand master

The top row is the **Grand-Master** — a higher-level tempo that **overrides all masters** when it is armed:

| Control | Effect |
|---|---|
| **Grand-Master scharf** (grand master armed) (checkbox) | When activated, **all** masters run on the grand master beat (subs stay relative to their master). |
| **BPM** (input) | The grand master tempo (0 = off). |
| **Tap** | Tap in the grand master beat. |
| **Status** (aus/scharf = off/armed) | Green „scharf" when active and BPM > 0; otherwise grey „aus". |

This way you can, for example, lock **all** effect tempos to one value in a flash for a drop, without touching each bus individually.

## Generator sub-tab (in brief)

The third sub-tab, **Generator**, analyzes a **complete song in advance** instead of live:

1. **Datei wählen** (choose file) (an audio file), select **Genre** and **Analyse-Engine** (analysis engine) (Eingebaut/numpy (built-in/numpy), librosa, Beat This! — engines that are not installed fall back cleanly to the built-in engine).
2. **Analysieren** (analyze) decodes the track and generates a **BPM curve** + a phase-accurate **beatgrid** (plotted with a time axis).
3. The grid can be **corrected** as in VirtualDJ/Serato: ½×/2×, nudge, set the **downbeat by clicking** in the plot.
4. **„Im Player laden & als BPM-Quelle nutzen"** makes the analysis the BPM source: the **Quelle** list in the Erkennung sub-tab jumps to **Lied-Analyse (Player)**, PC-Audio/Eingang and OS2L are switched off, and during playback the global BPM in **Auto** follows the song over time (in Manuell or with a frozen tempo it stays put). Alternatively **als .json exportieren** (export as .json).

This gives you a clean, pre-checked tempo even for tracks that change tempo or are hard to detect.

## Relation to the VC (widgets BPM display, tempo bus, speed dial, fader in BPM mode)

The BPM managed here is global — the Virtual Console accesses it directly:

- **BPM display widget** — mirrors the large BPM number/the beat onto your VC page.
- **Button „Musik-BPM“** (music BPM) — switches the source just like the **Quelle** list here: on = the last selected audio source (otherwise PC-Audio system default) in **Auto**, off = back to the last selected other source (OS2L, Lied-Analyse or Aus). The list in the Erkennung sub-tab follows every time.
- **Tempo bus widget** — selects **which bus** (Default/Master/Sub) an area should follow; this is how you make, for example, an effect run at "½×".
- **Speed dial** — controls the speed of a tempo-bound effect relative to the bus.
- **Fader in BPM mode** — a fader that doesn't set a DMX value but a **tempo/rate**; it thereby sets (in the MANUAL sense) the BPM or the bus factor.

Rule of thumb: **here** (in the manager) you decide the source and the buses; **in the VC** you get the display and live access during the show.

## Tips & pitfalls

- **Half/double tempo?** Almost always a limits problem. Set the *Tempo-Bereich* (Erweitert) more narrowly around the expected range, and the doubling/halving goes away.
- **Detection jumps:** In „Erweitert", set the **Tempo-Bereich** narrower or choose a **Vorlage**.
- **The beat sits right and should stay that way?** Press **🔒 Tempo einfrieren** (Erweitert) before you go into a quiet/breakdown passage.
- **The automatic detection is completely off:** switch to **Manuell** and **TAP** (3–4× in time) — safer than fighting the detection. Fine-tune with **Nudge**.
- **Only one live source:** PC-Audio/Eingang and OS2L exclude each other. When you switch, LightOS stops the other one automatically — don't be surprised if nothing is detected for a moment while switching. An analyzed song in the player still leads in Auto, as long as PC-Audio/Eingang is not selected (see precedence).
- **„Eingang" without sound?** Select the right device in the **Quelle** list (the list re-reads when opened) and check the level line, the status line and the diagnostic line in „Erweitert".
- **Don't forget to disarm the grand master:** As long as it is „scharf", all masters ignore their own tempo. Untick the checkbox again when the buses should run independently again.
