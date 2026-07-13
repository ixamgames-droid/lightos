# MIDI-Konflikt-Audit: globales Mapping vs. VC-Widget-Binding (STAB-12)

Datum: 2026-07-13 · Status: reines Audit (kein Code-Change) · Scope: wie eine
eingehende MIDI-Note/CC verteilt wird und ob **eine** Nachricht gleichzeitig ein
globales `MidiMapper`-Mapping **und** ein VC-Widget-Binding auslöst.

Verwandt: [ARCHITECTURE.md → MIDI & Virtual Console](../ARCHITECTURE.md) markiert
die globalen Mappings (`data/midi_mappings.json`, nicht pro Show) ausdrücklich als
Konfliktquelle mit VC-Bindings.

---

## 1. Wer abonniert den Bus — und in welcher Reihenfolge

Beide Ebenen hängen am **selben Singleton-Bus** `get_midi_manager()`
(`src/core/midi/midi_manager.py:349`). Der Bus hält **eine flache Callback-Liste**
`self._callbacks` (`midi_manager.py:72`); `subscribe()` hängt hinten an
(`midi_manager.py:286-287`). Der RX-Thread `_rx_loop` dekodiert jede Rohnachricht
**einmal** und ruft **jeden** Subscriber der Reihe nach auf — Rückgabewerte werden
**ignoriert**, es gibt **kein „consumed"/Kurzschluss**
(`midi_manager.py:328-332`):

```python
for cb in list(self._callbacks):
    try:
        cb(msg)
    except Exception:
        pass
```

| # | Subscriber | Registriert in | Wann konstruiert | Callback-Index |
|---|---|---|---|---|
| 1 | `MidiMapper._on_midi` | `midi_mapper.py:284-285` | `app_state.py:271` (App-Start, früh) | 0 |
| 2 | `VCCanvas._on_midi_raw` | `vc_canvas.py:160-161` | `virtual_console_view.py:400` (beim Öffnen der VC, später) | 1 |
| (∗) | `MidiTeachDialog` (temporär) | beim Öffnen des Teach-Dialogs | on-demand | wechselnd |

**Reihenfolge-Fazit:** Da die App-State den Mapper früh baut und die VC-Canvas erst
beim Öffnen der Ansicht, ist der **Mapper i.d.R. Index 0**, die **VC-Canvas Index 1**.
Beide werden für **dieselbe** Nachricht aufgerufen — der Mapper zuerst, die VC danach.
Es gibt **keine Priorität und keine Konsumierung**: Ebene 2 erfährt nicht, dass
Ebene 1 die Nachricht schon behandelt hat.

---

## 2. Was jede Ebene mit der Nachricht macht

### Ebene 1 — globaler `MidiMapper`
`_on_midi` (`midi_mapper.py:329-340`): erst Learn-Abfrage, sonst iteriert es **alle**
Mappings und feuert **jedes** passende — **kein `break`**:

```python
for mapping in self._mappings:
    if not mapping.midi_in.matches(msg):
        continue
    self._handle_inbound_mapping(mapping, msg)
```

Match-Regel `MidiInBinding.matches` (`midi_mapper.py:87-98`): Gerät (Substring),
Kanal (0 = alle), `trigger_id == data1`, note bindet note_on+note_off. → **Mehrere
globale Mappings auf derselben Note/CC feuern alle** (Intra-Ebene-Mehrfachfeuer).

### Ebene 2 — VC-Canvas / Widget-Bindings
`_on_midi_raw` marshallt thread-sicher per Qt-Signal in den UI-Thread
(`vc_canvas.py:332-335`); `_handle_midi` (`vc_canvas.py:337-357`): erst VC-eigener
Learn, sonst verteilt es an **alle** VC-Widgets **der aktiven Bank** — **kein `break`**:

```python
for widget in widgets:
    if not self.on_active_bank(widget):
        continue
    widget.handle_midi(msg)
```

Widget-Match `VCButton.matches_midi` → `midi_binding_matches`
(`vc_button.py:374-377`, `vc_widget.py:8-21`): Typ (note_on bindet note_off),
Kanal (0 = alle), `midi_data1 == data1`. → **Mehrere Widgets der aktiven Bank mit
gleichem Binding feuern alle** (kann für Gruppen gewollt sein).

