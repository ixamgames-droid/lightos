# osc_server

`src/core/osc/osc_server.py`

## Zweck

Empfängt **Open Sound Control**-Nachrichten (UDP) und mappt sie auf App-State-
Aktionen — für Tablet-Remotes wie TouchOSC / Lemur. App-weites **Singleton** über
`get_osc_server()`; Start/Stopp über das Menü in
`src/ui/main_window.py` (`_toggle_osc_server`, Port 7770). Braucht `python-osc`
(`HAS_OSC`); fehlt es, wirft `start()` mit Installationshinweis.

Der Server läuft in einem `ThreadingOSCUDPServer` auf einem Daemon-Thread
(`OSC-Server`). `OscSender` ist das Gegenstück zum Zurücksenden (z. B.
TouchOSC-Feedback).

## Unterstützte Nachrichten / Adressen

Default-Adressschema (TouchOSC/Lemur-kompatibel):

| Adresse | Wirkung |
|---------|---------|
| `/lightos/go` | globales GO auf die GO-Zielliste (siehe unten) |
| `/lightos/back` | globales BACK auf die GO-Zielliste |
| `/lightos/blackout {1\|0}` | Blackout an/aus |
| `/lightos/programmer/clear` | Programmer leeren |
| `/lightos/exec/{n}/go` \| `/back` \| `/stop` | Executor n Taste |
| `/lightos/exec/{n}/fader {f}` | Executor n Fader (0.0–1.0) |
| `/lightos/ch/{u}/{c} {v}` | Universe u, Kanal c, Wert v (0–255) |

**GO-Zielliste** (`/lightos/go`, `/lightos/back`; gleiche Regel wie Leertaste,
Kommandozeile `go`/`back` ohne Nummer und Web-Remote, zentral in
`src/core/cueliste_ziel.py`): die im Playback gewählte Cueliste, wenn sie auf
einem Executor liegt; sonst die des ersten belegten Executors der aktuellen Page;
sonst die erste Cueliste auf irgendeinem Executor; liegt keine auf einem
Executor, wird die gewählte (bzw. erste) weitergeschaltet — ohne Licht.
`/lightos/exec/{n}/…` trifft immer genau Executor n.

**Typ-tolerantes Blackout (`_as_on`, OSC-04):** Ein String-Argument `'0'`/`'off'`
ist in Python truthy — `bool('0') == True`. Darum werden Strings gegen die
üblichen Aus-Token (`""`,`0`,`off`,`false`,`no`) geprüft und getypte int/float
numerisch geschwellt (`>= 0.5`), damit `/blackout 0` wirklich ausschaltet.

## Mapping- / Learn-Mechanik

**Kein Learn** und **kein editierbares Mapping** — die Adressen sind fest
verdrahtet (`Dispatcher.map` in `start()`). Zusätzliche Handler lassen sich
programmatisch über `add_handler(address, fn)` vor dem Start registrieren
(`_custom_handlers` werden beim `start()` mitgemappt). Adress-Wildcards (`exec/*`,
`ch/*`) werden im Handler selbst geparst (`address.strip("/").split("/")`).

## Gekoppelte VC-/Engine-Teile

- **`src/core/app_state.py`** — Zugriff über `get_state()`: `cue_stacks`,
  `output_manager.set_blackout`, `clear_programmer`, `playback_engine.executors`,
  `universes[u].set_channel`.
- **`src/ui/main_window.py`** — Menü-Toggle `_act_osc` startet/stoppt den Server.

## Tests

- `tests/test_osc_mtc_robustness.py` — u. a. `_as_on`-Typ-Toleranz (OSC-04) und
  robustes Adress-Parsing.
- `tests/test_midi_view.py` — berührt OSC/MTC-Teile der Input-View.

Siehe auch das Audit [../../OSC_TIMECODE_AUDIT_2026_07_08.md](../../OSC_TIMECODE_AUDIT_2026_07_08.md).

## Quelle (`file:line`)

- `OscServer` + Adressschema-Docstring — `src/core/osc/osc_server.py:14`
- `start()` (Dispatcher-Map) — `src/core/osc/osc_server.py:35`
- `_handle_blackout()` / `_as_on()` — `src/core/osc/osc_server.py:87`
- `_handle_exec()` — `src/core/osc/osc_server.py:113`
- `_handle_channel()` — `src/core/osc/osc_server.py:138`
- `OscSender` — `src/core/osc/osc_server.py:154`
- Singleton `get_osc_server()` — `src/core/osc/osc_server.py:180`
