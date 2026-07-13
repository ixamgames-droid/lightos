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

## Zugehörige Tests

- `tests/test_bpm_view.py`, `test_bpm_view_speeds.py` — View-Verhalten/Speeds.
- `tests/test_bpm_leader.py` — Leader-Quelle.
- `tests/test_bpm_meter.py`, `test_bpm_timeline.py`, `test_vc_bpm.py`.

## Quelle (file:line)

- `src/ui/views/bpm_manager_view.py:51` — Klasse `BpmManagerView`
- `src/ui/views/bpm_manager_view.py:842` — globaler Auto-Sync · `:846` — globaler Sync
- `src/ui/views/bpm_manager_view.py:1170` — BPM-Quelle umschalten
- `src/ui/views/bpm_manager_view.py:868` — Takt-Zellen (beats_per_bar)
