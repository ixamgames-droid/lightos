# bpm_manager_view (BpmManagerView)

> Sub-Tab „Erkennung" der Sektion BPM: die Live-Erkennung auf einen Blick —
> sechs Bedienelemente, der Rest hinter „Erweitert". (Bis 2026-09-14 hieß der
> Sub-Tab „Manager" und trug 29 Bedienelemente; Klassenname unverändert.)

## Zweck

Sub-Tab „Erkennung" (Erkennung | Tempo-Buses | Generator). Wählt die BPM-Quelle
(PC-Audio / Eingang je Gerät / OS2L / Lied-Analyse / Aus), zeigt die große
BPM-Zahl, Beat-Punkt + Taktzellen, Zustandswort und Konfidenz, und bietet TAP,
Auto | Manuell, ×½/×2. **Tempo-Buses, Grand-Master, Auto-Sync und „Effekte je
Bus" liegen seit BPM-08 im eigenen Sub-Tab [`tempo_bus_view`](tempo_bus_view.md).**

## Bedienung / Optionen

| Bedienung | Wirkung |
|---|---|
| **Quelle** (`_cmb_source`, Daten `loopback` / `loopback:<sink_id>` / `input:<Gerät>` / `os2l` / `song` / `off`) | `bpm_source_controller.SourceController.apply(kind, device)` — EINE Stelle schaltet Capture (`set_source_mode` + start/stop), OS2L (start/stop) und Manager (`use_audio_source`); `det.set_tempo_hint(None)` + `det.reset()` beim Wechsel; idempotent. `activated` ist zusätzlich angebunden (derselbe Eintrag schaltet wegen der Idempotenz nichts erneut; „erneut verbinden" ist der Statuszeilen-Link mit `force=True`). Die Liste wird bei `showPopup` neu gelesen; der generische Eintrag heißt „PC-Audio (Systemstandard)" (S6, Daten weiter `loopback`); ein gespeichertes, fehlendes Gerät steht als „(nicht gefunden)" und setzt `SourceController.missing_sink`. |
| **TAP** (`_btn_tap`) | `bpm_tap_helper.TapHelper.tap()` — 1. Tipp `det.resync_phase()`, 2. Tipp nichts, ab dem 3. Tipp `mgr.tap()` + `det.set_tempo_hint(<gemessen>)` (Manager-Tempo ab dem 4.); derselbe Helfer wie der Topbar-TAP. |
| **Auto \| Manuell** (`_btn_auto`/`_btn_manual`, exklusive `QButtonGroup`) | `SourceController.set_auto(bool)` → `mgr.set_mode`; Auto holt bei Audio-Quelle `use_audio_source(True)` nach, bei `song` den Player-Track. Die Quelle bleibt. |
| **×½ / ×2** (`_btn_half`/`_btn_double`) | `SourceController.octave(±1) -> (ok, grund)`: in AUTO erst Tempo-Bereich prüfen (`octave_target` gegen `mgr.min_bpm/max_bpm`; außerhalb kein Aufruf, `(False, grund)` → Statuszeilen-Ereignis `ereignis_oktave`, 3 s, Link `range`), sonst `det.set_octave_preference`; in MANUAL `mgr.set_manual_bpm(bpm/2 bzw. ×2)`. |
| **▸ Erweitert** (`_advanced`, `CollapsibleSection` ohne `prefs_key`) | Zustand nur je Sitzung. |
| Erweitert: Tempo-Bereich (`_sp_min`/`_sp_max`) | `mgr.set_bounds` (spiegelt in den Detektor). |
| Erweitert: „Vorlage ▾" (`_btn_preset`, `QMenu` aus `genre_presets.ORDER`) | `genre_presets.apply_to_live(key)` — setzt NUR Bereich + Beats/Takt; die Spins ziehen nach. |
| Erweitert: Beats/Takt (`_sp_bpb`) | `mgr.set_beats_per_bar` + Taktzellen neu. |
| Erweitert: Beat-Latenz (`_sp_latency`, −300..300 ms) | `det.set_beat_latency_ms`. |
| Erweitert: „🔒 Tempo einfrieren" (`_btn_lock`) | `mgr.set_locked`. |
| Erweitert: Nudge −5/−1/+1/+5 (`_btn_nudge`) | `mgr.nudge(delta)`. |
| Erweitert: „Taktgenau" (`_chk_phase`) | `get_music_director().set_phase_accurate`. |
| Erweitert: „Eingang 30 s aufnehmen" (`_btn_record`, S6) | `AudioRecorder.start(30)` bzw. `cancel()` bei laufender Aufnahme; Text „Aufnahme … N s"; deaktiviert ohne laufende Audio-Quelle. Abschluss `on_finished` (Worker-Thread) → `_rec_done_sig` → Ereignis „Aufnahme gespeichert — audio_diag/<datei>.wav — Datei an Robin/Support schicken". |
| Statuszeilen-Link (`_lbl_abhilfe.linkActivated`, S6; QLabel, kein Bedienelement) | `reconnect` → `apply(aktuelle Quelle, force=True)` · `record` → Aufnahme · `range` → Erweitert aufklappen · `source` → `_cmb_source.showPopup()`. |

Anzeigen: `_lbl_bpm` (aus `mgr.bpm` per `subscribe_bpm_change` → Qt-Signal; gelb Auto,
grün Manuell, grau kein Tempo), `_dot` + `_phase_lbls` (Beat-Signal), `_lbl_state`
(Zustandswort, `state_word()` — reine Funktion), `_lbl_source` (`source_suffix()`: „· Tap“, „· 🔒“ … — leer statt „· —“, wenn die Manager-Quelle der Auswahl folgt; auch im Poll aktualisiert, BPM-13), `_conf` (seit BPM-13
kompakter 150-px-Balken „Konfidenz N %" neben dem Zustandswort), die **Zeile „Pegel"**
(BPM-13) direkt unter der Beat-/Zustandszeile: `_level` (`LevelMeterWidget`, volle
Breite, 18 px hoch, grüne Zielzone −30…−6 dBFS auch bei Stille sichtbar, Peak-Hold),
`_lbl_level` (`pegel_text(cap_snap)`: „−17 dBFS" / „Stille" / „— dBFS") und die Chips; in Erweitert
`_lbl_diag` (`diag_line(det_snap, cap_snap)` inkl. DC-Offset und Chunk-Abstand p95 des
Eingangs) und `SpectrumBars`. **Statuszeile** (S6): `_lbl_problem` — `_lbl_ursache` —
`_lbl_abhilfe` aus `bpm_status_rules.status_line()` über `StatusHysterese`, Farbe nach
Schwere; **Chips** `_chips` (CLIP/BRUMM/LEISE/AUSSETZER/DC) rechts in der Pegel-Zeile aus
`chips()` + `ChipHysterese`. **Kein `get_bpm(`-Aufruf** in
`src/ui/views/bpm_manager_view.py` und `src/ui/bpm_*.py` (Grep-Test).

## Datenfluss

- **Ereignisse** (BPM/Beat/Zustand) kommen aus Audio-/Timer-Threads → `_bpm_sig`/
  `_beat_sig`/`_state_sig` (Queued) → UI-Thread.
- **Kontinuierliche Werte** (Zustandswort, Konfidenz, Diagnose, Capture-Fehler) liest
  `_refresh_monitor` alle **50 ms** (`POLL_MS`) aus dem unveränderlichen
  `det.snapshot()` — der Timer läuft **nur bei Sichtbarkeit** (`showEvent`/`hideEvent`).
- **Statuszeile/Chips** (S6): im selben Poll `MgrState` (Quelle, Gerät, Modus, BPM,
  Lock, Bereich, `last_error`, `missing_sink`, Ereignis, Aufnahme-Fortschritt) +
  `Os2lState` → `status_line()` (erster Treffer gewinnt; alle Schwellen im Konstantenblock
  von `src/ui/bpm_status_rules.py`) → `StatusHysterese` (Störung 2 s an / 3 s aus,
  Zustandszeilen/Ereignisse sofort; BPM-13: `update(line, now, cap_snap)` — widerlegt der
  Pegel eine Abwesenheits-Störung klar (Kein Signal/Pegel niedrig: RMS 300 ms > Schwelle
  + 6 dB) oder eine Überschuss-Störung (Übersteuert: RMS 300 ms < −60 dBFS), entfällt die
  Aus-Hysterese, `bpm_status_rules.aufgeloest()`; gilt auch für `ChipHysterese`). Uhr injizierbar (`clock=`).
- **Aufnahme** (`src/core/audio/audio_recorder.py`): Capture-Callback nur `Queue.put`,
  Worker-Thread schreibt WAV PCM16 mono + Sidecar-JSON nach `app_data_dir()/audio_diag/`.
- Zustandswort (ui_diagnose 3.1): MANUELL · KEIN SIGNAL · SUCHT · EINGERASTET ·
  PAUSE · hält N (`hold_stage` 1/2) · OS2L (· wartet auf DJ-Software) · LIED-ANALYSE · AUS.

## Verknüpfungen

- **BpmManager:** Modus, Quelle, Tap, Lock laufen über `bpm_manager` (nur aufgerufen).
- **SourceController / TapHelper:** `src/ui/bpm_source_controller.py`,
  `src/ui/bpm_tap_helper.py` (Topbar-TAP in `main_window.py` nutzt denselben Helfer).
- **Tempo-Buses:** [`tempo_bus_view`](tempo_bus_view.md).
- **Audio:** analysierte Songs (`bpm_timeline`) kommen aus dem
  [`bpm_generator_view`](bpm_generator_view.md); die Quelle „Lied-Analyse" nimmt
  `get_media_player().current_track`.
- **VC:** dieselben Aktionen wie `vc_button` (`TAP`, `FREEZE`, `AUTO_SYNC`, …) und
  `vc_bpm_display`.

## Persistenz (BPM-09, v3)

Die Einstellungen liegen in `ui_prefs.json`, Sektion `bpm_settings`, Version 3
(`src/core/audio/bpm_settings.py`, Migrationstabelle in `bpm_arbeit/plan.md` 3.):

- **Eine Default-Quelle:** `bpm_settings.DEFAULTS`. Beim App-Start wendet
  `bpm_settings.boot()` die Datei an; die View liest danach in `_load_into_controls`
  den **Backend-Zustand** (Grenzen, Takt, Beat-Latenz, Taktgenau) — nur Quelle und
  Gerät kommen aus den Prefs.
- **Keys v3:** `source`, `device` (nur bei `input`), `mode`, `min_bpm`, `max_bpm`,
  `beats_per_bar`, `phase_accurate_beats`, `beat_latency_ms` (−300..300). Die v2-Keys
  `sensitivity`/`smoothing`/`subdivision` fallen bei der Migration mit Log
  „v2->v3: verworfen …" (entfernt 2026-09-14); `apply_to_backend` ruft
  `mgr.set_subdivision(1)` und `det.set_beat_latency_ms`.
- **Entprellung:** `_save()` startet einen 400-ms-Single-Shot neu; `flush_pending_save()`
  schreibt sofort (`hideEvent`/`closeEvent`/Tests). **Atomar** wie in v2.
- **Nicht persistiert:** Tempo einfrieren, Oktav-Vorzug, Tempo-Hinweis, Erweitert-Zustand.

## Zugehörige Tests

- `tests/test_bpm_view_layout.py` — 6 Bedienelemente (roh 7: Auto | Manuell = eine
  exklusive Gruppe; Statuszeilen-Link und Chips zählen nicht), Erweitert 6 + 12, Timer nur
  bei Sichtbarkeit, Tooltips, kein `get_bpm(`.
- `tests/test_bpm_view_status.py` — Statuszeile/Chips erscheinen nach 2 s, verschwinden nach
  3 s (Uhr gestellt); Links reconnect/record/range/source; Aufnahme-Knopf; ×2 außerhalb des
  Bereichs; fehlender Sink; Diagnosezeile; „PC-Audio (Systemstandard)".
- `tests/test_bpm_status_rules.py` — alle Situationen als Snapshot-Fixtures, nie leerer Text,
  Hysterese, gemessene Brumm-Fälle. `tests/test_audio_recorder.py` — WAV/JSON, Abbruch,
  Callback-Kosten.
- `tests/test_bpm_view_state_table.py` — Wahrheitstabelle Auto | Manuell × Quelle × Lock →
  `mgr.mode` / `current_source` / `_audio_active`; `state_word()`.
- `tests/test_bpm_view_source_combo.py` — jeder Combo-Eintrag → Fake-Capture/-OS2L/-Manager,
  doppelter Aufruf idempotent, ×½/×2 je Modus, TAP → Helfer.
- `tests/test_bpm_tap_helper.py` — 1 Tipp = `resync_phase` (kein `mgr.tap`), 2 Tipps
  aendern nichts, 4 Tipps bei 120 BPM = `mgr.tap` ×2 + `set_tempo_hint` 120 ± 1.
- `tests/test_bpm_view.py`, `tests/test_bpm_settings_v2.py` (v1→v2→v3, View-Teil),
  `tests/test_tempo_bus_view_move.py`, `tests/test_bpm_leader.py`.

## Quelle (file:line)

- `src/ui/views/bpm_manager_view.py:120` — `state_word()` · `:143` — `diag_line()`
- `src/ui/views/bpm_manager_view.py:179` — Klasse `BpmManagerView`
- `src/ui/views/bpm_manager_view.py:243` — `_build_head` (Quelle, Pegelmeter + Chips, Beat, Zustandswort, Konfidenz)
- `src/ui/views/bpm_manager_view.py:353` — `_build_buttons` (TAP, Auto | Manuell, ×½, ×2)
- `src/ui/views/bpm_manager_view.py:409` — `_build_status` (Statuszeile)
- `src/ui/views/bpm_manager_view.py:440` — `_build_advanced` (12 Bedienelemente)
- `src/ui/views/bpm_manager_view.py:636` — `_populate_sources` · `:689` — `_on_source_changed`
- `src/ui/views/bpm_manager_view.py:804` — `_refresh_monitor` (50-ms-Poll) · `:911` — `_on_status_link` · `:942` — `_start_recording` · `:1004` — `_octave`
- `src/ui/bpm_status_rules.py:157` — `status_line()` · `:463` — `StatusHysterese` · `:508` — `chips()` · `:530` — `ChipHysterese`
- `src/ui/bpm_source_controller.py:209` — `SourceController.octave` · `src/ui/bpm_tap_helper.py` — `TapHelper`
- `src/core/audio/audio_recorder.py:119` — `AudioRecorder.start` · `:156` — `_worker`
- `src/core/audio/bpm_settings.py:45` — `DEFAULTS` (v3) · `:150` — `_v2_to_v3` · `:160` — `migrate`
