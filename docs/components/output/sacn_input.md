# sacn_input — SACNReceiver

## Zweck

sACN-/E1.31-**Empfänger** (Input) via Multicast oder Unicast. Hört auf UDP 5568, joint
die Multicast-Gruppen der gewünschten Universen, parst E1.31-Datenpakete und ruft
Callbacks `cb(universe, dmx)`. Optional Merge über die AppState-Eingangsschicht.
Singleton über `get_sacn_receiver()`.

## Konfiguration / Schalter

| Schalter | Wirkung |
|---|---|
| `SACN_PORT = 5568` | Bind auf `0.0.0.0:5568` (`SO_REUSEADDR`, best-effort `SO_REUSEPORT`). |
| `start(universes=[...])` | Zu joinende Universen; `None` → `[1]`. `join_universe(u)` joint später weitere. |
| Multicast-Adresse | `239.255.<hi>.<lo>` aus der Universe-Nummer (`_multicast_addr`). |
| Merge | `set_merge(in_universe, out_universe, mode)` — `mode` ∈ `HTP` / `LTP` / `REPLACE`. `remove_merge` / `clear_merges`. |
| Socket-Timeout | `0.5 s`. |

## Threading- / Prozessmodell

- Ein Daemon-Thread `sACN-In` (`_loop`) mit blockierendem `recvfrom` (0.5-s-Timeout).
- `start()` bindet, joint die Multicast-Gruppen, startet den Thread und installiert den
  Merge-Callback. `stop()` verlässt die Gruppen (best-effort `IP_DROP_MEMBERSHIP`),
  schließt den Socket und joint den Thread (1 s).
- Callback-Liste ohne Lock, über Kopie iteriert.

## Fehler- / Watchdog-Verhalten

- **NET-06:** wie beim Art-Net-Input — `OSError`/Exception im Loop setzt
  `_running = False` und bricht ab; `is_running()` prüft `thread.is_alive()` für den
  UI-Auto-Restart-Guard.
- `_parse` validiert das E1.31-Paket (Länge ≥ 126, ACN-ID, Framing-Vector, Startcode 0)
  und klemmt die Slot-Zahl (`prop_count`) gegen die real vorhandenen Bytes UND 512 —
  kein überlanger Slice durch manipulierte Pakete. Ungültige Pakete → `None` (verworfen).
- Callback- und Join-Fehler werden je Aufruf abgefangen.

## Gekoppelte Module

- `src/core/app_state.py` — `apply_input_merge` (F-20: Merge in die Eingangsschicht).
- [`artnet_input`](artnet_input.md) — baugleiches Empfangs-Geschwister.
- [`sacn`](sacn.md) — Sende-Gegenstück (gleiches Paketlayout).
- Merge-Vertrag: [`docs/OUTPUT_MERGE_CONTRACT.md`](../../OUTPUT_MERGE_CONTRACT.md).

## Tests

- `tests/test_sacn_loopback.py`
- `tests/test_dmx_input_rx_lifecycle.py`

## Quelle

`src/core/dmx/sacn_input.py:26` (Klasse), `:39` `start`, `:94` `is_running`,
`:100` `_join_universe`, `:159` `_loop`, `:183` `_parse`, `:220` `get_sacn_receiver`.
