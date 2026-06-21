> ## ⚠️ HISTORISCH — überholt durch spätere Fixes
>
> **Dieses Dokument beschreibt den Debug-Stand vom 2026-05-27 und ist nur noch als History relevant.**
> Die hier vermuteten Haupt-Crash-Ursachen wurden inzwischen behoben:
>
> - **Hypothese B** (nativer Hard-Crash außerhalb Python) und **Hypothese C** (Event-Sturm durch
>   mehrere Subscriber/Views) gelten als **adressiert** durch:
>   - **Thread-Safety-Runde 2026-06-08** — `RLock` als `_io_lock`, entkoppelter `MidiDispatch` über
>     `_rx_queue`, Drop-on-Overload statt blockierendem Callback.
>   - **MIDI-Page-Crash-Fix 2026-06-14** — `_page_changed_sig` (Qt-Signal-Marshalling); QWidgets werden
>     nicht mehr cross-thread gebaut.
> - **Offen bleibt nur Hypothese A** (WinMM + Gerätetreiber/Port-Zustand unter Last) — rein
>   hardwareabhängig (`needs_hardware`) und nur am echten Gerät unter Last verifizierbar; dafür
>   gibt es keinen offenen Code-Punkt mehr (B-9 = diese Markierung, in
>   `docs/OPEN_POINTS_OVERVIEW.md` §5 als erledigt geführt).
>
> Offene Aufgaben werden ausschließlich in `docs/OPEN_POINTS_OVERVIEW.md` gepflegt, nicht hier.

---

# MIDI Crash Debug Notes

Stand: 2026-05-27 (siehe HISTORISCH-Hinweis oben)
Projekt: LightOS (`lightos-main`)

## Kontext
- Problem: Software stürzt nach MIDI-Connect und Fader-Bewegung (APC mini mk2) weiterhin sporadisch ab.
- Ziel: Bidirektionales MIDI-Mapping (Inbound + Outbound Feedback) stabil machen.

## Bereits umgesetzt

### 1) Bidirektionales MIDI-Mapping
- Neues Mapping-Modell mit:
  - `target`, `midi_in`, `button_mode`, `midi_out`
  - ON/OFF-Feedback via Velocity
- Inbound-Engine:
  - `toggle`, `flash`, `continuous`
- Outbound-Feedback-Engine:
  - asynchron über Queue + Worker
  - Zustandspolling + Feedback bei Statusänderung

Relevante Datei:
- `src/core/midi/midi_mapper.py`

### 2) MIDI-Manager robuster gemacht
- Thread-Safety für Output-Senden (`RLock`)
- Output-Port-Reuse (kein unnötiges Re-Open bei jedem Event)
- `current_output_name()` eingeführt
- `close_all()` schließt sauber Output + Virtual-Output

Relevante Datei:
- `src/core/midi/midi_manager.py`

### 3) Feedback-Loop entschärft
- Dedupe/Throttle im Feedback-Worker (verhindert identische Spam-Sends)
- Zustandspolling in den Worker integriert
- Timer-basierter Polling-Ansatz entfernt

Relevante Datei:
- `src/core/midi/midi_mapper.py`

### 4) MIDI-Input-Dispatch entkoppelt
- Native MIDI-Callback schreibt nur noch in Queue
- Separater `MidiDispatch`-Thread decodiert und verteilt Events
- Bei Überlast wird gedroppt statt Callback zu blockieren

Relevante Datei:
- `src/core/midi/midi_manager.py`

## Tests, die gelaufen sind

### Unit-Tests
- `python -m unittest tests.test_midi_mapper -v`
- Ergebnis: 4/4 OK
  - Toggle-Inbound + Feedback
  - Continuous Grand Master
  - Config Roundtrip
  - Feedback-Stress (Port-Reuse)

### Hardware-Testscript
- `examples/midi_color_chase_test.py`
- Lief erfolgreich auf:
  - `APC mini mk2`
  - (zuvor auch `MIDIOUT2 (APC mini mk2)` sichtbar)

## Weitere Features, die parallel ergänzt wurden
- Snap-Bibliothek erweitert:
  - Multi-Select
  - „Chase +“: Sequence aus mehreren Snaps erzeugen
- VC erweitert:
  - `FunctionToggle` / `FunctionFlash` im VCButton
  - SpeedDial kann `Target=Function` und `function.speed` steuern

## Vermutete Rest-Ursachen für den Crash

### Hypothese A (hoch): WinMM + Gerätetreiber/Port-Zustand unter Last
- Trotz Entkopplung kann WinMM bei schnellem CC-Strom + parallelem OUT-Feedback intern instabil werden.
- Besonders kritisch bei gleichzeitiger In/Out-Nutzung desselben Geräts.

### Hypothese B (mittel): Ungefangene Exception/Hard-Crash außerhalb Python
- `app_stderr.txt`/`err.txt` waren teils leer.
- Das deutet auf möglichen nativen Crash (DLL/Backend) statt regulärem Python-Traceback.

### Hypothese C (mittel): Event-Sturm durch mehrere Subscriber/Views
- Mehrere MIDI-Subscriber (Mapper, VC-Canvas, MIDI-View) verarbeiten ggf. denselben Event-Pfad.
- Könnte in Randfällen zu Lastspitzen führen, obwohl bisher kein eindeutiger Python-Fehlerlog vorliegt.

## Vorschläge für den nächsten Modelllauf
1. „Safe Mode“ für MIDI hinzufügen:
   - OUT-Feedback global deaktivierbar (nur Inbound)
   - Optionales Rate-Limit für eingehende CC (z. B. 60 Hz pro CC)
2. Strukturierte Crash-Telemetrie:
   - Ring-Buffer-Log mit letzten 500 MIDI-Events
   - letzte Port-Operationen + Thread-Status
   - Dump bei `sys.excepthook` und `faulthandler`
3. WinMM-spezifische Schutzschicht:
   - Reconnect-Backoff
   - Port-Fail Fast + Cooldown
4. Subscriber-Architektur prüfen:
   - zentraler Dispatch, optionale Priorisierung
   - doppelte Verarbeitung minimieren

## Wichtige Dateien (für Übergabe an anderes Modell)
- `src/core/midi/midi_manager.py`
- `src/core/midi/midi_mapper.py`
- `src/ui/views/midi_view.py`
- `tests/test_midi_mapper.py`
- `examples/midi_color_chase_test.py`
- `src/ui/views/snap_file_panel.py`
- `src/ui/virtualconsole/vc_button.py`
- `src/ui/virtualconsole/vc_speedial.py`
