# serial_process — EnttecProcessProxy

## Zweck

**STAB-08 / OUT-02⁺:** Betreibt die serielle Enttec-Ausgabe in einem EIGENEN PROZESS.
Eine native Access Violation im FTDI-/usbser-Kerneltreiber (USB mitten im `WriteFile`
abgezogen) ist in reinem Python NICHT fangbar und reißt den ganzen Prozess mit. Läuft
der serielle Write in einem separaten Prozess, killt eine solche AV nur den Worker; der
Hauptprozess (GUI/Engine) lebt weiter und respawnt den Worker.

`EnttecProcessProxy` ist schnittstellen-gleich zu [`EnttecPro`](enttec_pro.md)
(`send_dmx`, `close`, `is_open`, `is_disabled`, `port`) und für den `OutputManager`
transparent austauschbar.

## Konfiguration / Schalter

| Schalter | Wirkung |
|---|---|
| `LIGHTOS_SERIAL_INPROC` (Env) | NICHT gesetzt → dieser Prozess-Proxy wird gewählt (Default, auch Windows-`spawn`). Gesetzt → In-Prozess-`EnttecPro`. Auswahl in `output_manager._make_enttec_device`. |
| `FRAME_INTERVAL = 1/44` | Sende-Rate des Worker-Loops. |
| `OPEN_RETRY_S = 1.0` | Worker-internes, gedrosseltes (Wieder-)Öffnen des Ports. |
| `RESPAWN_EVERY_S = 3.0` | Drossel für den Parent-Respawn eines toten Workers. |
| `DMX_BYTES = 512` | Größe des Shared-Buffers. |
| Status | Shared `Value`: `ST_CONNECTING=0`, `ST_OK=1`, `ST_DISABLED=2` (vom Worker geschrieben, vom Parent für UI lesbar). |

## Threading- / Prozessmodell

- Kontext `mp.get_context("spawn")` — erzwungen für plattformgleiche AV-Isolation. Der
  Worker importiert NUR `enttec_pro` (serial + stdlib, KEIN Qt/app_state).
- **Latest-wins, entkoppelt:** Der Parent schreibt das aktuelle 512-Byte-Frame in einen
  Shared `Array` (`memmove` unter `get_lock`) — KEIN blockierendes IPC pro Frame. Der
  44-Hz-Output-Thread hängt damit NIE an einem seriellen Write (beseitigt zugleich die
  alte „Output-Thread hängt in write()"-Klasse, STAB-02/04).
- Der Worker (`_serial_worker_loop`) liest den Puffer mit ~44 Hz und sendet ihn über
  einen internen `EnttecPro`. Der Loop ist voll injizierbar und damit in-Prozess testbar.

## Fehler- / Watchdog-Verhalten

- Stirbt der Worker (native AV / Kill), erkennt der Parent das über `is_alive()` und
  respawnt ihn gedrosselt (`_maybe_respawn`, `RESPAWN_EVERY_S`); das aktuelle Frame wird
  verworfen.
- Fängt der Port (noch) nicht an, öffnet der Worker ihn gedrosselt erneut
  (`OPEN_RETRY_S`), ohne selbst zu sterben.
- Ordinäre (fangbare) Serial-Fehler erledigt der In-Worker-`EnttecPro` (OUT-02
  Watchdog/Reconnect) — kein Respawn nötig.
- `close()` setzt das Stop-Flag, joint sauber, sonst `terminate()`. Idempotent.

## Gekoppelte Module

- [`output_manager`](output_manager.md) — `_make_enttec_device` instanziiert den Proxy
  (mit Fallback auf In-Prozess bei Startfehler).
- [`enttec_pro`](enttec_pro.md) — das vom Worker betriebene Gerät.

## Tests

- `tests/test_serial_process.py`
- `tests/test_generator_spawn_safe.py`

## Quelle

`src/core/dmx/serial_process.py:97` (Klasse), `:41` `_serial_worker_loop`,
`:87` `_worker_main`, `:138` `_maybe_respawn`, `:150` `send_dmx`, `:174` `close`.