**Wichtiger Unterschied:** Die VC filtert auf die **aktive Bank**
(`vc_canvas.py:354-356`) — verdeckte Banks bleiben stumm. Der **Mapper kennt kein
Bank-/Seiten-Konzept**: globale Mappings feuern **unabhängig davon, welche VC-Bank
sichtbar ist**.

---

## 3. Beobachtetes Verhalten — welche Nachricht löst was aus

Szenario: Note_on Ch1 Note 36 kommt herein; global ist Note 36 als „Executor 1 Go"
gemappt **und** ein sichtbarer VC-Button ist per MIDI-Learn auf Note 36 gelegt.

| Schritt | Ausführender Code | Ergebnis |
|---|---|---|
| RX dekodiert 1× | `midi_manager.py:324` | `MidiMessage(note_on, ch1, 36, vel)` |
| Dispatch an Sub 0 (Mapper) | `midi_manager.py:328` | `MidiMapper._on_midi` |
| Mapper matcht + feuert | `midi_mapper.py:337-340` | `Executor 1 → press_btn(0)` (Go) |
| Dispatch an Sub 1 (VC) | `midi_manager.py:328` | `VCCanvas._on_midi_raw` → Signal |
| VC matcht + feuert | `vc_canvas.py:353-357` | VC-Button `trigger_from_midi` |
| **Netto** | — | **BEIDE Aktionen aus EINEM Tastendruck = Doppel-Auslösung** |

**Bewertung: unerwartet / Konflikt.** Für den Anwender ist eine physische Note eine
Absicht; dass sie zwei Aktionen zündet, ist keine dokumentierte/gewollte Semantik,
sondern Folge zweier unabhängiger Subscriber ohne Arbitrierung. Die
Doppel-Auslösung tritt in **drei** Ausprägungen auf:

1. **Cross-Ebene** (global × VC) — der eigentliche STAB-12-Fall (oben).
2. **Intra-Mapper** — zwei globale Mappings auf gleicher Note (`midi_mapper.py:337`).
3. **Intra-VC** — zwei Widgets der aktiven Bank mit gleichem Binding
   (`vc_canvas.py:353`); für Gruppen ggf. gewollt.

### Learn-Modus-Konflikt
VC-Learn (`vc_canvas.py:361-369`, `_handle_midi:339-344`) und Mapper-Learn
(`midi_mapper.py:318-335`) sind **getrennte, unabhängige** Zustände am selben Bus.
Sind zufällig beide „scharf", greift **jede** Ebene dieselbe Nachricht (beide lernen
sie). Zudem gibt es **an keiner Stelle einen Cross-Check beim Lernen**: weder VC noch
Mapper warnen, wenn die zu lernende Note bereits von der jeweils anderen Ebene (oder
mehrfach in der eigenen) belegt ist.

---

## 4. Konkrete Verdachtsstellen (file:line)

| # | Ort | Problem |
|---|---|---|
| V1 | `src/core/midi/midi_manager.py:328-332` (`_rx_loop`) | Dispatch an **alle** Subscriber ohne Konsumierungs-Protokoll; Callback-Rückgaben ignoriert → Wurzel der Cross-Ebene-Doppel-Auslösung. |
| V2 | `src/core/midi/midi_mapper.py:337-340` (`_on_midi`) | Feuert **jedes** passende Mapping, kein `break` → Intra-Mapper-Mehrfachfeuer. |
| V3 | `src/ui/virtualconsole/vc_canvas.py:353-357` (`_handle_midi`) | Feuert **jedes** passende Widget der aktiven Bank, kein `break` → Intra-VC-Mehrfachfeuer. |
| V4 | `vc_canvas.py:361-369` **und** `midi_mapper.py:318-322` (Learn) | Kein Cross-Ebene-Konflikt-Check/Warnung beim MIDI-Learn. |
| V5 | Mapper hat **kein** Bank-Konzept (vgl. `vc_canvas.py:354-356`) | Globale Mappings feuern bank-unabhängig — Cross-Ebene-Kollision auch auf nicht sichtbaren VC-Seiten möglich. |

---

## 5. Minimal-Fix-Skizzen

### Option A — Priorität „VC vor global" via Konsumierungs-Protokoll (behaviorale Änderung)
Bus so erweitern, dass ein Subscriber die Nachricht als „konsumiert" markieren kann,
und die Subscriber so ordnen, dass **VC zuerst** geprüft wird:

- `midi_manager.py:_rx_loop`: `if cb(msg): break` (Callback gibt truthy zurück, wenn
  er die Nachricht behandelt hat).
