# universe — Universe

## Zweck

Thread-sicherer 512-Kanal-DMX-Puffer. Jedes DMX-Universum ist eine `Universe`-Instanz
mit einem `bytearray(512)`. Bietet Einzel- und Bereichs-Schreibzugriff, einen Snapshot
(`get_all`) für den Output-Thread und ein optionales Schreib-Protokoll für den Renderer.

## Konfiguration / Schalter

| Schalter | Wirkung |
|---|---|
| `SIZE = 512` | Feste Universumsgröße (Kanäle 1–512, 1-basiert). |
| Schreib-Protokoll | `begin_write_log()` / `end_write_log()` — zeichnet WERT-unabhängig alle geschriebenen Kanäle auf, damit der Renderer erkennt, ob der Funktions-Layer einen Kanal „besitzt" (auch beim Schreiben des Default-Werts, z. B. Dimmer 0 im Strobe-Nulldurchgang). |

## Threading- / Prozessmodell

- Kein eigener Thread. Jede Instanz kapselt ein `threading.Lock`, das jeden Zugriff
  auf `_data` und `_write_log` serialisiert.
- Wird vom Output-Thread (`get_all`), vom Renderer (Schreiben) und von Input-Merges
  gleichzeitig benutzt — daher durchgängig unter Lock.

## Fehler- / Watchdog-Verhalten

- `set_channel` validiert robust OHNE `assert`: Eingaben kommen ungeprüft aus
  Netzwerk-Quellen (OSC/Web/Art-Net-Merge). Out-of-range-Kanäle werden verworfen,
  der Wert auf 0–255 geklemmt. `assert` wäre unter `python -O` entfernt und würde zu
  stillem Negativ-Index-Wraparound bzw. `IndexError` führen.
- `set_range` nutzt für die obere Grenze weiterhin ein `assert` (interner,
  vertrauenswürdiger Aufrufpfad).

## Gekoppelte Module

- [`output_manager`](output_manager.md) — hält das `universes`-Dict und liest jedes
  Frame per `get_all`.
- `src/core/engine/renderer.py` (bzw. Render-Frame) — nutzt das Schreib-Protokoll.
- [`artnet_input`](artnet_input.md) / [`sacn_input`](sacn_input.md) — schreiben (über
  die AppState-Eingangsschicht) in Universen.

## Tests

- `tests/test_benchmark_universes.py`
- `tests/test_grandmaster_mask_universe.py`
- `tests/test_input_layer.py`
- breit genutzt in Engine-/Render-Tests (z. B. `tests/test_render_frame.py`).

## Quelle

`src/core/dmx/universe.py:5` (Klasse), `:31` `set_channel`, `:56` `set_range`,
`:69` `get_all`.
