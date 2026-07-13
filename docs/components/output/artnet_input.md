# artnet_input — ArtNetReceiver

## Zweck

Art-Net-**Empfänger** (Input). Hört auf UDP 6454, parst ArtDmx-Pakete und ruft
registrierte Callbacks `cb(universe, dmx)`. Optional merged er eingehende Universen
über die AppState-Eingangsschicht in lokale (gepatchte) Universen. Singleton über
`get_artnet_receiver()`.

## Konfiguration / Schalter

| Schalter | Wirkung |
|---|---|
| `ARTNET_PORT = 6454` | Bind auf `0.0.0.0:6454` (`SO_REUSEADDR`). |
| Merge | `set_merge(in_universe, out_universe, mode)` — `mode` ∈ `HTP` / `LTP` / `REPLACE` (unbekannt → `HTP`). `remove_merge` / `clear_merges`. |
| Socket-Timeout | `0.5 s` (`settimeout`), damit `stop()` den Loop zeitnah beendet. |

Universe-Mapping: Art-Net-Wire ist 0-basiert; der Receiver liefert Callbacks
1-basiert (`+1`).

## Threading- / Prozessmodell

- Ein Daemon-Thread `ArtNet-In` (`_loop`) mit blockierendem `recvfrom` (0.5-s-Timeout).
- `start()` bindet den Socket, startet den Thread und installiert den Merge-Callback.
  `stop()` schließt den Socket und joint den Thread (1 s).
- Kein Lock auf der Callback-Liste — über eine Kopie (`list(self._callbacks)`) iteriert.

## Fehler- / Watchdog-Verhalten

- **NET-06:** Bei `OSError` oder anderer Exception im Loop wird `_running = False`
  gesetzt und `break` — ein so gestorbener Thread gilt in `is_running()` (prüft
  `thread.is_alive()`) als NICHT laufend, damit der UI-Auto-Restart-Guard greift.
- Das Längenfeld stammt ungeprüft aus dem Paket und wird gegen die real vorhandenen
  Bytes UND das DMX-Maximum (512) geklemmt — kein überlanger Slice durch manipulierte
  Pakete.
- Callback-Fehler werden je Callback abgefangen (ein defekter Subscriber blockiert die
  anderen nicht).

## Gekoppelte Module

- `src/core/app_state.py` — `apply_input_merge` (F-20: Merge in die Eingangsschicht statt
  direkt ins Live-Universe, sonst überschreibt der Per-Frame-Renderer gepatchte Kanäle).
- [`sacn_input`](sacn_input.md) — baugleiches Empfangs-Geschwister.
- [`artnet`](artnet.md) — Sende-Gegenstück (gleiches Wire-Format).
- Merge-Vertrag: [`docs/OUTPUT_MERGE_CONTRACT.md`](../../OUTPUT_MERGE_CONTRACT.md).

## Tests

- `tests/test_dmx_input_rx_lifecycle.py`

## Quelle

`src/core/dmx/artnet_input.py:22` (Klasse), `:38` `start`, `:73` `is_running`,
`:91` `set_merge`, `:130` `_loop`, `:170` `get_artnet_receiver`.
