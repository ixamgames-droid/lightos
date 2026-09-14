# tempo_bus_view (TempoBusView)

> Sub-Tab „Tempo-Buses" der Sektion BPM: Tempo-Speeds & Grand-Master (Bus-Tabelle,
> Master/Sub, Auto-Sync) und „Effekte je Bus — taktgleich".

## Zweck

Eigener Sub-Tab (BPM-08, seit 2026-09-14) für alles, was **Tempo-Buses** betrifft.
Die beiden Gruppen lagen vorher unten im
[`bpm_manager_view`](bpm_manager_view.md) und sind **unverändert** hierher gezogen
(reiner Move: Attribut-, Methoden- und Beschriftungsnamen gleich; einzige
Änderung: der zweite Knopf „Aktualisieren" unter der Bus-Tabelle entfällt, der
150-ms-Poll und „⟳ Aktualisieren" im Effekte-Panel decken das ab).

- **Tempo-Speeds && Grand-Master** (Phase D2): Grand-Master scharf/BPM/Tap,
  Auto-Sync + „Jetzt synchronisieren", Bus-Tabelle (Bus/Rolle/Folgt/Faktor/BPM,
  Default zuerst), Master anlegen/löschen, Editor Rolle/Folgt/Faktor.
- **Effekte je Bus — taktgleich** (Stufe 2): Baum Haupt-BPM · A–D · Frei; pro
  Effekt Bus-Dropdown, Tempo ×, Taktgleich-Haken; „Sync jetzt" je Bus.

## Bedienung / Optionen

| Bedienung | Wirkung |
|---|---|
| Grand-Master scharf / BPM / Tap | `set_grandmaster_armed` / `set_grandmaster_bpm` / `tap_grandmaster` — übertrumpft alle Master |
| Auto-Sync | `TempoBusManager.set_auto_sync` (global, alle Buses; spiegelt die VC-Aktion) |
| Jetzt synchronisieren | `bus.sync(reset_downbeat=True)` für **alle** Buses |
| Master anlegen / Löschen | `ensure_bus(name).set_role("master")` / `remove_bus` (Default und seine Aliase abgewiesen, ENG-26) |
| Rolle / Folgt / Faktor → Übernehmen | `set_role` / `set_parent` / `set_bus_multiplier` des gewählten Bus |
| Bus-Dropdown je Effekt | `assign_effects_to_bus([fid], bus)` — Baum wird verzögert neu gebaut (Combo nicht synchron zerstören) |
| Tempo × je Effekt | `tempo_multiplier` (über `set_param`, falls vorhanden) |
| Taktgleich-Haken | `align_on_start`; läuft der Effekt, sofort `sync_phase()` |
| Sync jetzt (je Bus) | `bus_for_effect(bus_id).sync(reset_downbeat=True)` |
| ⟳ Aktualisieren | Effekte-Baum neu aufbauen (zusätzlich automatisch bei `FUNCTION_CHANGED`) |

## Verknüpfungen

- **TempoBusManager** (`src/core/engine/tempo_bus.py`): alle Schreibzugriffe;
  kein eigener Zustand in der View.
- **FunctionManager:** Effekt-Zeilen über `list_effects_by_bus()`;
  Live-Refresh per `get_sync().subscribe_widget(FUNCTION_CHANGED, …)` — das
  Abo ist an die Widget-Lebenszeit gebunden (Abmeldung bei `destroyed`).
- **Poll:** `_refresh_bus_bpm_live` alle 150 ms (nur sichtbar, `showEvent`/
  `hideEvent`) zieht die BPM-Spalte nach — ein TempoBus hat keine Subscribe-API.
  Bei geänderter Bus-Anzahl einmal voller Rebuild (`_refresh_speeds`).
- **VC:** dieselben Aktionen wie `vc_button` (`AUTO_SYNC`, `SYNC_BUS`,
  `TAP_BUS`) und der Speed-Dial; Anleitung: `docs/ANLEITUNG_TEMPO_SYNC.md`,
  `docs/anleitung_speed/ANLEITUNG_SPEED.md`.
- **Hauptfenster:** `src/ui/main_window.py`, Sektion 7 BPM — Sub-Tabs
  Erkennung | Tempo-Buses | Generator (Sub-Tab „Erkennung" seit BPM-09, vorher „Manager").

## Zugehörige Tests

- `tests/test_tempo_bus_view_move.py` — BPM-08: Attribute nur noch hier,
  Zählung sichtbarer Bedienelemente (Manager 29 / Tempo-Buses 13 leer, 21 mit
  einer Matrix), genau ein `FUNCTION_CHANGED`-Abo, drei Sub-Tabs.
- `tests/test_bpm_view_speeds.py` — Grand-Master, Master anlegen/löschen,
  Editor, Live-BPM-Spalte.
- `tests/test_bpm_window_effects_panel.py` — Effekte-je-Bus-Panel.
- `tests/test_tempo_sync_button.py` — Auto-Sync-Toggle, „Jetzt synchronisieren".

## Quelle (file:line)

- `src/ui/views/tempo_bus_view.py:31` — Klasse `TempoBusView`
- `src/ui/views/tempo_bus_view.py:272` — `_build_speeds` · `:304` — Auto-Sync ·
  `:312` — „Jetzt synchronisieren" · `:323` — Bus-Tabelle
- `src/ui/views/tempo_bus_view.py:95` — `_build_effects_panel` · `:137` —
  `_refresh_effects_panel` · `:249` — `_on_bus_sync_now`
- `src/ui/views/tempo_bus_view.py:420` — `_refresh_bus_bpm_live` (150-ms-Poll)
- `src/ui/views/tempo_bus_view.py:552` — `showEvent`/`hideEvent` (Poll nur sichtbar)
