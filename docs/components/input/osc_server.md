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
| `/lightos/ch/{u}/{c} {v}` | Universum u, Kanal c, Wert v (0–255) |

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

**Druck-Schwelle für Tasten (`_is_pressed`, OSC-05):** `/lightos/go`,
`/lightos/back` und `/lightos/exec/{n}/go` \| `/back` \| `/stop` lösen nur beim
**Drücken** aus, nicht beim Loslassen (TouchOSC/Lemur senden 1.0 und danach 0.0).
Die Skala wird aus dem Wert erkannt, die Schwelle ist die halbe Skala:

| Erstes Argument | gedrückt, wenn |
|---|---|
| kein Argument oder OSC-Nil | immer (reiner Auslöser) |
| Wert 0–1 (auch int 0/1, True/False) | ab 0,5 |
| Wert über 1 bis 100 (Prozent) | ab 50 |
| Wert über 100 (0–127 bzw. 0–255) | immer |
| NaN | nie |
| Text | als Zahl gelesen; sonst wie `_as_on` (`off`, `false`, `no`, `0`, leer = nicht gedrückt) |

`/lightos/exec/{n}/fader` ist davon nicht betroffen (Wert 0.0–1.0, geklemmt).

## Mapping- / Learn-Mechanik

Die `/lightos/…`-Adressen oben sind fest verdrahtet (`Dispatcher.map` in
`start()`) und gelten immer. **Zusätzlich** (OSC-06) gibt es freie Zuordnungen
mit Mustern, Lernen und Rückmeldung — `src/core/osc/osc_zuordnung.py`:

- Der Dispatcher (`_ZuordnungsDispatcher`) reicht **jede** eingehende Nachricht,
  auch `/lightos/…`, an `_freie_zuordnung` weiter. Dort vergleicht
  `OscZuordnung.empfange` im OSC-Thread nur und reiht eine Aktion ein; angewandt
  wird im GUI-Thread (`abarbeiten`, per Queued-Signal). Trifft eine Nachricht eine
  feste Adresse und eine Zuordnung, wirkt sie auf beiden Wegen.
- Muster in der Spalte „Adresse“: `*`, `?`, `[..]`, `{a,b}`; `{n}` liefert die
  Zielnummer (Zielnummer = n + Versatz). Alternativ nimmt „Nr. aus Arg.“ das erste
  Argument als Zielnummer.
- Tasten mit Wert lösen auch hier nur beim Druck aus (ab der halben Skala des
  gewählten Bereichs), ohne Argument immer.
- **Lernen:** die nächste eingehende Adresse landet in der gewählten Zeile
  (ohne Auswahl: neue Zeile); die letzte Zahl wird zu `{n}`.
- **Rückmeldung** (`OscRueckmeldung`): Executor-Fader, Executor aktiv, Cue-Nummer,
  Grand Master und Blackout gehen über `OscSender` an ein Ziel (IP:Port), nur bei
  Änderung; mit Echo-Schutz.
- Gespeichert in `osc_zuordnungen.json` im App-Datenordner (nicht in der Show).

Bedienung: Menü **Ausgabe** → **OSC-Zuordnungen & Rückmeldung…**
(`src/ui/widgets/osc_einstellungen_dialog.py`) mit den Reitern „Eingang“ (Haken
„Zuordnungen aktiv“, Knöpfe „+ Zuordnung“, „Entfernen“, „Lernen“) und
„Rückmeldung“, unten „Übernehmen“ und „Schließen“. Schritt für Schritt:
[Anleitung OSC](../../anleitung_osc/ANLEITUNG.md).

Zusätzliche Handler lassen sich weiterhin programmatisch über
`add_handler(address, fn)` vor dem Start registrieren (`_custom_handlers` werden
beim `start()` mitgemappt). Adress-Wildcards der festen Adressen (`exec/*`,
`ch/*`) werden im Handler selbst geparst (`address.strip("/").split("/")`).

## Gekoppelte VC-/Engine-Teile

- **`src/core/app_state.py`** — Zugriff über `get_state()`: `cue_stacks`,
  `output_manager.set_blackout`, `clear_programmer`, `playback_engine.executors`,
  `universes[u].set_channel`.
- **`src/ui/main_window.py`** — Menü-Toggle `_act_osc` startet/stoppt den Server;
  Menüeintrag „OSC-Zuordnungen & Rückmeldung…“ öffnet den Dialog.
- **`src/core/osc/osc_zuordnung.py`** / **`src/ui/widgets/osc_einstellungen_dialog.py`**
  — freie Zuordnungen, Lernen, Rückmeldung (OSC-06).

## Tests

- `tests/test_osc_mtc_robustness.py` — u. a. `_as_on`-Typ-Toleranz (OSC-04) und
  robustes Adress-Parsing.
- `tests/test_midi_view.py` — berührt OSC/MTC-Teile der Input-View.

Siehe auch das Audit [../../OSC_TIMECODE_AUDIT_2026_07_08.md](../../OSC_TIMECODE_AUDIT_2026_07_08.md).

## Quelle (`file:line`)

- `OscServer` — `src/core/osc/osc_server.py:32`
- `start()` (Dispatcher-Map) — `src/core/osc/osc_server.py:70`
- `_freie_zuordnung()` — `src/core/osc/osc_server.py:109`
- `_is_pressed()` (Druck-Schwelle) — `src/core/osc/osc_server.py:132`
- `_handle_blackout()` / `_as_on()` — `src/core/osc/osc_server.py:197`
- `_handle_exec()` — `src/core/osc/osc_server.py:223`
- `_handle_channel()` — `src/core/osc/osc_server.py:250`
- `OscSender` — `src/core/osc/osc_server.py:268`
- Singleton `get_osc_server()` — `src/core/osc/osc_server.py:311`
