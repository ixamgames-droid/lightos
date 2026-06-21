# BPM-Manager — Umsetzungsplan (eigene BPM-Erkennung + Tab + VC)

> **Stand: 2026-06-16.** Grundlage: verifizierter Ist-Stand von `core/engine/bpm_manager.py`,
> `core/audio/beat_detector.py`, `core/audio/capture.py`, `core/audio/offline_analysis.py`,
> `core/audio/os2l.py`, `core/audio/media_player.py`, `ui/main_window.py`, `ui/views/audio_input_view.py`,
> `ui/views/spectrum_bars.py`, `ui/virtualconsole/*` (Multi-Agent-Audit + adversariale Gegenprüfung).
>
> **Entscheidungen des Nutzers (2026-06-16):**
> 1. **Quellen:** Interner Player **und** PC-Audio (Spotify etc.) werden gemeinsam über **PC-Loopback**
>    erfasst (der Player spielt über die PC-Soundkarte); **externes Mikrofon/Line-In** als separate
>    Eingabe-Quelle. Kein eigener QMediaPlayer-Dekoder-Abgriff (Loopback genügt).
> 2. **VC: voll** — Nudge-Buttons (±1/±5/±10), Auto/Manual-Umschalter, APC-LED-Feedback.
> 3. **AUTO standardmäßig an, Capture startet sofort beim Programmstart.**

---

## ✅ Umsetzungsstand (2026-06-16)

**Vollständig umgesetzt und getestet** — Voll-Suite **1298 grün** (+358 Subtests). Alle 8 Arbeitspakete erledigt; eine adversariale Multi-Agent-Review (28 Agenten) lief über den Gesamt-Diff, alle bestätigten Befunde wurden behoben:
- **Leader thread-sicher:** Single-Beat-Emitter-Transitions unter RLock + Thread-Identitäts-Guard im `_loop` (kein Doppel-Timer/Doppel-Beat mehr); `request_bpm` mit Audio-Vorrang-Präzedenz (OS2L/Datei übersteuern laufende AUTO-Erkennung nicht mehr).
- **Capture robuster:** Geräte-Neuauflösung beim Quellenwechsel (kein hängendes Alt-Mikro), Geräteverlust-Erkennung mit `last_error` (unter Lock) statt stummem Dauerlauf.
- **Persistenz/UI:** OS2L-Quelle über Neustart korrekt wiederhergestellt; OS2L-Server wird beim Wechsel auf Audio gestoppt; Detektor-`reset()` bei Quellenwechsel; Top-Bar-Beat-Flash off-by-one behoben; Audio-Input-Checkbox spiegelt Live-Zustand.
- **Tests:** `tests/test_bpm_leader.py`, `tests/test_bpm_view.py`, `tests/test_vc_bpm.py` + conftest-Cleanup-Fixture für den BPM-Timer.

**Offen (bewusst, Folgeaufgaben):** `tempo_bus.py` (Bus `bpm_global`) ruft `get_bpm_manager().set_bpm()` direkt → umgeht Lock/Präzedenz; `AudioInputView`-Detektor-Parameter überschneiden sich mit dem BPM-Tab (volle Konsolidierung offen).

---

## 0. Leitidee / Architektur

- **Genau ein** globaler Tempo-„Leader": die Singleton-Instanz aus `get_bpm_manager()`
  (`core/engine/bpm_manager.py`). Tab, Top-Leiste, VC **lesen/schreiben nur über ihn** — kein
  eigener BPM-Zustand.
- Der `BPMManager` bleibt **reines Python (kein Qt)**, damit Engine-Threads ihn nutzen können.
  Qt-Marshalling passiert ausschließlich in der UI (Muster `_bpm_changed_sig` in `main_window.py`).
- **Drei Quellen, eine Wahrheit, klare Präzedenz:**
  `MANUAL (Tap/Nudge/Lock) ▸ OS2L (VirtualDJ) ▸ AUTO (Audio-Detektor) ▸ Datei-/Tag-Fallback`.
  AUTO ist Default-an, wird aber von einer manuellen Aktion oder einem Lock überstimmt.
