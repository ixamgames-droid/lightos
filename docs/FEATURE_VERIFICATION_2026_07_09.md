# Feature-Verifikation LightOS — Sweep 2026-07-09

> Auftrag (Robin): „Alle Funktionen der Software mit dem Computer beweisen/überprüfen —
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

## 6. Live-Durchlauf 17.11.2026 (Linux, echter Fenster-Server, echte Eingaben)

Rest von QA-LIVE: Effect-Layer-Editor und Web-Remote-/Web-Server-Lifecycle. Die
echte App lief in einem abgeschotteten X-Server (1600×900, Fenstermanager metacity)
im Probelauf (Wegwerf-Datenordner, Ausgabe gesperrt — Titel „PROBELAUF“, Banner
„Probenmodus — es wird kein DMX gesendet“). Bedient wurde mit echten Maus- und
Tastatur-Ereignissen (XTEST), jeder Schritt mit mindestens einem Bildschirmfoto des
Ergebnisses.
Testshow: `tools/build_demo_rgb_par.py` (4 RGB-PAR, 3 Kanäle, Adressen 1/4/7/10,
Cueliste „Demo-Show“ mit 4 Cues) in eine Wegwerf-Datei; für Teil A wurde ihr per
Skript ein leerer Layered-Effekt „QA Layer“ (Geräte 1–4) hinzugefügt, weil die
Oberfläche keinen leeren Layered-Effekt anlegen kann (Befund FM-79). Web-Zugriff nur
über `127.0.0.1` (curl mit Cookie-Datei als Client). Die Fotos liegen lokal, nicht im
Repo.

### A. Effect-Layer-Editor (18 Schritte)

| # | Getan | Erwartet | Gesehen | Urteil |
|---|---|---|---|---|
| 1 | Prog → Snapshots → Bibliothek: „QA Layer“ doppelt angeklickt | Effekt startet (Bibliothek: Doppelklick = Start) | Kontextmenü bietet danach „Stop“ an | ok |
| 2 | Rechtsklick → „Bearbeiten…“ | Editor-Dialog öffnet | Dialog „Bearbeiten: QA Layer“, Target intensity, Base 0,50, Geräte 1,2,3,4, keine Layer | ok |
| 3 | Jede angebotene Layer-Art über die Auswahl + „Layer hinzufügen“ angelegt (12 Arten; PhaseOffset wird bewusst nicht mehr angeboten, BH-PHASEOFF) | 12 Einträge in der Liste | Constant, Sin, Cos, Triangle, Saw, Square, Random, Ramp, Multiply, Add, Clamp, Map (Map einmal doppelt durch den letzten Klick) | ok |
| 4 | „⤢ Großes Fenster“ (Popout 1) | eigenes Fenster mit demselben Inhalt | Fenster „Effekt-Layer-Editor“ 760×863, alle Layer sichtbar | ok |
| 5 | Doppeltes Map markiert → „Löschen“ | Eintrag verschwindet | 12 Einträge, Map einmal | ok |
| 6 | Clamp markiert → Eigenschaften | nur Min/Max (Grenzen-Typ) | Min 0,00 / Max 1,00 | ok |
| 7 | Clamp: Max = 0,3, dann Min = 0,8 (Min > Max) | Grenzen bleiben widerspruchsfrei | Max wird auf 0,80 nachgezogen (Min 0,80 / Max 0,80) | ok |
| 8 | Clamp: Max = 0,9, Min = 0,1 | Werte bleiben stehen | 0,10 / 0,90 | ok |
| 9 | Clamp → „Runter“ | Clamp unter Map, Auswahl wandert mit | Reihenfolge … Add, Map, Clamp; Clamp markiert, Werte unverändert | ok |
| 10 | Clamp → „Hoch“ | Clamp wieder über Map | … Add, Clamp, Map | ok |
| 11 | Neun Layer nacheinander markiert und gelöscht | Rest Sin, Multiply, Clamp | genau diese drei, in dieser Reihenfolge | ok |
| 12 | Sin: Amplitude 0,5, Frequenz 0,25 Hz, Phase je Gerät 1,57 | Felder übernehmen | Werte stehen nach Tab | ok |
| 13 | „Play“, Popout schließen (Andocken 1), Dialog zu, E/A → DMX Monitor | Ausgabe-Werte im Monitor | Target „intensity“: alle Kanäle 0 — die Test-PAR haben keinen Dimmerkanal (siehe Nebenbefund FM-79) | Hinweis |
| 14 | Popout 2: Base Value 0,6 → Fenster schließen; Popout 3: Multiply markiert | Änderung überlebt Andocken/Abdocken | Base 0,60 nach erneutem Popout, Multiply zeigt Faktor 1,00 | ok |
| 15 | Target auf color_r, Dialog zu, DMX Monitor zweimal fotografiert | Rot-Kanäle laufen phasenversetzt zwischen 0,1 und 0,9 | Kanäle 1/4/7/10: 35/201/229/104, kurz darauf 218/229/88/43; Grün/Blau 0; nie über 229 (= 0,9) | ok |
| 16 | Editor erneut, Popout 4, „Stop“, andocken, schließen, DMX Monitor | alle Kanäle 0 | Kanäle 1–12 alle 0 | ok |
| 17 | Datei → Speichern | Datei wird geschrieben | Show-Datei enthält „QA Layer“: target color_r, base 0,6, Sin(0,5/0,25 Hz/Phase je Gerät 1,57), Multiply(1,0), Clamp(0,1–0,9) | ok |
| 18 | Datei → Zuletzt verwendet → Show neu laden, Editor öffnen | Effekt unverändert | Target color_r, Base 0,60, Sin/Multiply/Clamp, Clamp 0,10/0,90; Kontextmenü „Start“ (nach dem Laden gestoppt) | ok |

