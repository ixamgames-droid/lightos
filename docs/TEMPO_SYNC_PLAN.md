# Tempo-Sync-Plan — unterschiedliche Geschwindigkeiten, synchronisiert & BPM-koppelbar

> **Status: Phasen 1–5 implementiert & getestet (2026-06-16).** Engines (1–4) + die VC-Bedienung (Phase 5) stehen; nur der externe Analyzer (Phase 6) folgt.
> Ziel: Effekte auf unterschiedliche, unabhängige Geschwindigkeiten legen (Tap/Speed-Regler),
> sie aber zueinander **phasen-synchronisieren** (gleich starten, harmonische Verhältnisse),
> alles an BPM / den künftigen eigenen Wave-Analyzer koppelbar, in der Virtuellen Konsole bedienbar.

---

## 0. Umsetzungsstand (2026-06-16)

**Fertig & grün (27 Tempo-Tests + 215 Regressionstests grün, Pyright sauber):**
- **Phase 1 — TempoBus-Kern:** `src/core/engine/tempo_bus.py` (NEU) — `TempoBus`/`TempoBusManager`/`get_tempo_bus_manager()`, `TempoSource`-Protocol, `advance_frame(dt)` einmal pro Frame in `app_state._render_frame`. (`tests/test_tempo_bus.py`, 18)
- **Phase 2 — Function-Felder + Persistenz:** 4 Felder (`tempo_bus_id`/`tempo_multiplier`/`phase_offset`/`sync_group`) + privates `_beat_anchor` auf `Function`; generischer Loader in `FunctionManager.from_dict`; `tempo_buses`-Block in `show_file.py` (save/load/reset). (`tests/test_tempo_sync_persistence.py`, 4)
- **Phase 3 — RGB-Matrix Bus-Sync:** `RgbMatrixInstance._advance_step()` (bus-synchron vs. byte-identischer Free-Run), `write()/tick()` umgestellt, `sync_phase()/_on_start()` re-ankern. Rot/Grün-↔-2×-Dimmer-Determinismus als Test. (`tests/test_tempo_sync_matrix.py`)
- **Phase 4 — EFX + Chaser + Sequenz Bus-Sync:** EFX `_sync_from_bus()` (forward/backward/bounce/one-shot/RANDOM korrekt abgebildet); Chaser `_advance_from_bus()` + Sequenz `_bus_steps_to_advance()` (1 Step je `beats_per_step` Beats × Multiplier → ×2/÷2); `sync_phase()` auf allen. (`tests/test_tempo_sync_efx_chaser.py`)
- **Review-Fixes (adversarial):** Default-Bus = monotone Integration (kein absoluter Beat-Index-Sprung); `external` klemmt Phase, Beat-Callback zählt; `round(…,9)` gegen die Float-Kante am Beat; EFX One-Shot-Bounce hält bei 0 statt endlos zu schwingen; One-Shot-forward auf [0,1] geklemmt. Externer Within-Frame-Latch = **Phase-6-TODO**.

**✅ Phase 5 — VC-Bedienung ERLEDIGT (2026-06-16):** `ButtonAction.TAP_BUS/SYNC_BUS/ARM_BUS` + `tempo_bus_id` (vc_button.py), `SliderMode.TEMPO_BUS` (vc_slider.py), neues `VCBusSelector` (vc_bus_selector.py, setzt `armed_bus_id`), `VCSpeedDial`-Ziele `TEMPO_BUS` (Bus-BPM) + `TEMPO_BUS_MULT` (Half/Double via `effect_live.set_param("tempo_multiplier")`), `VCBpmDisplay` mit optionalem `tempo_bus_id` (GUI-Timer-Poll auf `bus.snapshot()`). Dazu der Smart-Drop-Dialog (`vc_effect_meta.py`/`smart_drop_dialog.py`/`apply_drop(interactive)`). Tests: `test_vc_tempo_widgets.py`, `test_vc_smart_drop.py`, `test_tempo_sync_vc_persistence.py`. Voll-Suite 1339 grün.

**Offen:**
- **Phase 6 — externe Quellen** (BeatDetector-/OS2L-Adapter + eigener Wave-Analyzer via `TempoSource`).

---

## 1. Was du willst (verstanden)

