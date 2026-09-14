# bpm_manager_view (BpmManagerView)

> Der „Leader"-zentrierte BPM-Tab: Monitor, globale Tempo-Quelle, Tap/Lock,
> Genre-Presets und Takt-Anzeige.

## Zweck

Sub-Tab „Manager" der Sektion BPM (Manager | Tempo-Buses | Generator). Wählt die
BPM-Quelle (Manual/Tap/Audio/analysierter Song), zeigt Monitor und Takt-Zellen
zum aktuellen Beat und spiegelt Lock/Freeze wie die VC-Aktionen. Genre-Presets
stellen die Beat-Erkennung passend ein. **Tempo-Buses, Grand-Master, Auto-Sync
und „Effekte je Bus" liegen seit BPM-08 im eigenen Sub-Tab
[`tempo_bus_view`](tempo_bus_view.md).**

## Bedienung / Optionen

| Bedienung | Wirkung |
|---|---|
| Quelle umschalten | Primär-Steuerung der globalen BPM-Quelle (`_SRC_LABELS`) |
| Modus/Lock | AUTO/MANUAL + Lock-Zustand |
| Genre-Preset | Erkennungs-Parameter je Genre setzen + UI nachziehen |
| Analysierter Song | Track mit `bpm_timeline` als aktive Quelle wählen |
| Takt-Zellen | An `beats_per_bar` angepasst (max. 16 sichtbar) |

## Verknüpfungen

- **BpmManager:** Kern-Kopplung — Modus, Quelle, Tap, Freeze laufen über
  `bpm_manager`; der Default-Bus folgt der hier gesetzten globalen BPM.
- **Tempo-Buses:** [`tempo_bus_view`](tempo_bus_view.md) (Bus-Tabelle,
  Grand-Master, Auto-Sync, Effekte je Bus).
- **Audio:** analysierte Songs (`bpm_timeline`) kommen aus dem
  [`bpm_generator_view`](bpm_generator_view.md)/Audio-Analyse.
- **VC:** dieselben Aktionen wie `vc_button` (`TAP`, `FREEZE`, `AUTO_SYNC`,
  `TAP_BUS`…) und `vc_bpm_display`.

## Persistenz (BPM-07, v2)

Die Einstellungen liegen in `ui_prefs.json`, Sektion `bpm_settings`, Version 2
(`src/core/audio/bpm_settings.py`, Migrationstabelle in `bpm_arbeit/plan.md` 3.):

- **Eine Default-Quelle:** `bpm_settings.DEFAULTS`. Beim App-Start wendet
  `bpm_settings.boot()` die Datei auf Manager/Detektor/Director an; die View
  liest danach in `_load_into_controls` den **Backend-Zustand** (Grenzen, Takt,
  Unterteilung, Taktgenau) — nur Audio-Quelle und Gerät kommen aus den Prefs,
  weil der Capture gestoppt oder die Quelle `off` sein kann.
- **Keys v2:** `source` (`loopback`/`input`/`os2l`/`song`/`off`), `device`
  (Eingangsgerät — nur bei `input`, sonst `null`; ein Mikrofonname unter
  `loopback` würde PC-Audio nach dem Neustart auf das Mikrofon lenken, ein
  Sink-Name für PC-Audio kommt mit S5), `mode`, `min_bpm`, `max_bpm`, `beats_per_bar`,
  `phase_accurate_beats`; geduldet bis S4: `sensitivity`, `smoothing`,
  `subdivision`. Alte v1-Dateien (`auto_default`/`mode_default`/`source_mode`/
  `input_device`) werden beim Laden migriert; das erste Schreiben sichert die
  Datei einmalig als `ui_prefs.json.v1.bak`. Ungültige Werte fallen auf den
  Default, unbekannte Keys werden mit Log verworfen; eine Datei einer
  **neueren** Version bleibt unangetastet (Defaults, kein Schreiben).
- **Entprellung:** `_save()` startet einen 400-ms-Single-Shot neu; aus einem
  Sliderzug mit hunderten `valueChanged` wird **ein** Schreibvorgang
  (`_write_settings`). `flush_pending_save()` schreibt Ausstehendes sofort und
  läuft in `hideEvent`/`closeEvent` (und in Tests vor dem Lese-Assert).
- **Atomar:** tmp-Datei im selben Ordner + `flush` + `fsync` + `os.replace`;
  Fremd-Sektionen (`live_view` u. a.) bleiben erhalten. Bricht das Schreiben ab,
  bleibt die alte Datei vollständig, die tmp wird entfernt. Ist die Datei beim
  Speichern vorhanden, aber unlesbar (halbe Datei eines nicht atomaren
  Schreibers), wird sie vor dem Überschreiben einmalig als
  `ui_prefs.json.corrupt.bak` gesichert.

## Zugehörige Tests

- `tests/test_bpm_view.py` — View-Verhalten (Speeds: siehe `tempo_bus_view`).
- `tests/test_tempo_bus_view_move.py` — BPM-08: keine Tempo-Bus-Attribute mehr
  hier, 29 sichtbare Bedienelemente, kein `FUNCTION_CHANGED`-Abo.
- `tests/test_bpm_settings_v2.py` — Persistenz v2: Migration (Beispiel aus
  `plan.md` 3. byte-genau), Typprüfung, atomares Schreiben, v1-/corrupt-Sicherung,
  Entprellung (250 Ticks → 1 Schreibvorgang), `flush_pending_save()`, `device`
  nur für `input` (View und Auto-Start); `AudioCapture.start` ist dort gestubbt.
- `tests/test_bpm_leader.py` — Leader-Quelle, Roundtrip/`apply_to_backend`.
- `tests/test_bpm_meter.py`, `test_bpm_timeline.py`, `test_vc_bpm.py`.

## Quelle (file:line)

- `src/ui/views/bpm_manager_view.py:51` — Klasse `BpmManagerView`
- `src/ui/views/bpm_manager_view.py:704` — BPM-Quelle umschalten (`_apply_source_kind`)
- `src/ui/views/bpm_manager_view.py:396` — Takt-Zellen (beats_per_bar)
- `src/ui/views/bpm_manager_view.py:415` — `_load_into_controls` (Backend-Zustand)
- `src/ui/views/bpm_manager_view.py:553` — `_refresh_monitor` (150-ms-Poll)
- `src/ui/views/bpm_manager_view.py:788` — `_save` (Entprellung) · `:795` —
  `flush_pending_save` · `:804` — `_write_settings`
- `src/core/audio/bpm_settings.py:38` — `DEFAULTS` (v2) · `:146` — `migrate` ·
  `:238` — `save_settings` (atomar) · `:274` — `apply_to_backend`
