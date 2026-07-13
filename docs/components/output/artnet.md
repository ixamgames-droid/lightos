# artnet — ArtNetSender

## Zweck

Art-Net-4-UDP-**Sender** (Ausgabe). Baut spec-konforme ArtDmx-Pakete und schickt sie
per UDP an ein Ziel (Broadcast oder Unicast). Ein `ArtNetSender` bedient genau ein
Netzwerkziel; der `OutputManager` hält je Universe einen Sender.

## Konfiguration / Schalter

| Schalter | Wirkung |
|---|---|
| `ARTNET_PORT = 6454` | Fester Art-Net-UDP-Port. |
| `target_ip` (Konstruktor) | Zieladresse; Default `255.255.255.255` (Broadcast). Für Unicast eine konkrete IP übergeben. Socket hat `SO_BROADCAST` gesetzt. |
| `ARTNET_VERSION = 14`, `OPCODE_DMX = 0x5000` | Protokoll-Konstanten im Header. |

Universe-Mapping: Der Wire-Wert ist 0-basiert. Der `OutputManager` übergibt
`univ_num - 1` an `send_dmx`. Ein interner Sequence-Zähler (1–255) wird pro Paket
hochgezählt.

## Threading- / Prozessmodell

Kein eigener Thread und keine Locks. `send_dmx` wird ausschließlich aus dem
44-Hz-Output-Thread des `OutputManager` aufgerufen (dort unter dessen `_io_lock`).
Der UDP-Socket wird im Konstruktor geöffnet und in `close()` geschlossen.

## Fehler- / Watchdog-Verhalten

Kein eigener Watchdog. `send_dmx`-Fehler werden vom aufrufenden `OutputManager._send_all`
in einem `try/except` verworfen (ein Frame fällt aus, der Thread läuft weiter). `close()`
schließt den Socket; unterstützt Context-Manager (`__enter__`/`__exit__`).

## Gekoppelte Module

- [`output_manager`](output_manager.md) — `add_artnet` / `remove_output`, Aufruf im
  Output-Loop.
- [`artnet_input`](artnet_input.md) — Empfangs-Gegenstück (gleiches Wire-Format).
- Protokoll-Details: [`docs/DMX_PROTOCOL.md`](../../DMX_PROTOCOL.md),
  [`docs/ARTNET.md`](../../ARTNET.md).

## Tests

- `tests/test_output_manager.py` (Adapter-Verdrahtung über den `OutputManager`).
- `tests/test_dmx_input_rx_lifecycle.py` (Wire-Format gegen den Receiver).

## Quelle

`src/core/dmx/artnet.py:24` (Klasse), `:11` `_build_artdmx`, `:31` `send_dmx`.