1. Mehrere **unabhängige Tempi** speichern — per Tap-Button und/oder Speed-Fader.
2. Effekte mit **unterschiedlichen** Geschwindigkeiten laufen lassen, sie aber **synchron starten** und in **festen Verhältnissen** (×2, ×½, ×4 …) halten.
3. Dein Kern-Beispiel: Farbmatrix wechselt **Rot↔Grün** (1 Wechsel pro Beat), Dimmer-Matrix macht **voll an / voll aus** doppelt so schnell — aber **phasen-gekoppelt**, sodass jeder Farbwechsel sauber mit „voll an" beginnt (nie „Rot + dunkel" mitten im Fade).
4. Jedes Tempo an **BPM** koppelbar — inkl. deines gerade live entstehenden **Wave-/Audio-Analyzers**, ohne den Plan später umbauen zu müssen.
5. Gilt für **viele Effekt-Typen**: RGB-Matrix, EFX, normale Chaser/Sequenzen — gleiche Show, verschiedene Speeds, mit **Abhängigkeiten** untereinander.
6. Steuer- und konfigurierbar aus der **Virtuellen Konsole**.

---

## 2. Ausgangslage im Code (kartiert)

- **Eine** zentrale Render-Schleife mit 44 Hz: `OutputManager._loop` (`output_manager.py:152`) → `AppState._render_frame(dt)` (`app_state.py:850`) → `FunctionManager.tick(..., dt)` (`function_manager.py:332`) → `f.write(universes, patch_cache, dt, registry)`.
- Das `dt` ist die **nominelle** Konstante `FRAME_INTERVAL = 1/44 s` (`output_manager.py:10/171`) — kein gemessener Wall-Clock-Delta.
- **Jeder zeitbasierte Effekt akkumuliert seine eigene Phase**, völlig unabhängig:
  - EFX: `self._phase += speed_hz * Function.speed * dt` (`efx.py:176/180`)
  - RGB-Matrix: `self._step += matrix_speed * Function.speed * dt` (`rgb_matrix.py:478`), Render via `_render(self._step)` (`:479/566`)
  - Carousel ist der **einzige** Effekt, der heute schon Phase aus Beats ableitet (`carousel.py:73-89`).
