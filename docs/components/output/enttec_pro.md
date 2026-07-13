# enttec_pro — EnttecPro

## Zweck

Ausgabe an einen **Enttec DMX USB Pro** über pyserial. `EnttecPro` öffnet einen
COM-Port, verpackt 512 DMX-Bytes ins Enttec-Framing (Label 6) und schreibt sie. Enthält
den Fehler-Watchdog und die Reconnect-Logik, die einen wackligen/abgezogenen USB-Stecker
überlebt, ohne LightOS abzuschießen.

## Konfiguration / Schalter

| Schalter | Wirkung |
|---|---|
| `ENTTEC_BAUD = 57600` | Serielle Baudrate. |
| `ENTTEC_VID = 0x0403`, `ENTTEC_PID = 0x6001` | VID/PID für die Auto-Erkennung (`find_enttec_port`). |
| `FAIL_LIMIT = 20` | So viele aufeinanderfolgende Schreib-Fehler werten den Port als tot (OUT-02). |
| `RECONNECT_EVERY_S = 3.0` | Drossel für Reconnect-Versuche, solange der Port als tot gilt. |
| `write_timeout = 0.5` | KRITISCH: ohne Timeout blockiert `write()` endlos und friert die 44-Hz-Engine ein; 0.5 s sind großzügig für ein 513-Byte-Paket bei 57600 Baud (~90 ms). |

Hilfsfunktionen: `find_enttec_port()` (Auto-Erkennung per VID/PID),
`list_serial_ports()` (alle COM-Ports).

## Threading- / Prozessmodell

Kein eigener Thread. Wird entweder direkt aus dem 44-Hz-Output-Thread des
`OutputManager` (bei `LIGHTOS_SERIAL_INPROC`) ODER innerhalb des Worker-Prozesses von
[`serial_process`](serial_process.md) betrieben. Keine internen Locks — die
Serialisierung übernimmt der Aufrufer (`OutputManager._io_lock` bzw. der Single-Thread-
Worker-Loop).

## Fehler- / Watchdog-Verhalten

- **OUT-02 Fehler-Watchdog:** `send_dmx` zählt aufeinanderfolgende Schreib-Fehler
  (`_note_fail`). Ab `FAIL_LIMIT` wird der Port als tot markiert und geschlossen
  (`_disable`) — kein weiteres 44-Hz-Hämmern auf ein abgezogenes USB-Gerät (jeder
  `WriteFile` darauf riskiert eine native, nicht fangbare Access Violation).
- Ein erfolgreicher Frame setzt den Zähler zurück → nur ein ANHALTENDER Abriss löst das
  Auto-Disable aus, kein einzelner Hickup.
- `is_open`-Guard: kein Schreiben auf ein bereits geschlossenes Handle.
- `_try_reconnect` öffnet den Port gedrosselt neu; gelingt es, reaktiviert sich die
  Ausgabe von selbst (ohne App-Neustart). `is_disabled()` für UI-Status.
- `close()` bricht/leert vorher den Output-Puffer, damit `CloseHandle()` nicht mit einem
  ausstehenden `WriteFile` kollidiert. Idempotent, fehlertolerant.

## Gekoppelte Module

- [`output_manager`](output_manager.md) — `_make_enttec_device` wählt In-Prozess
  `EnttecPro` (bei `LIGHTOS_SERIAL_INPROC`) oder den Prozess-Proxy.
- [`serial_process`](serial_process.md) — der Worker-Prozess betreibt intern einen
  `EnttecPro`.

## Tests

- `tests/test_enttec_pro.py`
- `tests/test_enttec_fail_watchdog.py`

## Quelle

`src/core/dmx/enttec_pro.py:40` (Klasse), `:68` `send_dmx`, `:102` `_note_fail`,
`:108` `_disable`, `:122` `_try_reconnect`, `:150` `close`.