- **Ein** Beat-Emitter per Konstruktion (siehe WP-1): der Timer `_loop()` ist die **einzige**
  Beat-Quelle; der Audio-Pfad aktualisiert nur die BPM. Das beseitigt Doppel-Beats.

---

## 1. Bereits vorhanden (wiederverwenden — nicht neu bauen)

| Baustein | Datei / Symbol |
|---|---|
| Globaler Leader: BPM, **Tap-Tempo** (4-Intervall), Timer-Beat-Broadcast, schaltet Chaser + Cuelisten beat-synchron | `core/engine/bpm_manager.py` → `BPMManager`, `tap()`, `set_bpm()`, `subscribe_beat/bpm_change()`, `use_audio_source()` |
| Audio-Beat-Detektor: FFT Bass-Band 40–180 Hz, adaptive Schwelle, `set_sensitivity()`, `get_bpm()`, 8-Band-Spektrum | `core/audio/beat_detector.py` |
| **WASAPI-Loopback-Capture** (PC-Wiedergabe abgreifen) via `soundcard`-Lib | `core/audio/capture.py` |
| Offline-BPM-Analyse (Autokorrelation, **Oktav-Faltung ≥90 BPM**) | `core/audio/offline_analysis.py` → `analyze_bpm()` |
| OS2L-Server (VirtualDJ/Mixxx, Port 1234) | `core/audio/os2l.py` |
| Audio-Tuning-UI (Sensitivity, Bass-Band, Cooldown, Device-Combo, Live-Meter, Beat-Flash) | `ui/views/audio_input_view.py` |
| 8-Band-Spektrum-Widget | `ui/views/spectrum_bars.py` |
| **Top-Leiste: BPM-Label + Beat-Punkt + Tap-Button** (Zahl wird oben schon gezeigt) | `ui/main_window.py` → `_lbl_bpm`, `_bpm_indicator`, `_btn_tap`, `_bpm_changed_sig` |
| **VC fertig: Tap** (`ButtonAction.TAP`), **Audio-Toggle** (`ButtonAction.AUDIO_BPM`), **BPM-Fader** (`SliderMode.BPM`) | `ui/virtualconsole/vc_button.py`, `vc_slider.py` |
| VC-Widget-Registry + Serialisierung; Subscribe-Muster | `ui/virtualconsole/vc_canvas.py` (`WIDGET_REGISTRY`), `vc_song_info.py` |

## 2. Abgrenzung gegen den bestehenden Musik-Tab (keine Doppelung)

- **Musik-Tab** (`music_view.py`): bleibt **track-zentriert** — Playlist, Transport, Datei-/Tag-BPM.
- **Neuer BPM-Manager-Tab**: **leader-zentriert** — Live-Detektion, Quellenwahl, AUTO/MANUAL,
  Grenzen/Smoothing/Sensitivity, Tap/Nudge/Lock, Monitor. Zeigt, **welche Quelle** gerade führt.
- **`AudioInputView`** bleibt rohe Capture-Diagnose. Alle drei nutzen **dieselben Singletons** —
  **kein zweiter Capture-Stream** (sonst WASAPI-Block). Die Live-Sektion von `AudioInputView` wird
  ein dünnes Embed des neuen Monitors (oder umgekehrt) — keine drei identischen Meter-Blöcke.

---

## 3. Arbeitspakete (Backend zuerst, jedes einzeln auslieferbar)

### WP-1 — Leader-Kern: Quellen-Präzedenz, Modus, Lock, Nudge, Single-Beat-Emitter
**Dateien:** `core/engine/bpm_manager.py` **+ die drei bestehenden Aufrufer** (kritisch — sonst
greift die Präzedenz nicht):
- Neue zentrale API **`request_bpm(bpm, source)`** mit Präzedenztabelle
  `MANUAL/Lock ▸ OS2L ▸ AUTO ▸ Datei-Fallback`. `set_bpm()` bleibt nur noch der **tiefe, geklemmte
  Setter ohne Moduswechsel**.
