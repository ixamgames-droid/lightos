# output_manager — OutputManager

## Zweck

Zentraler Koordinator der gesamten DMX-Ausgabe. Der `OutputManager` hält alle
`Universe`-Puffer, betreibt EINEN Ausgabe-Thread mit fester Frame-Rate (44 Hz) und
verteilt jedes Frame an die je Universe registrierten Adapter (Enttec / Art-Net /
sACN). Zusätzlich verwaltet er die globalen Dimmer-Master (Grand Master, Blackout,
globale und zugewiesene Submaster) sowie Tick-Callbacks für die Engine.

## Konfiguration / Schalter

| Schalter | Wirkung |
|---|---|
| `TARGET_HZ = 44` | Ausgabe-Frequenz; `FRAME_INTERVAL = 1/44`. |
| `LIGHTOS_SERIAL_INPROC` (Env) | Gesetzt → direkter In-Prozess-`EnttecPro` statt prozess-isoliertem Proxy (Tests/Debug/Fallback). Siehe `_make_enttec_device`. |
| `_stop_join_s = 2.0` | Wartezeit beim `stop()` auf das saubere Thread-Ende, bevor Geräte geschlossen werden (testbar überschreibbar). |
| Grand-Master-Adressmaske | `set_gm_address_mask({universe: frozenset(addr)})` — nur Intensitäts-/Farbadressen werden vom Grand Master skaliert; Pan/Tilt/Gobo bleiben unberührt (Audit B4). Universen ohne Eintrag dimmen global. |
| Submaster | `set_submaster(slot, level, fids=None)` — `fids=None` = globaler Submaster, ein iterierbares von Fixture-fids = zugewiesener Submaster. |

Universe-Mapping: Enttec sendet roh, Art-Net erhält `univ_num - 1` (0-basiert),
sACN erhält `univ_num` (1-basiert). Siehe `_send_all`.

## Threading- / Prozessmodell

- **Ein** Daemon-Thread `DMX-Output` (`_loop`) rendert und sendet bei 44 Hz.
- `_io_lock` (`RLock`) schützt jeden Geräte-Zugriff gegen gleichzeitiges Senden
  (Output-Thread) und Verbinden/Trennen/Schließen (UI-Thread). Ohne diesen Lock
  führte `close()`/Reconnect während eines laufenden `send_dmx()` unter Windows
  (pyserial) zum Deadlock.
- Das (potenziell blockierende) Öffnen neuer Geräte passiert bewusst **außerhalb**
  des Locks (`_swap_device`).
- **STAB-04:** Überlebt ein früherer Output-Thread den `stop()`-Join-Timeout, wird
  bei `start()` KEIN zweiter Thread gestartet — stattdessen wird `_running`
  reaktiviert (Selbstheilung statt konkurrierender serieller Writes).

## Fehler- / Watchdog-Verhalten

- Eine Exception in `_send_all` beendet den Output-Thread NIE (`_loop` fängt sie).
- `stop()` joint mit `_stop_join_s`. Hängt der Thread danach weiter (blockierender
  Treiber / totes Gerät), bleiben die Geräte BEWUSST offen — ein `CloseHandle()`
  neben einem laufenden `WriteFile` löst unter Windows eine native Access Violation
  aus. Der Zombie-Thread wird referenziert behalten (STAB-04).
- **OUT-05:** `remove_output(universe)` entfernt ALLE Adapter eines Universe (nötig
  für Output-Typ-Wechsel / „Disabled"), sonst Doppel-Output oder Handle-Leak.

## Gekoppelte Module

- [`universe`](universe.md) — die verwalteten Kanal-Puffer.
- [`enttec_pro`](enttec_pro.md) / [`serial_process`](serial_process.md) — serielle
  Ausgabe (In-Prozess bzw. prozess-isoliert, via `_make_enttec_device`).
- [`artnet`](artnet.md) / [`sacn`](sacn.md) — Netzwerk-Ausgabe.
- `src/core/engine/channel_modifier.py` — `apply_to_universe` läuft vor Grand-Master/
  Blackout.
- `src/core/app_state.py` — setzt die Grand-Master-Adressmaske (`_rebuild_render_plan`)
  und treibt Tick-Callbacks.

## Tests

- `tests/test_output_manager.py`
- `tests/test_output_config.py`
- `tests/test_grandmaster_mask_universe.py`
- `tests/test_submaster_assignable.py`
- `tests/test_dimmer_master.py`

## Quelle

`src/core/dmx/output_manager.py:36` (Klasse), `:211` `start`, `:237` `stop`,
`:273` `_loop`, `:286` `_send_all`.
