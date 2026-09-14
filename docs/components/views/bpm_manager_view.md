# bpm_manager_view (BpmManagerView)

> Der „Leader"-zentrierte BPM-Tab: globale Tempo-Quelle, Tempo-Buses, Tap/Sync,
> Genre-Presets und Takt-Anzeige.

## Zweck

Eigenständiger Tab zur globalen Tempo-Steuerung. Wählt die BPM-Quelle
(Manual/Tap/Audio/analysierter Song), zeigt die Takt-Zellen zum aktuellen Beat,
verwaltet Tempo-Buses (Tap/Sync/Arm je Bus) und spiegelt Auto-Sync/Freeze wie die
VC-Aktionen — nur global über alle Buses. Genre-Presets stellen die
Beat-Erkennung passend ein.

## Bedienung / Optionen

| Bedienung | Wirkung |
|---|---|
| Quelle umschalten | Primär-Steuerung der globalen BPM-Quelle (`_SRC_LABELS`) |
| Modus/Lock | AUTO/MANUAL + Lock-Zustand |
| Auto-Sync (global) | Auto-Sync für ALLE Tempo-Buses (spiegelt VC) |
| Sync (global) | Einmal-Sync für alle Buses gleichzeitig |
| Genre-Preset | Erkennungs-Parameter je Genre setzen + UI nachziehen |
| Analysierter Song | Track mit `bpm_timeline` als aktive Quelle wählen |
| Takt-Zellen | An `beats_per_bar` angepasst (max. 16 sichtbar) |

## Verknüpfungen

- **BpmManager / TempoBus:** Kern-Kopplung — Modus, Quelle, Tap, Auto-Sync,
  Freeze laufen über `bpm_manager` und die Tempo-Buses.
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
- **Keys v2:** `source` (`loopback`/`input`/`os2l`/`song`/`off`), `device` (wird
  auch für PC-Audio gemerkt), `mode`, `min_bpm`, `max_bpm`, `beats_per_bar`,
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
  bleibt die alte Datei vollständig, die tmp wird entfernt.

## Zugehörige Tests

- `tests/test_bpm_view.py`, `test_bpm_view_speeds.py` — View-Verhalten/Speeds.
- `tests/test_bpm_settings_v2.py` — Persistenz v2: Migration (Beispiel aus
  `plan.md` 3. byte-genau), Typprüfung, atomares Schreiben, v1-Sicherung,
  Entprellung (250 Ticks → 1 Schreibvorgang), `flush_pending_save()`.
- `tests/test_bpm_leader.py` — Leader-Quelle, Roundtrip/`apply_to_backend`.
- `tests/test_bpm_meter.py`, `test_bpm_timeline.py`, `test_vc_bpm.py`.

## Quelle (file:line)

- `src/ui/views/bpm_manager_view.py:51` — Klasse `BpmManagerView`
- `src/ui/views/bpm_manager_view.py:861` — globaler Auto-Sync · `:865` — globaler Sync
- `src/ui/views/bpm_manager_view.py:1195` — BPM-Quelle umschalten
- `src/ui/views/bpm_manager_view.py:887` — Takt-Zellen (beats_per_bar)
- `src/ui/views/bpm_manager_view.py:906` — `_load_into_controls` (Backend-Zustand)
- `src/ui/views/bpm_manager_view.py:1279` — `_save` (Entprellung) · `:1286` —
  `flush_pending_save` · `:1295` — `_write_settings`
- `src/core/audio/bpm_settings.py:31` — `DEFAULTS` (v2) · `:139` — `migrate` ·
  `:213` — `save_settings` (atomar) · `:242` — `apply_to_backend`
