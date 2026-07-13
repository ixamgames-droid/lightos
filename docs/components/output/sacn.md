# sacn — SACNSender

## Zweck

sACN-/E1.31-**Sender** (Ausgabe) über UDP. Baut spec-konforme E1.31-Datenpakete
(Root-/Framing-/DMP-Layer, 638 Byte für 512 Slots) und sendet sie per Multicast oder
Unicast. Der `OutputManager` hält je Universe einen Sender.

## Konfiguration / Schalter

| Schalter | Wirkung |
|---|---|
| `SACN_PORT = 5568` | Fester E1.31-UDP-Port. |
| `target_ip` (Konstruktor) | `None` → Multicast an `239.255.<hi>.<lo>` (aus Universe abgeleitet); IP-String → Unicast. |
| `source_name = "LightOS"` | Quellname im Framing-Layer (max. 63 Byte, null-terminiert). |
| `_E131_DEFAULT_PRIORITY = 100` | Sende-Priorität. |
| CID | Zufällige `uuid4` je Sender-Instanz. |

Universe-Mapping: `send_dmx(universe, data)` erwartet die 1-basierte Universe-Nummer
(der `OutputManager` übergibt `univ_num`). Daten werden auf exakt 512 Byte
gepolstert/getrimmt; ein Sequence-Zähler wird je Universe geführt.

## Threading- / Prozessmodell

Kein eigener Thread und keine Locks. `send_dmx` läuft im 44-Hz-Output-Thread (unter
`_io_lock` des `OutputManager`). Socket wird in `_open` erstellt (`SO_REUSEADDR`, bei
Multicast `IP_MULTICAST_TTL = 8`).

## Fehler- / Watchdog-Verhalten

- `send_dmx` verwirft `struct.error` und `OSError` still (kein Absturz, kein Blockieren).
- **OUT-06 Stream-Termination:** `close()` sendet je zuletzt bespieltem Universe 3 Pakete
  mit gesetztem `Stream_Terminated`-Options-Bit (`0x40`), damit Empfänger die Quelle
  SOFORT verwerfen, statt ~2,5 s auf den Network-Data-Loss-Timeout zu warten (hängende
  Kanäle beim Adapter-Wechsel).

## Gekoppelte Module

- [`output_manager`](output_manager.md) — `add_sacn` / `remove_output`, Aufruf im
  Output-Loop.
- [`sacn_input`](sacn_input.md) — Empfangs-Gegenstück (gleiches Paketlayout).
- Protokoll-Details: [`docs/DMX_PROTOCOL.md`](../../DMX_PROTOCOL.md).

## Tests

- `tests/test_sacn_loopback.py` (Sender↔Receiver Roundtrip).
- `tests/test_output_manager.py` (Adapter-Verdrahtung).

## Quelle

`src/core/dmx/sacn.py:87` (Klasse), `:37` `_pack_framing`, `:107` `send_dmx`,
`:134` `close`.
