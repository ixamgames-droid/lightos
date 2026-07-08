# OSC- & Timecode/MTC-Remote-Eingang-Audit (2026-07-08)

**Auftrag:** AUD-08 — verifizierte Bug-/Risiko-Liste für den OSC- (`src/core/osc/osc_server.py`, 171 Z.)
und MTC-Timecode-Eingang (`src/core/timecode/mtc_reader.py`, 184 Z.). Beide mutieren rohen Live-State
aus eigenem Thread; **0 Tests** (per `ls tests/` verifiziert).

**Methode:** 4-Dimensionen-Workflow (OSC-Input-Robustheit · OSC-Semantik/Parität · MTC-Frame-Korrektheit ·
MTC-Lifecycle/Thread), jedes Finding **adversarial verifiziert** (je 2 Skeptiker). **22 Agenten,
9 Roh-Befunde → 7 CONFIRMED, 1 PLAUSIBLE, 1 zurückgewiesen.** **Kein neuer P1/P2** — die beiden P2 sind
**Parität** zu bereits bekannten Web-Items. Zeilennummern gegen `main` (`0b56ef4`).

## Positiv bestätigt (kein Bug)

- **OSC-Handler robust gekapselt:** Alle 6 Handler in `try/except: pass`; die int-Parses der Slot/
  Universe/Channel-Teile sind bounds-checked, der Fader `float()`-geklemmt (0..1). `set_channel` klemmt
  Kanal/Wert selbst. Kein Crash/Fehldispatch durch manipulierte Adressen.
- **Cross-Thread sauber:** `ThreadingOSCUDPServer` bearbeitet jede Nachricht in eigenem Thread, aber
  **alle** mutierten Ziele sind gelockt — `Universe.set_channel` (`_lock`), `CueStack.go()/back()`
  (`_lock`), `clear_programmer` (`_prog_lock`); `set_blackout` setzt nur ein bool. **Keine** Race mit
  beobachtbarem Schaden.
- **MTC-Dekodierung spec-konform:** SysEx-Full-Frame (`msg[5..8]` durch doppelten `len>=10`-Check
  sicher), Nibble-/Masken-Arithmetik (frames 5 Bit, sec/min 6 Bit, `hours & 0x1F`, `fps_code`), alle 4
  fps-Codes + Default. **MTC-Lifecycle** (attach/detach/reattach, `_buf`-Nutzung, no-rtmidi-No-op) sauber
  — kein Use-after-free, kein Thread-Tod.

---

## Befunde

### 🟠 P2 — Parität (kein neuer Fix nötig, in bestehende Items falten)

| ID | Stelle | Befund | Parität |
|----|--------|--------|---------|
| **OSC-01** | `osc_server.py:125-138` | `/lightos/ch/{u}/{c}` ruft `set_channel` **direkt** ins Live-Universe → der 44-Hz-Renderer committet gepatchte Spans jeden Frame und überschreibt den OSC-Wert nach ~23 ms; nur auf **nicht** gepatchten Kanälen hält er. `/lightos/ch` steuert reale Fixtures faktisch nicht. | **= WEB-01** (`/api/channel`). Gemeinsamer Fix: beide Remote-Kanal-Schreiber über eine Input-/Override-Ebene (wie `input_layer`) statt direkt ins Live-Universe. → in **WEB-01** vermerkt. |
| **OSC-02** | `osc_server.py:27/48` | OSC bindet `0.0.0.0:7770` **ohne Auth/Token** (aktiviert via `main_window.py:1623`) → jeder im LAN kann go/back/blackout/clear/exec/ch senden. | **= NET-01** (Web `0.0.0.0` auth-los). Gemeinsamer Bind-/Token-Ansatz für ALLE externen Eingänge (Web + OSC). → in **NET-01** vermerkt. |

### 🟡 P3 — neu (klein, konkret)

| ID | Stelle | Befund | Fix-Richtung |
|----|--------|--------|--------------|
| **OSC-04** | `osc_server.py:89` | **`_handle_blackout` invertiert bei nicht-numerischen Args:** `val = bool(args[0])` → `bool("0")`/`bool("off")` = True → Blackout **AN** obwohl AUS gemeint (kein Exception → `except` greift nicht). Bei getypten OSC-int/float (TouchOSC/Lemur) korrekt; nur bei String-Typetag falsch. | Typ-tolerant interpretieren: numerisch `float(raw) >= 0.5`, String gegen `{"0","off","false","no",""}` prüfen. |
| **MTC-02** | `mtc_reader.py:117` | **Feuern bei `piece==7` ohne Vollständigkeits-/Reihenfolge-Prüfung:** bei Mid-Stream-Attach oder Rückwärts-Transport wird ein Frame aus **gemischten** alten+neuen Nibbles zusammengesetzt → kurzzeitig falscher Timecode. | Bitmaske der seit dem letzten Feuern empfangenen Pieces führen; nur feuern, wenn ein vollständiger 0..7-Satz vorliegt, dann zurücksetzen. |
| **MTC-01** | `mtc_reader.py:131` | **`adj_frames = frames + 2` ohne Wrap/Sekunden-Carry:** erzeugt Frame-Nummern ≥ fps (z. B. 30 fps → „:31") → falscher Timecode/Absolutzeit. | Timecode nach dem +2 normalisieren (Frame in Sekunden übertragen, Cascade min/std). **Achtung:** korrektes Normalisieren muss Drop-Frame (29,97) berücksichtigen — eigene sorgfältige Runde, nicht als Schnellfix. |
| **MTC-03** | `mtc_reader.py:167/173` | **Lock-freie `time()`/`format()`:** ein Cross-Thread-Leser kann ein gemischtes (h,m,s,f)-Tupel sehen (Torn-Read). **Latent** — der einzige reale Consumer (`midi_view._on_mtc`) bekommt den konsistenten Snapshot über die `_fire`-Callback-Args (per Qt-Signal marshalled); heute kein Live-Defekt, aber eine Falle für künftige Poll-Consumer. | Tupel unter einem Lock lesen/schreiben, oder `time()` gibt eine unter Lock kopierte Momentaufnahme. |

_(Das flächendeckende `except: pass` ohne Logging wurde als reines Observability-Nit **zurückgewiesen** — kein Defekt.)_

---

## Zusammenfassung

Der OSC/MTC-Eingang ist **grundsolide**: robuste Handler-Kapselung, korrekte int/float-Guards, saubere
Cross-Thread-Locks, spec-konforme MTC-Dekodierung. **Kein neuer P1/P2.** Die zwei P2 sind exakte Parität
zu **WEB-01** (Remote-Kanal am Renderer vorbei) und **NET-01** (auth-loser `0.0.0.0`-Bind) — das bestätigt,
dass diese beiden als **querschnittliche** Themen aller externen Eingänge (Web + OSC, vermutlich auch
MIDI-in) mit **einem** gemeinsamen Fix gelöst werden sollten (Produkt-Entscheidung Davids). Neu sind nur
vier P3 (OSC-Blackout-Coercion, MTC-Frame-Wrap, MTC-Vollständigkeit, MTC-Torn-Read). Empfehlung: die zwei
sauber+sicher fixbaren P3 (OSC-04 Blackout-Coercion, MTC-02 Vollständigkeits-Gate) direkt beheben; MTC-01
(Frame-Wrap mit Drop-Frame) und MTC-03 (Torn-Read) als dokumentierte P3 parken.