- **BPM** lebt separat in `BPMManager` (`bpm_manager.py:18`, Singleton `get_bpm_manager()`): eigener Daemon-Thread, der **diskrete Beats** broadcastet (`_emit_beat`, `:119`). Konsumenten: `audio_triggered` Chaser, `beat_sync` CueStack, Carousel. **EFX/Matrix lesen BPM überhaupt nicht.**
- **Es gibt heute keine Beat-Phase** (kein 0..1 „wie weit im Beat", kein Takt/Downbeat). Nur skalare BPM + Integer-Beat-Index.
- Prior Art, die wir verallgemeinern: EFX `phase_mode`/`phase_offset_deg`/`counter_rotate` (`efx.py:110/111/114`) = räumlicher Phasen-Versatz; RGB-Matrix `params['offset']` (`:576`); `sync_phase()`/`VCSpeedDial.sync()` (`rgb_matrix.py:360`, `vc_speedial.py:123`) = bestehender „auf 0 setzen"-Hook.

**Kernproblem:** Zwei Effekte mit „gleicher" Geschwindigkeit driften trotzdem auseinander (verschiedene Startzeiten, Frame-Jitter, Freeze) — es gibt **keine gemeinsame Uhr und keine Phasen-Kopplung**.

---

## 3. Kernidee — „Tempo-Buses" + kontinuierliche Beat-Position

Eine **neue Singleton-Klasse** `TempoBusManager` (neue Datei `src/core/engine/tempo_bus.py`), analog zu `get_bpm_manager()`. Sie verwaltet **benannte Uhren** („Buses"):

- Ein reservierter Bus **`"default"`** ist ein dünner Proxy über den bestehenden `BPMManager` → alle heutigen Beat-Konsumenten (Carousel, Chaser, CueStack) laufen unverändert weiter, sie sind implizit „auf dem Default-Bus".
- Zusätzliche **benannte Buses** (`A`, `B`, … oder frei benannt) = **unabhängige Tempi**. Das ist genau dein „mehrere unterschiedliche Geschwindigkeiten in derselben Show".

### `TempoBus` (Zustand lebt im Manager, NICHT in den Effekten)
```
bus_id        : str
source        : {"manual","tap","bpm_global","external"}
_bpm          : float          # 0 == aus / Free-Run
_beat_count   : int            # ganze Beats seit Bus-Start (Integer-Anteil)
_beat_phase   : float [0,1)    # NEU: Bruchteil in den aktuellen Beat hinein
_last_beat_mono : float        # monotonic-Zeit des letzten ganzen Beats (fehlt heute!)
_tap_times    : list[float]    # eigene Tap-Historie (gleiche Mathematik wie BPMManager.tap)
_lock         : RLock
```

**Die eine geteilte Größe**, die jeder synchronisierte Effekt liest:
```
position(bus) = _beat_count + _beat_phase     # kontinuierlich = „verstrichene Beats auf diesem Bus"
```
Atomar via `bus.snapshot() -> (bpm, beat_count, beat_phase, position)` unter dem Lock.

### Wie ein Effekt einen Bus referenziert — 4 neue gespeicherte Felder auf `Function` (Basis)
Direkt neben `speed`/`priority`/`env_*` (`function.py:74-94`), generisch geladen in `FunctionManager.from_dict` (`function_manager.py:482-508`) per `fd.get(key, default)` — **exakt** das Muster, mit dem schon `priority`/`env_*`/`folder` nachgerüstet wurden:

| Feld | Default | Bedeutung |
|---|---|---|
| `tempo_bus_id` | `""` | `""` = Legacy-Free-Run (heutiges Verhalten **byte-genau**) |
| `tempo_multiplier` | `1.0` | harmonisches Verhältnis zum Bus (UI: ×0.25 … ×4, Feld = freier Float) |
| `phase_offset` | `0.0` | Versatz in **Beats** des eigenen Zyklus (additiv, wie EFX `_fan_for` / Matrix `offset`) |
| `sync_group` | `""` | Effekte mit gleichem `(tempo_bus_id, sync_group)` re-ankern gemeinsam beim Sync |

Plus eine private, **nicht** gespeicherte Größe `self._beat_anchor` (Bus-Position beim letzten Sync/Start). `local_beats = position - _beat_anchor`.

### Frame-Verdrahtung — **ohne** Signatur-Änderung
Einmal pro Frame in `AppState._render_frame` (`app_state.py:850`), **direkt vor** `function_manager.tick(...)` bei `:879`:
```python
get_tempo_bus_manager().advance_frame(dt)   # läuft auf dem Render-Thread, snapshottet → race-frei
```
Die Effekte lesen den Bus **selbst** in ihrem bestehenden `write()`/`_advance` (`get_tempo_bus_manager().get(self.tempo_bus_id).snapshot()`). Damit bleibt der `f.write(universes, patch_cache, dt, functions)`-4-Argument-Vertrag **unangetastet** — alle ~9 Subtyp-Overrides + Tests kompilieren unverändert. (Das ist dasselbe „Singleton out-of-band lesen", das `Carousel.write` heute schon mit `get_bpm_manager()` macht — der risikoärmste Kanal.)

---

## 4. Die Sync-Mathematik — dein Beispiel, am echten Render-Code geprüft

Jeder zeitbasierte Effekt berechnet seine Position aus dem Bus statt aus einem privaten dt-Akku, **sobald** `tempo_bus_id != ""`:
```
bpm, beat_count, beat_phase, pos = bus.snapshot()    # pos = beat_count + beat_phase
local_beats = pos - self._beat_anchor                # Beats seit letztem Sync/Start
effect_pos  = local_beats * self.tempo_multiplier + self.phase_offset
```
Abbildung auf den **bestehenden** Phasen-Konsumenten jedes Subtyps (Render-Funktionen bleiben unverändert):
- **RGB-Matrix:** statt `self._step += rate*dt` → `self._step = effect_pos` (das `_render(self._step)` frisst genau diesen Float schon, `:479`). Free-Run bleibt byte-genau. Beide Pfade über einen Helper `_effective_step(dt)`, den `write()` **und** `tick()` (Preview) nutzen.
- **EFX:** `self._phase = effect_pos % 1.0` (RANDOM: `self._rand_progress = effect_pos`). `_values` unangetastet → Fan/`counter_rotate` legen sich weiter über die beat-gelockte Basis.
- **Chaser/Sequenz (diskret):** `step = int(local_beats * tempo_multiplier / beats_per_step)` — über die kontinuierliche Bus-Position, also gehen jetzt auch **×2 / ÷2** (heute kann `_emit_beat` nicht unterteilen).

### Dein Beispiel, durchgerechnet
- **Farbmatrix = COLORFADE**, Farben `[Rot, Grün]` → `L=2`. `_render_colorfade` (`rgb_matrix.py:1087`): `seg = int(p)%2`, `t = p-floor(p)`. ⇒ **1 Farbwechsel pro ganzem Phasenschritt**.
- **Dimmer-Matrix = STROBE**. `_render` STROBE (`rgb_matrix.py:665`): `on = int(p)%2==0`. ⇒ **ein voll-an/voll-aus = 2 Phasenschritte**.
- **Konfig:** beide `tempo_bus_id="A"`, gleiche `sync_group="S"`. Farbe `mult=1` ⇒ `p_color = local_beats`. Dimmer `mult=2` ⇒ `p_dim = 2·local_beats`.

> Bei **jedem** ganzen Farb-Beat (`local_beats` ganzzahlig) ist `p_dim` eine **gerade** ganze Zahl → `int(p_dim)%2==0` → **voll AN**, und ein frischer An/Aus-Zyklus beginnt **genau** am Farbwechsel. Einen halben Beat später ist `p_dim` ungerade → AUS.
> Weil **beide** aus **derselben** `bus.position()` und demselben `_beat_anchor` ableiten, fallen die Integer-Grenzen **immer** zusammen — unabhängig von Frame-Jitter oder Startzeit. Die „nie Rot + dunkel mitten im Fade"-Garantie gilt **konstruktiv**.

(Willst du am Wechsel einen **harten Schnitt** statt Crossfade: COLORFADE-Param `hold≈0.95` oder eine 2-Step-Chaser-Farbe — die Phasen-Kopplung ist identisch.)

```
Beat:        0       1       2       3       4
Farbe:      ROT     GRÜN    ROT     GRÜN    ROT      (mult ×1)
Dimmer:    AN AUS  AN AUS  AN AUS  AN AUS  AN AUS    (mult ×2, phasengleich)
            │       │       │       │       │
            └ jeder Farbwechsel startet mit „AN"
```

### „Sync" / Re-Trigger (dein „gleich starten")
Eine **Sync**-Aktion auf einen Bus (oder eine `sync_group`) macht atomar unter dem Bus-Lock:
1. **Re-Anchor:** für jede Funktion mit diesem `(tempo_bus_id[, sync_group])` → `self._beat_anchor = bus.position()` (nicht 0 — der Bus läuft weiter; durch Ankern auf „jetzt" startet `local_beats` aller Gruppen-Effekte gemeinsam bei 0). Verallgemeinert `VCSpeedDial.sync()`.
2. **Optional Bus-Downbeat:** `bus.reset_phase()` setzt `_beat_count=_beat_phase=0` → „jetzt ist die Eins".

Ergebnis: nach Sync haben alle Gruppen-Effekte gleichzeitig `local_beats=0` → COLORFADE `seg=0` (Rot) und STROBE „AN" starten **zusammen**.

### Free-Run-Fallback
Hat der Bus `bpm==0` (= aus), liefert `snapshot()` eine aus dt integrierte Position bei der Eigenrate des Effekts (× Multiplier) — synchronisierte Effekte **degradieren** auf heutiges Verhalten statt einzufrieren.

---

## 5. BPM-Quellen — inkl. deinem Live-Wave-Analyzer

Ein Bus bezieht BPM über `TempoBus.source`, alles durch ein `set_bpm()` (wie `BPMManager` manual/tap/audio bündelt):

1. **`manual`** — Wert von einem VC-Tempo-Fader / einer Zahl; Bus läuft frei mit `60/bpm`. **Pro Bus unabhängig** → das ermöglicht „mehrere Tempi gleichzeitig".
2. **`tap`** — `TempoBus.tap()` mit eigener Historie (gleiche bewährte Mathematik wie `BPMManager.tap`: Mittel der letzten 4 Intervalle, `TAP_WINDOW_SEC=2.0`). Vereint die heute **zwei** getrennten Tap-Implementierungen (`BPMManager.tap` vs. isoliertes `VCSpeedDial._tap`).
3. **`bpm_global`** — dünner Proxy über den bestehenden `BPMManager`. Der `"default"`-Bus ist dauerhaft das → null Migration.
4. **`external` / Live-Analyzer** — die **Zukunftssicherheit**. Ein winziges, duck-typed `Protocol`, das dein Analyzer später implementiert, **ohne** `tempo_bus.py` anzufassen:
   ```python
   class TempoSource(Protocol):
       def current_bpm(self) -> float: ...                  # 0 wenn unbekannt
       def register_beat(self, cb: Callable[[float], None]) -> None: ...  # cb(monotonic_ts) pro erkanntem Beat
       def beat_phase(self) -> float | None: ...            # OPTIONAL: kontinuierliche 0..1, sonst None
   ```
   `TempoBus.attach_source(src)`: pro Beat-Callback setzt der Bus `_last_beat_mono` und erhöht `_beat_count` (re-ankert die Phase auf den erkannten Beat); `advance_frame` interpoliert `_beat_phase` zwischen Beats aus `current_bpm`; liefert `src.beat_phase()` einen Wert, **überschreibt** er die Interpolation (kontinuierlicher Lock).
   **Sofort nutzbare Adapter** ohne Rework: `OS2L` empfängt heute schon `msg['pos']` (Beat-Position im Takt) und **verwirft** es (`os2l.py`) → `OS2LTempoSource` speist es direkt in `beat_phase()`. `BeatDetector` hat schon Onset-Timestamps + `get_bpm()` (`beat_detector.py`) → `BeatDetectorTempoSource` wrappt sein `subscribe(cb)`. Dein Analyzer implementiert dasselbe Protocol und ruft `bus.attach_source(...)` — fertig.

**Drift/Handoff-Sicherheit:** ein Bus hat **genau einen** maßgeblichen Beat-Anker (`_last_beat_mono`); Quellenwechsel re-seedet ihn atomar unter Lock → kein Phasen-Sprung bei manual↔tap↔external. `advance_frame` snapshottet einmal/Frame auf dem Render-Thread → Lesungen aus `write()` sind wertstabil, auch wenn Beat-Callbacks auf dem Audio-Thread landen.

---

## 6. Virtuelle Konsole

Neue/erweiterte Widgets erben von `VCWidget`/`VCButton`/`VCSlider` (für MIDI/Key-Teach **VCButton/VCSlider** bevorzugen — `VCSpeedDial` kann heute kein MIDI-Teach). Jedes bekommt ein `tempo_bus_id`-Feld (leer = „aktueller Bus" vom Bus-Selector).

1. **Tap-Tempo-Button** — `ButtonAction.TAP_BUS` (`vc_button.py:18`), Handler `…get(bus).tap()`, deutsches Label „Tap-Tempo (Bus)", Bus-Feld im Eigenschaften-Dialog. Erbt MIDI/Key-Teach + Pad-LED → APC-Pad tappt einen bestimmten Bus. (`ButtonAction.TAP` bleibt = globaler Bus.)
2. **Sync-Button** — `ButtonAction.SYNC_BUS`, `…get(bus).sync(group=…)` → re-ankert alle Funktionen der `(bus, sync_group)`, optional Downbeat-Reset. MIDI/Key-bindbare Verallgemeinerung von `VCSpeedDial.sync()`.
3. **Tempo-Fader** — `SliderMode.TEMPO_BUS` (`vc_slider.py:11`); `_apply` (`:139`) → `…get(bus).set_bpm(...)`, **wiederverwendet** Mapping/Clamps von `SliderMode.BPM` + range/invert + Soft-Takeover/Pickup. Der gewünschte „Speed-Regler", aber auf einen **benannten** Bus.
4. **Bus-Selector** — kleines `VCBusSelector`-Widget, setzt eine geteilte „aktueller Bus"-ID, die alle Tap/Sync/Tempo-Widgets mit leerem `tempo_bus_id` lesen (analog zur bestehenden `edit_slot`-Indirektion). Eine APC-Bank steuert den „scharf geschalteten" Bus.
5. **Pro-Effekt Multiplier + Bus** — über den bestehenden Param-Kanal: `tempo_bus_id`/`tempo_multiplier`/`phase_offset`/`sync_group` in `list_params/get_param/set_param` (Matrix `:1135`, EFX `:470`) — genau wie `offset`/`speed`. Dann setzen `EFFECT_PARAM`-Fader/Encoder sie ohne neue Verdrahtung; die Matrix-/EFX-Editoren bekommen Combo „Tempo-Bus", Selector „×0.25…×4", Spin „Phasen-Versatz", `sync_group`-Feld.

**Persistenz:** Tempo-Buses als **neuer** Top-Level-Block `show['tempo_buses']` in `show_file.py` (`save_show ~:254-278`, `load_show` mit Default `[]` — additiv, keine Versions-Verzweigung). VC-Widgets round-trippen automatisch über `VCCanvas.to_dict/from_dict` (Registry in `vc_canvas.py`).

---

## 7. Betroffene Dateien (Überblick)

| Datei | Änderung |
|---|---|
| `src/core/engine/tempo_bus.py` **(NEU)** | `TempoBus` + `TempoBusManager` + `get_tempo_bus_manager()`; `set_bpm/tap/sync/reset_phase/position/snapshot/advance_frame/attach_source`; reservierter `default`-Bus |
| `src/core/engine/bpm_manager.py` | **additiv read-only:** `_last_beat_mono` speichern + `beat_phase()`/`beats_per_bar`/`bar_phase()` |
| `src/core/engine/function.py` | 4 Felder + `_beat_anchor` in `__init__`; in `to_dict` (`:171`) emittieren |
| `src/core/engine/function_manager.py` | 4 Felder generisch in `from_dict` (`:482-508`) laden; `tick()` **unverändert** |
| `src/core/app_state.py` | 1 Zeile vor `tick` (`:879`): `get_tempo_bus_manager().advance_frame(dt)` |
| `src/core/engine/rgb_matrix.py` | `_effective_step(dt)`-Helper; synced → `_step=effect_pos`, sonst byte-genau; `sync_phase()` re-definiert; Tempo-Params exponieren |
| `src/core/engine/efx.py` | `_advance` synced → `_phase=effect_pos%1.0` (RANDOM `_rand_progress`); `_on_start` setzt Anchor; Params + Serialisierung |
| `src/core/engine/chaser.py` + `sequence.py` | Bus-synced Step-Index (×2/÷2, Downbeat-Reset); Sequenz bekommt Beat-Modus |
| `src/core/engine/carousel.py` | optional: `sync_to_beat` auf benannten Bus umlenken (niedrige Prio) |
| `src/core/show/show_file.py` | `show['tempo_buses']` save/load, Default `[]` |
| `src/ui/virtualconsole/vc_button.py` | `TAP_BUS` + `SYNC_BUS` + Labels/Handler/Bus-Feld |
| `src/ui/virtualconsole/vc_slider.py` | `SliderMode.TEMPO_BUS` + Label/Dispatch (BPM-Mapping wiederverwenden) |
| `src/ui/virtualconsole/vc_bus_selector.py` **(NEU)** + `vc_canvas.py` | Bus-Selector + Registry |
| `src/ui/views/rgb_matrix_view.py` + `efx_view.py` | Editor: Tempo-Bus-Combo, ×0.25..×4, Phasen-Versatz, `sync_group` |

---

## 8. Roadmap (in Abhängigkeitsreihenfolge, jede Phase einzeln testbar)

**Phase 1 — TempoBus-Kern + kontinuierliche `beat_phase` (headless).** Risiko: niedrig.
`_last_beat_mono` + `beat_phase()`/`bar_phase()` in `BPMManager`; `tempo_bus.py`; `TempoSource`-Protocol; `advance_frame` in `_render_frame`. *Tests: 120-BPM-Bus → nach 0,5 s `position≈1.0`; Tap-Parität; `default`-Bus folgt `BPMManager`; Voll-Suite grün.*

**Phase 2 — Function-Felder + Serialisierung.** Risiko: niedrig.
4 Felder + `_beat_anchor`; `from_dict`-Loader; `show['tempo_buses']`. *Tests: Round-Trip neu/alt; fehlende Keys → Defaults.*

**Phase 3 — RGB-Matrix Bus-Sync + dein Rot/Grün-↔-2×-Dimmer-Beispiel.** Risiko: mittel.
`_effective_step`; `sync_phase()` re-definiert; Params. *Tests: COLORFADE×1 + STROBE×2 → an jedem Farb-Beat ist Dimmer voll AN & Farbe rein; **Frame-Jitter-Immunität** (unregelmäßiges dt, Grenzen fallen zusammen); Free-Run bit-identisch.*

**Phase 4 — EFX + Chaser/Sequenz Bus-Sync.** Risiko: mittel.
EFX `_advance`; Chaser/Sequenz Step-Index aus Bus-Position; Downbeat-Reset. *Tests: 2 EFX phasengleich über Restart; Chaser ×2/÷2; Free-Run unverändert.*

**Phase 5 — VC-Widgets.** Risiko: niedrig-mittel.
`TAP_BUS`/`SYNC_BUS`/`TEMPO_BUS`/`VCBusSelector`; Editor-Controls. *Tests: Tap/Sync/Tempo auf benannten Bus; MIDI-Teach auf APC; VC-Layout + Speed-Dial-Back-Compat grün.*

**Phase 6 — Externe/Live-Analyzer-Quellen.** Risiko: mittel.
`BeatDetectorTempoSource` + `OS2LTempoSource`; pro-Bus-Quellen-Selector; `TempoSource` als dokumentierter Integrationsvertrag für deinen Analyzer. *Tests: Mock-Quelle treibt Bus; Handoff ohne Phasensprung; OS2L-`pos` → Takt-Phase.*

---

## 9. Rückwärtskompatibilität (per Konstruktion regressionsfrei)

- `default`-Bus = Proxy über bestehenden `BPMManager` → Carousel / `audio_triggered` Chaser / `beat_sync` CueStack unverändert, keine Migration.
- `tempo_bus_id=""` standard → der synchronisierte Pfad wird für Alt-Shows **nie** betreten; `_step += rate*dt` / `_phase += delta` laufen **byte-genau**.
- Serialisierung spiegelt den bewährten `priority`/`env_*`/`folder`-Retrofit; alte `.lshow` laden unverändert (fehlende Keys → Defaults); `tempo_buses` mit Default `[]`.
- **Per-Frame-Clear / Write-Log (EE-02/WP-6) unangetastet:** `advance_frame` mutiert nur Bus-State, schreibt **keine** Universes, läuft **vor** `tick`. F-17-Priority-Sort ist von Timing unabhängig — ein Bus ändert **wo im Zyklus** ein Effekt ist, nie die LTP-Schreibreihenfolge.
- `f.write`-4-Argument-Vertrag exakt erhalten → alle Subtyp-Overrides + Tests unverändert.

---

## 10. Offene Entscheidungen (vor Phase 1 klären)

1. **Bus-Identität/UX:** feste kleine Menge (A/B/C/D als farbige Chips) **oder** frei anlegbar/umbenennbar?
2. **`beats_per_bar`** Default 4 ok, oder konfigurierbare Taktart (3/4, 6/8) pro Bus von Anfang an?
3. **Multiplier-Set:** UI auf harmonische Verhältnisse `{¼,½,1,2,4}` sperren (sauberster Lock) oder auch freie/ungerade (×3, ×1.5) erlauben?
4. **Farbwechsel-Look** im Beispiel: harter Schnitt am Beat **oder** Crossfade, der genau zwischen den Beats fertig wird? (bestimmt den Default)
5. **Sync-Button:** auch Bus-Downbeat zurücksetzen („jetzt ist die Eins") **oder** nur die Gruppe re-ankern, Bus läuft weiter? (beides möglich — was als Default?)
6. **Carousel** jetzt schon auf benannte Buses heben (Phase 4) oder vorerst lassen?
7. **Live-Analyzer-Handoff:** soll der Bus auch die Takt-/Downbeat-Position des Analyzers übernehmen (falls verfügbar) oder nur die Beat-Phase?