- Subscribe-Reihenfolge umkehren (VC vor Mapper) **oder** eine explizite Prioritäts-Zahl
  pro Subscriber einführen.
- `VCCanvas._handle_midi` müsste `True` liefern, wenn **mindestens ein** aktives Widget
  gematcht hat (`handle_midi` gibt das bereits pro Widget zurück).

Risiko: berührt **alle** Subscriber (inkl. Teach-Dialog, Feedback). `note_on`/`note_off`
müssten konsistent behandelt werden (sonst „hängende" Flash-States). **Nicht** als
Ein-Zeilen-Fix umsetzen — braucht Tests über alle Subscriber.

### Option B — Konflikt-Warnung beim Learn (nicht-behavioral, empfohlen)
Beim Zuweisen einer Bindung (VC: `vc_button.accept_midi` / `vc_canvas.start_midi_learn`;
global: `MidiMapper.start_learn`-Callback) die **jeweils andere** Ebene auf ein bereits
belegtes `(msg_type, channel, data1)` prüfen und den Anwender warnen (Dialog/Log),
**ohne** das Laufzeitverhalten zu ändern. Löst V4, verhindert unbeabsichtigte
Doppelbelegung an der Quelle. Umfang: klein, aber > 1 Zeile (Nachschlage-Helfer +
Warn-Hook je Learn-Pfad).

### Option C — Intra-Ebene-Mehrfachfeuer entschärfen (optional, mit Vorbehalt)
`midi_mapper.py:_on_midi` nach dem ersten Treffer `return`/`break`. Verhindert V2,
**ändert aber** die dokumentierbare Möglichkeit, mehrere globale Mappings auf einer Note
zu stapeln — daher **nicht** eindeutig „sicher". Für VC (V3) ist Mehrfachfeuer teils
gewollt (Gruppen) → dort **nicht** ändern.

### Zur „sicheren Ein-Zeilen-Verbesserung"
Es gibt **keine** risikofreie **Ein-Zeilen**-Änderung, die die Cross-Ebene-Doppel-
Auslösung beseitigt: Sie entsteht strukturell aus zwei unabhängigen Bus-Subscribern.
Jede Verhaltensänderung (Option A/C) berührt bewusst-gewollte Fälle und braucht Tests.
Die **sicherste kleine** Verbesserung ist die **nicht-behaviorale** Learn-Warnung
(Option B). Empfehlung an David: **Option B umsetzen** (warnt vor Konflikt beim Learn),
Option A nur mit vollständiger Subscriber-/Regressionsabdeckung.

---

## 6. Regressionstest-Idee (`tests/test_midi_vc_conflict.py`, headless)

Dokumentiert das **aktuelle** Verhalten und dient als Guard für einen künftigen Fix.

1. `QT_QPA_PLATFORM=offscreen`. Minimal-`app_state` mit `playback_engine`-Stub, dessen
   `get_executor(slot).press_btn(...)` einen Aufruf protokolliert.
2. Mapper (`get_midi_mapper(state)`) ein Mapping `executor_go` auf `note_on ch1 data1=36`
   hinzufügen (`add_mapping`).
3. `VCCanvas()` bauen, einen `VCButton` auf die **aktive** Bank legen und via
   `accept_midi(1, 36, "note_on")` binden; eine Aktion mit sichtbarem Seiteneffekt wählen.
4. **Eine** `MidiMessage(port, 1, "note_on", 36, 127)` einspeisen. Robust im Test:
   die beiden Subscriber direkt aufrufen — `mapper._on_midi(msg)` und
   `canvas._handle_midi(msg)` (umgeht Bus-Thread + Qt-Marshalling). Alternativ über
   `get_midi_manager()._on_message([...], port)` und den RX-Thread kurz joinen.
5. **Ist-Assertion (heute):** **beide** Seiteneffekte traten auf → Doppel-Auslösung
   bestätigt (Test dokumentiert „unerwartet").
6. **Soll-Assertion nach Fix:** je nach gewählter Option — bei A genau **eine** Aktion
   (VC gewinnt), bei B eine **Warnung** beim Learn und **unverändertes** Feuern.

Zusatz-Fälle: (a) Intra-Mapper — zwei Mappings auf Note 36, prüfen dass **beide** feuern
(V2); (b) VC-Bank-Isolation — Widget auf **inaktiver** Bank feuert **nicht**, das globale
Mapping aber **schon** (V5, bank-unabhängig).