### B. Web-Remote / Web-Server-Lifecycle (16 Schritte)

| # | Getan | Erwartet | Gesehen | Urteil |
|---|---|---|---|---|
| 1 | Ausgabe → „Web-Interface (Port 5000)“ | Server startet, Dialog | Dialog „Web-Interface läuft — nur dieser PC (127.0.0.1:5000)“, Statuszeile „Web: :5000 OK“, Port lauscht nur auf 127.0.0.1 | ok |
| 2 | Dialog → Erweitert → „Feste Fernbedienung“ an | fester Link mit Schlüssel | Link `http://127.0.0.1:5000/?k=…` erscheint | ok |
| 3 | Client 1 ruft den Link auf, dann `/api/status` | Seite 200, Status-JSON | 200; 1 Cueliste (4 Cues), 4 Geräte, Executor-Fader 1,0 | ok |
| 4 | Client 1: GO | quittiert, Cue 1 aktiv | `{"ok":true,"licht":true,"liste":"Demo-Show"}`; Playback: Cue 1.0 aktiv | ok |
| 5 | Client 1: GO | Cue 2 | „Cue 2.0 — Warm White“ aktiv, nächste 3.0 | ok |
| 6 | Client 1: BACK | Cue 1 | „Cue 1.0 — Blackout“ aktiv | ok |
| 7 | Client 1: Blackout an; leerer Körper | an; leer abgewiesen | `{"blackout":true}`, BLACKOUT-Knopf rot; leerer Körper → `anfrage_ungueltig` (nichts geändert) | ok |
| 8 | Client 1: Blackout aus | aus | `{"blackout":false}`, Knopf wieder normal | ok |
| 9 | Client 2 ohne Schlüssel: STOP | abgewiesen | 403 Forbidden | ok |
| 10 | Client 2 mit Schlüssel: STOP | quittiert, Liste gestoppt | `ok:true`, keine Cue-Zeile mehr markiert | ok |
| 11 | Client 1: Executor 1 Fader 0,5 | Engine 0,5, Pult zeigt 50 % | `/api/status` meldet 0,5 — der Fader in der Executor-Leiste bleibt sichtbar auf 100 % (auch nach 2 s) | **Befund WEB-16** |
| 12 | `/konsole` abrufen | Seite antwortet | 200 | ok |
| 13 | Menü: Web-Interface aus | Port zu, Client bekommt Fehler | „Web: aus“, Port frei, Client: Verbindung abgelehnt | ok |
| 14 | Fremdes Programm belegt 127.0.0.1:5000, Menü: Web-Interface an | verständliche Meldung, App läuft weiter | „Port 5000 ist belegt — … Das Web-Interface wurde NICHT gestartet; LightOS laeuft weiter …“, „Web: aus“ | ok |
| 15 | Blocker beendet, erneut einschalten; alter Client; Link neu öffnen | wieder erreichbar | „Web: :5000 OK“; alter Sitzungs-Cookie 403 (neuer Sitzungsschlüssel je Start, gewollt), nach erneutem Link-Aufruf GO ok; nach Show-Wechsel antwortet `/api/status` weiter | ok |
| 16 | Datei → Beenden bei laufendem Server | Prozess endet, Port frei | kein Prozess mehr, Port 5000 nicht mehr belegt, Client: Verbindung abgelehnt | ok |

**Folgebefunde (eigene Items):** WEB-16 (Executor-Fader aus dem Web wird im Pult nicht
nachgezogen), FM-79 (leerer Layered-Effekt in der Oberfläche nicht anlegbar;
Nebenbefund Target „intensity“ auf Geräten ohne Dimmerkanal bleibt stumm).
**Randnotiz Testumgebung:** Der zweite Aufruf von „Show öffnen“ zeichnete im
abgeschotteten X-Server keinen Inhalt (leerer Rahmen, Eingaben kamen an); ein Fehler
der App ist das nicht nachweislich — neu geladen wurde über „Zuletzt verwendet“.
**Gegenprobe (zweite, unabhängige Sitzung, gleicher abgeschotteter X-Server):** A2/A4,
A7–A10, A13–A16 mit der gespeicherten Show wiederholt — gespeicherter Stand (color_r,
Base 0,60, Sin/Multiply/Clamp 0,10–0,90) kommt zurück, Min > Max zieht Max nach,
Hoch/Runter und Andocken behalten den Stand, Rot-Kanäle 157/25/148/229 (Paare 1/3 und
2/4 ergänzen sich zu 2 × Base, Clamp-Grenzen 25 und 229), nach Stop alle 0. B1–B4,
B7, B9, B11, B13 und B16 wiederholt — gleiche Antworten; WEB-16 nachgestellt
(`/api/status` 0,5, Regler bleibt oben).

---
*Erzeugt im vollautonomen Loop-Modus. Methodik: automatisierte Smoke-Tests +
Multi-Agent-Inventar (22 Agenten) + adversariale Bug-Verifikation (6 Agenten). Alle
Zähler aus dem Lock-Runner-Gate (`tools/verify_loop.ps1`, headless offscreen).*
