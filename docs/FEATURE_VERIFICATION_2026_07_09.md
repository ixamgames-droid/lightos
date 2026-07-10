# Feature-Verifikation LightOS — Sweep 2026-07-09

> Auftrag (David): „Alle Funktionen der Software mit dem Computer beweisen/überprüfen —
> Überblick verschaffen, was theoretisch möglich ist, alles einmal durchtesten, und
> gefundene Fehler beheben lassen."
>
> Dieser Bericht dokumentiert den vollautomatischen Verifikations-Durchlauf, das
> Feature-/Abdeckungs-Inventar (21 Subsysteme, 519 Funktionen), die adversarial
> bestätigten Bugs samt Fixes, und den priorisierten **Live-Test-Plan** für die
> render-/hardware-abhängige Oberfläche, die nur ein echter Klick-Durchlauf beweist.

## 1. Automatisierte Beweise (bestanden)

| Prüfung | Ergebnis |
|---|---|
| Import aller `src`-Module | ✅ **232/232**, 0 Fehler |
| MainWindow-Konstruktion + alle **8 Sektionen** & Sub-Tabs durchgeschaltet | ✅ 0 harte Fehler, 0 verschluckte init-Fehler (nur benigne Font-Warnung headless) |
| Alle committeten `.lshow`-Shows laden (Persistenz/Migration v1.1/v1.2) | ✅ **54/54** |
| Volle pytest-Suite (Lock-Runner, isoliert) | ✅ **337 Dateien, 0 Failures** (1 tolerierter viz13-QtWebEngine-Teardown-Segfault) |

**Fazit Engine-Ebene:** Die Rechen-/Denk-Logik (Playback/CueStack, Fade-Kurven, Farbe,
EFX-Mathematik, Undo/Redo, Output-Sendepfad, BPM, Capability-Linter/Builder, Chaser/
Sequence/Collection) ist durchgehend **solide bis vorbildlich** getestet.

## 2. Feature-/Abdeckungs-Inventar (Multi-Agent, 21 Subsysteme)

- **519 nutzbare Funktionen** katalogisiert, **85 als high-risk** (ungetestet UND
  interaktiv/render-abhängig/fragil) eingestuft.
- **Abdeckungslücken-Muster (konsistent überall):** Alles, was echtes **Qt-Widget-
  Verhalten** (Maus-Drag, Popout/Andocken-Reparenting, Timer-Animationen), **UI-seitige
  Persistenz-Rundtrips** oder **externe Hardware/Netzwerk** (MIDI, Audio-Capture, OS2L,
  Enttec, Art-Net/sACN-Empfang, WebEngine) berührt, ist quasi ungetestet.
- Besonders exponiert: das **Popout/„Großes Fenster"-Muster** in ≥9 Editoren
  (RGB-Matrix, Effect-Layer, EFX, Farb-Picker, Chaser, Sequence, Carousel, Audio,
  Scene) — überall ungetestetes Qt-Reparenting (bekannte Fallenklasse).

## 3. Adversarial verifizierte Bug-Verdachte → 4 bestätigt, behoben/erfasst

| # | Verdacht | Verdikt | Severity | Status |
|---|---|---|---|---|
| A | STOP ALL stoppt nur die aktuelle Playback-Page | **CONFIRMED** | 🔴 hoch (Safety) | ✅ Fix PR #230 |
| B | Web-Remote-STOP → tote Route `/api/executor/1/back` (404) | **CONFIRMED** | 🟠 mittel | ✅ Fix PR #231 |
| E | Web-Remote-Fader zeigen initial hart 100 % | **CONFIRMED** | 🟠 mittel | ✅ Fix PR #231 |
| D | Range-Lock lässt Identitäts-Modifier zurück | **PARTIAL** | 🟡 niedrig (folgenlos) | 📋 BACKLOG RL-01 |
| C | Art-Net „Startuniversum" totes UI-Feld | CONFIRMED | 🟡 niedrig | 📋 bereits OUT-03 (geplant) |
| F | `apply_output_config` stellt Verbindung nach Neustart nicht her | **REFUTED** | – | kein Bug |
| — | Tests verschmutzen echtes `crash.log` (APPDATA nicht umgelenkt) | CONFIRMED | 🟡 niedrig (Diagnose) | ✅ Fix PR #232 |

