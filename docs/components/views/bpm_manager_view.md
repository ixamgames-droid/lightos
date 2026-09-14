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
| **Quelle** (`_cmb_source`, Daten `loopback` / `input:<Gerät>` / `os2l` / `song` / `off`) | `bpm_source_controller.SourceController.apply(kind, device)` — EINE Stelle schaltet Capture (`set_source_mode` + start/stop), OS2L (start/stop) und Manager (`use_audio_source`); `det.set_tempo_hint(None)` + `det.reset()` beim Wechsel; idempotent. `activated` ist zusätzlich angebunden („erneut verbinden" auf denselben Eintrag). Die Liste wird bei `showPopup` neu gelesen; ein gespeichertes, fehlendes Gerät steht als „(nicht gefunden)". |
| **TAP** (`_btn_tap`) | `bpm_tap_helper.TapHelper.tap()` — 1. Tipp `det.resync_phase()`, jeder Tipp `mgr.tap()`, ab dem 3. Tipp `det.set_tempo_hint(<gemessen>)`; derselbe Helfer wie der Topbar-TAP. |
| **Auto \| Manuell** (`_btn_auto`/`_btn_manual`, exklusive `QButtonGroup`) | `SourceController.set_auto(bool)` → `mgr.set_mode`; Auto holt bei Audio-Quelle `use_audio_source(True)` nach, bei `song` den Player-Track. Die Quelle bleibt. |
| **×½ / ×2** (`_btn_half`/`_btn_double`) | `SourceController.octave(±1)`: in AUTO `det.set_octave_preference`, in MANUAL `mgr.set_manual_bpm(bpm/2 bzw. ×2)`. |
| **▸ Erweitert** (`_advanced`, `CollapsibleSection` ohne `prefs_key`) | Zustand nur je Sitzung. |
| Erweitert: Tempo-Bereich (`_sp_min`/`_sp_max`) | `mgr.set_bounds` (spiegelt in den Detektor). |
| Erweitert: „Vorlage ▾" (`_btn_preset`, `QMenu` aus `genre_presets.ORDER`) | `genre_presets.apply_to_live(key)` — setzt NUR Bereich + Beats/Takt; die Spins ziehen nach. |
| Erweitert: Beats/Takt (`_sp_bpb`) | `mgr.set_beats_per_bar` + Taktzellen neu. |
| Erweitert: Beat-Latenz (`_sp_latency`, −300..300 ms) | `det.set_beat_latency_ms`. |
| Erweitert: „🔒 Tempo einfrieren" (`_btn_lock`) | `mgr.set_locked`. |
| Erweitert: Nudge −5/−1/+1/+5 (`_btn_nudge`) | `mgr.nudge(delta)`. |
| Erweitert: „Taktgenau" (`_chk_phase`) | `get_music_director().set_phase_accurate`. |

Anzeigen: `_lbl_bpm` (aus `mgr.bpm` per `subscribe_bpm_change` → Qt-Signal; gelb Auto,
grün Manuell, grau kein Tempo), `_dot` + `_phase_lbls` (Beat-Signal), `_lbl_state`
(Zustandswort, `state_word()` — reine Funktion), `_lbl_source`, `_conf`, in Erweitert
`_lbl_diag` (`diag_line()`) und `SpectrumBars`. **Kein `get_bpm(`-Aufruf** in
`src/ui/views/bpm_manager_view.py` und `src/ui/bpm_*.py` (Grep-Test).

## Datenfluss

- **Ereignisse** (BPM/Beat/Zustand) kommen aus Audio-/Timer-Threads → `_bpm_sig`/
  `_beat_sig`/`_state_sig` (Queued) → UI-Thread.
- **Kontinuierliche Werte** (Zustandswort, Konfidenz, Diagnose, Capture-Fehler) liest
  `_refresh_monitor` alle **50 ms** (`POLL_MS`) aus dem unveränderlichen
  `det.snapshot()` — der Timer läuft **nur bei Sichtbarkeit** (`showEvent`/`hideEvent`).
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
  exklusive Gruppe), Erweitert 6 + 11, Timer nur bei Sichtbarkeit, Tooltips, kein `get_bpm(`.
- `tests/test_bpm_view_state_table.py` — Wahrheitstabelle Auto | Manuell × Quelle × Lock →
  `mgr.mode` / `current_source` / `_audio_active`; `state_word()`.
- `tests/test_bpm_view_source_combo.py` — jeder Combo-Eintrag → Fake-Capture/-OS2L/-Manager,
  doppelter Aufruf idempotent, ×½/×2 je Modus, TAP → Helfer.
- `tests/test_bpm_tap_helper.py` — 1 Tipp = `resync_phase`, 4 Tipps bei 120 BPM =
  `mgr.tap` ×4 + `set_tempo_hint` 120 ± 1.
- `tests/test_bpm_view.py`, `tests/test_bpm_settings_v2.py` (v1→v2→v3, View-Teil),
  `tests/test_tempo_bus_view_move.py`, `tests/test_bpm_leader.py`.

## Quelle (file:line)

- `src/ui/views/bpm_manager_view.py:88` — `state_word()` · `:111` — `diag_line()`
- `src/ui/views/bpm_manager_view.py:143` — Klasse `BpmManagerView`
- `src/ui/views/bpm_manager_view.py:201` — `_build_head` (Quelle, Beat, Zustandswort, Konfidenz)
- `src/ui/views/bpm_manager_view.py:290` — `_build_buttons` (TAP, Auto | Manuell, ×½, ×2)
- `src/ui/views/bpm_manager_view.py:346` — `_build_advanced` (11 Bedienelemente)
- `src/ui/views/bpm_manager_view.py:519` — `_populate_sources` · `:551` — `_on_source_changed`
- `src/ui/views/bpm_manager_view.py:663` — `_refresh_monitor` (50-ms-Poll)
- `src/ui/bpm_source_controller.py` — `SourceController` · `src/ui/bpm_tap_helper.py` — `TapHelper`
- `src/core/audio/bpm_settings.py:45` — `DEFAULTS` (v3) · `:150` — `_v2_to_v3` · `:160` — `migrate`