- **Aufrufer umstellen:** `os2l.py` `_push_bpm_to_manager` (`source="os2l"`),
  `media_player.py` `_apply_track_bpm` (`source="file"`), `MusicShowDirector._ensure_bpm`.
- `BpmMode` (`AUTO`/`MANUAL`, Default **AUTO**), `set_mode()`, `set_locked()`/`is_locked`,
  `nudge(±delta)` (setzt MANUAL), `current_source`.
- **Single-Beat-Emitter:** der Timer `_loop()` ist die **einzige** Beat-Quelle. `_on_audio_beat()`
  ruft **kein** `_emit_beat()` mehr, sondern nur noch `_apply_detected_bpm()`.
- `_apply_detected_bpm()`: Lock prüfen → nur in AUTO schreiben → auf Grenzen klemmen → Smoothing →
  **`_emit_bpm_change()`** (heute aktualisiert sich das Label bei Audio-BPM nicht).
- Bestehender `_on_audio_beat()`-Hinweis: er klemmt bereits inline (Z. 184); die echten Lücken sind
  fehlendes `_emit_bpm_change()` + fehlende Timer-Zustands-Verwaltung — genau das fixt `_apply_detected_bpm()`.
- **Tests:** (a) OS2L/Track-Load kippt **nicht** in MANUAL; (b) genau 1 Beat/Intervall beim
  AUTO↔MANUAL-Wechsel bei aktivem Audio; (c) `set_bounds(80,160)`+detektiert 200 → 160;
  (d) `set_locked(True)` friert BPM bei Audio-Beats ein; (e) `nudge(+5)` setzt MANUAL.

### WP-2 — Detektor: konfigurierbare Grenzen, Oktav-Faltung, Smoothing, Confidence
**Datei:** `core/audio/beat_detector.py`
- Konfigurierbare `min_bpm`/`max_bpm` (statt hartem 20–300 in `get_bpm`, Z. 59) — die „Höhen und Tiefen".
- **Oktav-Faltung in die Grenzen** (×2 / ÷2), Logik aus `offline_analysis.analyze_bpm` (faltet ≥90)
  übernehmen — **nötig, nicht optional**, sonst landen halb/doppelt erkannte Tempi außerhalb der Grenzen.
- Smoothing (EMA) gegen Zappeln; `set_smoothing(0..1)`.
- **Confidence** aus Übereinstimmung aufeinanderfolgender `get_bpm()`-Schätzungen bzw.
  Autokorrelations-Peak-Schärfe — **nicht** naive Intervall-Varianz über `_beat_times` (das sind
  Onsets, keine Viertel → würde saubere 4/4-Tracks fälschlich als unsicher melden).
- **Tests:** synthetischer 75-BPM-Onset-Strom + Grenzen 120–200 → meldet ~150; Smoothing dämpft
  Sprünge; saubere Beats → hohe Confidence, jittrige → niedrige.

### WP-3 — Audio-Eingang: externes Line-In/Mikrofon zusätzlich zu Loopback
**Datei:** `core/audio/capture.py`
- Quellen-Modus `loopback` (PC-Audio inkl. internem Player + Spotify) **vs** `input`
  (externes Mikrofon/Line-In). Eingänge via `soundcard.all_microphones(include_loopback=False)` —
  **keine neue Abhängigkeit**. Namens-Kollisionen Loopback↔Input sauber kennzeichnen.