### Fixes (gemergt, je mit Regressionstest + grünem Gate)
- **PR #230** `fix/stop-all-all-pages` (Gate 337 ok): `MainWindow._stop_all` delegiert an
  `PlaybackEngine.stop_all()` (alle Pages) statt `pe.executors` (nur aktuelle).
- **PR #231** `fix/web-remote-stop-fader` (Gate 337 ok): `/api/stop`-Route + Socket-`stop`;
  `/api/status` liefert echte Executor-Fader; `index.html` synchronisiert.
- **PR #232** `fix/tests-appdata-isolation` (Gate 338 ok): conftest lenkt `APPDATA` in
  PID-Temp um → Tests fassen die echte `%APPDATA%/LightOS` (crash.log, stages/, …) nie an.

## 4. Priorisierter LIVE-Test-Plan (nur echter Klick-Durchlauf beweist das)

> Reihenfolge = Schaden×Wahrscheinlichkeit. Für einen Computer-Use-Durchlauf oder
> manuelles Abnehmen. Höchste Priorität zuerst.

**0. Sicherheit übergreifend** — Blackout (sofort 0 / zurück), STOP ALL über mehrere
Pages (nach Fix #230 erneut bestätigen), Grand-Master dimmt nur Intensität/Farbe
(nicht Pan/Tilt/Gobo), Laser-Not-Aus (dunkel + unscharf, auch nach Show-Neuladen),
VC Touch-Lock (Maus tot, MIDI wirkt), Command-Line `blackout`/`go`/`back`/`stop`/`record`.

**1. Web-Remote End-to-End** (nach Fix #231) — STOP stoppt jetzt, Fader initial korrekt,
GO/BACK/Blackout, bidirektionaler Sync mit Haupt-GUI.

**2. EFX Custom-Path-Editor** — Pan/Tilt-Zeichenwerkzeug (Punkte setzen/ziehen/löschen,
Linear/Spline, Pfad schließen), Vorschau folgt exakt; Popout-Stresstest.

**3. Fan-Tool / Position-Tool** — 4 Modi × 5 Kurven durchklicken, Werteverteilung
plausibel; Position-Pad Pan/Tilt; DMX-/3D-Wirkung.

**4. Effect-Layer-Editor** — LayeredEffect (Sin+Multiply+Clamp) bauen, Play, DMX-Monitor;
Min>Max-Validierung; Layer verschieben/löschen; Popout.

**5. Popout/Andocken systematisch** — je Editor „Großes Fenster" öffnen/ändern/schließen
×3 (RGB-Matrix, Farb-Picker, Chaser, Sequence, Carousel, Audio, Scene) → Absturz/
Doppel-Widgets/RuntimeError prüfen; während laufender Show auskoppeln.

**6. Scene-Editor** — Szene anlegen, Kanaltabelle editieren, „Vom Programmer übernehmen",
**„Vorschau senden"** (schreibt direkt auf DMX ohne Safety-Gate — bei Laser prüfen!).

**7. Show-Manager/Timeline** — Drag&Drop auf Tracks, Blöcke verschieben, speichern/laden,
Play/Loop/Playhead, Track-Mute, QXW-Import.

**8. MIDI/OSC/Timecode/APC** — Port öffnen, Monitor, MIDI-Learn, Teach-Dialog (beide
Wege), APC-mini-mk2-Feedback/Ripple, OSC-Befehle (:7770), MTC.

**9. Audio** — Capture/Pegel/BPM, OS2L (:1234), AudioFunction-Fade (Fade-Out mitten in
Fade-In), Musik-Player.

**10. Patch/Fixture-Dialoge** — Laser-Protokoll-Umschaltung (DMX↔Ether Dream/IDN),
Fixture-Editor Save/Load-Rundtrip, Auto-Patch + Undo, QLC+/QXF/.qxi-Import.

**11.–20.** Farb-Picker-Interaktion · Output-Konfig/DMX-Verbindungen · Command-Line
`execute()` · Web-Server-Lifecycle · Kurven-Editor/Modifier/Range-Lock · Laser-Zeichen-
Studio · Playback/Executor-Konfig · Layout-Persistenz/Show-Validierung · Simple Desk/
Channel-Groups · 3D-Visualizer/Bühnenpersistenz.

**Nachtrag 2026-07-10 — OutputView:** Universe 17–32 waren trotz gültigem Patch nicht
im Monitor auswählbar. Die Auswahl reicht nun bis U32; ein Qt-Keyboard-Test bestätigt
die Auswahl und den DMX-Refresh einer 512-Zellen-Ansicht (`tests/test_output_view.py`).
**Nachtrag 2026-07-10 — MidiView:** Die MIDI-/MTC-Ansicht baut ohne Hardware mit
isolierten Fakes, zeigt eingehende Nachrichten im Qt-Monitor und entfernt beim Schließen
alle registrierten MIDI-, Log- und MTC-Subscriber. Regression:
`tests/test_midi_view.py`.
**Nachtrag 2026-07-10 — AudioEditor:** Eine Minimal-`AudioFunction` lässt sich über
die Qt-Controls bearbeiten; der gesamte Editor übersteht drei Popout-/Andock-Zyklen
ohne verlorenen Körper oder Modellwerte. Regression: `tests/test_audio_editor.py`.
**Nachtrag 2026-07-10 — CarouselEditor:** Die Engine-Option `paint_color` war nicht
bedienbar. Der neue Opt-in-Schalter erhält die sichere Standardsemantik (Look-Farbe
nicht überschreiben) und erlaubt bei Bedarf eine feste Carousel-Farbe. Regression:
`tests/test_carousel_editor.py`.
**Nachtrag 2026-07-10 — CollectionEditor:** Der Editor baut mit einem Minimal-Manager
ohne Datenbank-/Hardware-Abhängigkeit; Listeninhalt, Umbenennen, Umordnen, Entfernen
und Transport der Collection sind regressionsgetestet (`tests/test_collection_editor.py`).
**Nachtrag 2026-07-10 — EffectLayerEditor:** Clamp-Grenzen konnten im Editor in
eine widersprüchliche Reihenfolge geraten. Min/Max werden nun beim Überschreiten
miteinander synchronisiert; inklusive Popout-Regression
`tests/test_effect_layer_editor.py`.
**Nachtrag 2026-07-10 — SceneEditor:** Minimal-Szene ohne Patch: Name, Timing,
Leeren und wiederholtes Popout/Andocken sind abgedeckt (`tests/test_scene_editor.py`).
**Nachtrag 2026-07-10 — ScriptEditor:** Modellbindung, Syntax-Highlighter und
Run/Stop eines Minimal-Scripts sind abgedeckt (`tests/test_script_editor.py`).

## 5. Offene, dokumentierte Niedrig-Prio-Punkte

- **RL-01** (neu, P3): Range-Lock „entfernen" lässt einen Identitäts-`ChannelModifier`
  (LINEAR, 0–255) im Manager zurück — funktional folgenlos (Identität), nur Hygiene/UI-Rest.
  Fix-Skizze: im „Lock entfernen"-Zweig (`channel_range_lock_dialog.py:_on_accept`) den
  Eintrag ganz entfernen, wenn er ausschließlich wegen des Locks existiert
  (`curve==LINEAR and not custom_lut`).
- **OUT-03** (bestehend): Art-Net „Startuniversum"-Feld nutzbar machen (externe
  Universe-Nummer statt fix `univ_num-1`) — bewusst zurückgestellt.

---
*Erzeugt im vollautonomen Loop-Modus. Methodik: automatisierte Smoke-Tests +
Multi-Agent-Inventar (22 Agenten) + adversariale Bug-Verifikation (6 Agenten). Alle
Zähler aus dem Lock-Runner-Gate (`tools/verify_loop.ps1`, headless offscreen).*