- `set_source_mode(mode, device_name)` (stoppt/startet Capture sauber wie `set_device`).
- `last_error()` + Status, damit der „stille Thread-Tod" (heute setzt `_run()` nur `_running=False`)
  in der UI sichtbar wird — sowohl in `AudioInputView` (zeigt schon „Status: läuft/gestoppt") als
  auch im neuen Tab.
- **Laufende Songs → BPM:** interner Player + PC-Audio laufen über die Soundkarte → vom Loopback
  erfasst. Externes Signal → Input-Modus. (Reicht für alle drei Wünsche.)
- **Tests:** `HAS_SOUNDCARD`-geschützt; Capture-Tests laufen unter **venv 3.14**
  (im Basis-Interpreter ist `soundcard` nicht importierbar). Fake-Chunk-Injektionspunkt für
  deterministische Detektor-Tests.

### WP-4 — Persistenz + AUTO-beim-Start
**Datei:** `core/app_state.py` / `ui_prefs.json`-Muster
- **Eine** autoritative Grenzen-Quelle (persistiert), beim Start in den Detektor gespielt —
  **einmal klemmen** (im Detektor), nicht dreifach (Manager/Detektor/Settings).
- Block `bpm_settings`: `mode_default, min_bpm, max_bpm, sensitivity, smoothing, source_mode,
  input_device, auto_default` (Default `True`).
- **AUTO sofort beim Start:** beim App-Start `set_mode(AUTO)` + `use_audio_source(True)` →
  WASAPI-Loopback-Capture läuft ab Programmstart. **Diesen Pfad direkt nach WP-3 validieren**
  (vor der Persistenz-Feinarbeit), da Capture/Mode-Interaktion früh getestet sein muss.

### WP-5 — Neuer View: BPM-Monitor (Anzeige-Hälfte)
**Datei (neu):** `ui/views/bpm_manager_view.py`
- Großes Live-BPM-Readout (Subscribe `subscribe_bpm_change`).
- Beat-Phase-Indikator „1·2·3·4" (`_beat_index % 4`).
- Beat-Flash-Punkt (Stil aus `main_window._bpm_indicator`).
- **Confidence-Balken** (`BeatDetector.get_confidence()`, QTimer ~100 ms).
- Spektrum (Reuse `SpectrumBars`, **kein** neuer Capture).
- Aktive-Quelle-Anzeige („AUTO/Audio", „MANUAL/Tap", „OS2L", „🔒 Locked").
- Alle Callbacks über Qt-Signal in den Mainthread (Audio-/Timer-Thread → nie direkter Widget-Zugriff).
- **Eigenes Smoke-Harness** (`docs/_walkthrough/`-Muster): Tab öffnet ohne Exception, Readout
  aktualisiert bei `set_bpm()` — **schon in WP-5**, nicht erst WP-6.

### WP-6 — BPM-Manager-Tab: Einstellungen + Tab-Registrierung
**Dateien:** `ui/views/bpm_manager_view.py` (erweitern), `ui/main_window.py`
- **AUTO/MANUAL-Umschalter** → `set_mode()` / `use_audio_source()`.
- **Quellen-Selector** (RadioGroup): *PC-Audio (Loopback)* / *Externer Eingang* (Device-Combo aus
  `list_input_devices()`) / *OS2L* → `AudioCapture.set_source_mode()` bzw. OS2L-Toggle.
- **Min/Max-BPM** (zwei Slider „Höhen und Tiefen") → `set_bounds()` (eine Quelle, in Detektor gespielt).
- **Sensitivity** (0.5–3.0) → `set_sensitivity()`; **Smoothing** (0–1) → `set_smoothing()`.
- **Tap** → `tap()`; **Nudge ±1/±5/±10** → `nudge()`; **Lock-Toggle** → `set_locked()`.
- **Tab-Registrierung in `main_window.py`:** 8. Eintrag in der `sections`-Liste; im Stack
  `BpmManagerView` als Index 7; `Ctrl+8` entsteht automatisch (Shortcut-Schleife ist dynamisch).
  Kiosk-Auto-Hide + sonstige fest erwartete „7" prüfen.
- **Verifikation:** App startet, 8 Section-Buttons, Ctrl+8 springt zum BPM-Tab; alle Regler wirken
  sofort auf Leader/Detektor (BPM-Sprung in Top-Bar sichtbar). Voll-Suite grün (Live-App vorher
  schließen — COM3-Hang; Tests auf separater DB `LIGHTOS_SHOW_DB`).

### WP-7 — Top-Leiste: Quellen-/Modus-Badge
**Datei:** `ui/main_window.py`
- Die **Zahl oben existiert schon** (`_lbl_bpm`). Neu: kleines Badge `_lbl_bpm_mode`
  („AUTO" / „MAN" / „🔒") + aktive Quelle, über neues `_bpm_mode_sig = Signal(str)` (vorhandenes
  Marshalling-Pattern). Klick auf Badge togglet AUTO/MANUAL; Klick auf `_lbl_bpm` springt zum BPM-Tab.
- **Verifikation:** Tap → Badge „MAN"; AUTO-Toggle im Tab → Badge „AUTO". Cross-Thread sauber.

### WP-8 — Virtual Console (voll)
**Dateien:** `ui/virtualconsole/vc_bpm_display.py` (neu), `vc_canvas.py`, `vc_button.py`,
APC-Feedback (`core/midi/apc_mk2_feedback.py`).
- `VCBpmDisplay(VCWidget)`: Live-BPM + aktive Quelle; Subscribe im `__init__`,
  **`unsubscribe` im Destruktor** (Callback-Leak vermeiden — Muster `vc_song_info._connect_player`).
  `to_dict()/apply_dict()` (mind. Geometrie). Registrierung in `WIDGET_REGISTRY` via `_register()`.
- Neue `ButtonAction`-Werte: `BPM_NUDGE_UP` / `BPM_NUDGE_DOWN` (Delta-Param) + `BPM_MODE_TOGGLE`,
  Handler nach Muster `TAP`/`AUDIO_BPM` → `nudge(±d)` bzw. `set_mode(...)`.
- **APC-LED-Feedback** für Modus/Lock (konsistent zum bestehenden AUDIO_BPM-Cyan-Feedback).
- **Verifikation:** Widget hinzufügen → Live-BPM tickt; Nudge ±5 ändert Leader; Layout-JSON
  Round-Trip (speichern/laden) ohne Crash (neue VC-Typen brauchen `to_dict/apply_dict`).

---

## 4. Risiken (verifiziert)
- **Doppelter Capture-Stream blockiert** → alle Views denselben Singleton; nie zweiter Stream.
- **Cross-Thread-Widget-Zugriff** → ausnahmslos über Qt-Signal (vgl. MIDI-Page-Crash).
- **WASAPI nur Windows** (Zielsystem Win 11 — ok, dokumentieren; keine Degradierung auf macOS/Linux).
- **Stiller Capture-Thread-Tod** → `last_error()` + Statusanzeige (WP-3) end-to-end.
- **Präzedenz-Bug (Alt-Code):** `set_bpm()` wird bereits von OS2L/Media-Player/VC-Fader aufgerufen —
  deshalb **niemals** `set_bpm()` selbst den Modus auf MANUAL kippen lassen; nur `request_bpm`/`nudge`.
- **Doppel-Beats (Alt-Code):** im AUTO-Modus feuerten Timer **und** `_on_audio_beat()` Beats →
  WP-1 macht den Timer zur einzigen Beat-Quelle.
- **`media_player._apply_track_bpm`** hat schon eine eigene Vorrang-Logik („OS2L gewinnt über
  couple_bpm", „skip wenn `audio_active`") — muss von `request_bpm`/der neuen Präzedenz **subsumiert**
  werden, nicht parallel laufen.
- **VC-Callback-Leak:** `VCBpmDisplay` muss bei Zerstörung sauber `unsubscribe`.

## 5. Reihenfolge
WP-1 → WP-2 → WP-3 → (AUTO-Start-Pfad validieren) → WP-4 → WP-5 → WP-6 → WP-7 → WP-8.
Jedes WP endet mit grüner Voll-Suite (Live-App vorher schließen, Tests auf `LIGHTOS_SHOW_DB`;
Capture-Tests unter venv 3.14, sonst `HAS_SOUNDCARD`-Guard).
