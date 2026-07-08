# Web-Remote-Audit — `src/web/app.py` (2026-07-08)

**Auftrag:** AUD-05 — verifizierte Bug-/Risiko-Liste für den Web-Remote (Flask + SocketIO),
den externen Steuer-Eingang von LightOS (schreibt rohe DMX-Kanäle, GO/Back/Blackout/Fader,
leert den Programmer). Die Datei hatte **0 Tests**.

**Methode:** 4-Dimensionen-Workflow (Eingabe-Validierung/Clamping · Cross-Thread-Zugriff ·
Netz/Auth · Test-Lücke), jedes Finding **adversarial gegen den echten Code verifiziert**
(21 Agenten, 16 CONFIRMED, 1 als „kein Bug" korrekt zurückgewiesen). Zeilennummern gegen
`src/web/app.py` @ `main` geprüft.

**Positiv bestätigt (kein Bug):** `SECRET_KEY` ist korrekt behandelt — aus ENV
`LIGHTOS_FLASK_SECRET`, sonst `secrets.token_hex(32)` (zufällig pro Start, **kein** hardcodierter
Default; `app.py:35`). Die Index-Guards (`0 <= idx < len(executors)`, `1 <= channel <= 512`,
`universe in state.universes`) und die Wert-Clamps (`max(0,min(255,·))`, `max(0.0,min(1.0,·))`)
sind vorhanden und korrekt — es gibt **keine** Out-of-range-Schreib- oder Negativ-Index-Lücke.

---

## Befunde (nach Severity)

### 🔴 P1

| ID | Stelle | Befund | Fix-Richtung |
|----|--------|--------|--------------|
| **NET-01** | `app.py:170` | **Web-Remote ohne jede Authentifizierung, gebunden an `host="0.0.0.0"`** → im gesamten LAN erreichbar. Jeder im selben (Venue-/Gäste-)WLAN kann ohne Hürde `POST /api/blackout`, `/api/channel/<u>/<c>`, `/api/executor/<n>/go`, Fader und `/api/programmer/clear` auslösen — d. h. **eine laufende Show fremd blackouten/übersteuern**. Kein Token, kein PIN, keine Origin-Bindung. | Bind default auf `127.0.0.1`, LAN-Bind nur per bewusster Option; optional ein PIN/Token (Header oder Query), das der Verbindungs-Dialog anzeigt. Mindestens: der Dialog muss die LAN-Exposition unmissverständlich benennen (siehe NET-02). |

### 🟠 P2

| ID | Stelle | Befund | Fix-Richtung |
|----|--------|--------|--------------|
| **NET-02** | `main_window.py:1606` | **Irreführender Verbindungs-Dialog:** zeigt `localhost:5000`, obwohl der Server auf `0.0.0.0` (das ganze LAN) bindet. Der Nutzer unterschätzt die Exposition und aktiviert das Remote im offenen WLAN. | Dialog zeigt die tatsächliche LAN-IP + Warnhinweis; koppelt an NET-01 (Bind-Wahl). |
| **NET-03** | `app.py:36` | **`cors_allowed_origins="*"`** am SocketIO ohne CSRF-/Origin-Schutz → eine beliebige (bösartige) Webseite, die der Operator im selben Netz öffnet, kann sich mit dem SocketIO verbinden und Steuerbefehle senden. Verschärft NET-01. | Origins auf die eigene UI/`localhost` beschränken; mit Auth (NET-01) entschärft. |
| **WEB-01** | `app.py:108` | **`POST /api/channel` schreibt am 44-Hz-Renderer vorbei** direkt via `universes[u].set_channel(...)`. Für **gepatchte** Adressen überschreibt `_render_frame` (Output-Thread) jeden Frame den Span mit den gerenderten Werten → der Web-Wert hält höchstens ~23 ms und wird zurückgesetzt (Regler „flackert"/hält nicht). Auf **un**gepatchten Adressen bleibt er stehen. Inkonsistentes, verwirrendes Verhalten (kein Crash). | Rohe Kanal-Sets in eine Web-/Input-Override-Ebene leiten (analog `input_layer`), die der Renderer respektiert — oder das Verhalten dokumentieren/auf ungepatchte Adressen beschränken. |

### 🟡 P3

| ID | Stelle | Befund | Fix-Richtung |
|----|--------|--------|--------------|
| **WEB-02** | `app.py:85`, `app.py:105` | **Ungekapselte `float()`/`int()`-Coercion** in `api_fader` (`level`) und `api_channel` (`value`): nicht-numerischer Payload (`"abc"`, `[1]`, `null`) bzw. `Infinity`/`NaN` (Flask-JSON parst diese) → `ValueError`/`TypeError`/`OverflowError` **vor** dem Clamp, ungefangen → **HTTP 500**. Auth-los per LAN triggerbar. Kein State-Corrupt. | Coercion in `try/except` (Default beibehalten) bzw. `math.isfinite`-Prüfung vor `int()`. |
| **WEB-03** | `app.py:139`, `app.py:148` | **`on_fader`/`on_blackout` ohne None-Guard:** Signaturen `def on_fader(data)` deref'en sofort `data.get(...)`. Emittet ein Client das Event **ohne Payload** → `data=None` → `AttributeError` (bzw. `TypeError` fehlendes Arg). `on_go`/`on_back` machen es richtig (`data=None`-Default, kein Deref). Nur Handler-Exception (von SocketIO geloggt), kein Prozess-Crash. | `def on_fader(data=None)` + `data = data or {}`; Coercion wie WEB-02 kapseln. |
| **WEB-04** | `app.py:64-65` (auch `69-72`, `127-128`, `134-135`) | **TOCTOU auf `state.cue_stacks[0]`:** `if state.cue_stacks: state.cue_stacks[0].go()` — wird die Liste zwischen Check und Index-Zugriff aus einem anderen Thread geleert (Show-Load/Reset), `IndexError`. Enges Fenster, aber der Web-Thread läuft echt nebenläufig zum UI-/Output-Thread. | Lokale Referenz greifen (`stacks = state.cue_stacks; if stacks: stacks[0]...`) oder try/except. Teil des Cross-Thread-Themas (s. u.). |
| **WEB-05** | `app.py:53`, `app.py:56` | **`GET /api/status` iteriert `state.cue_stacks`/`state.universes` ohne Lock** → bei gleichzeitiger Mutation (Show-Load) `RuntimeError: dictionary/list changed size during iteration`. | Über Kopien iterieren (`list(state.universes.keys())` kopiert bereits — die `cue_stacks`-Comprehension über eine Snapshot-Kopie führen). |
| **WEB-QA** | ganze Datei | **0 Tests** für einen vollwertigen externen Steuer-Eingang. | Neuer `tests/test_web_app.py` (Flask `test_client`, gemockter `get_state`): Clamping (Fader 0–1, Kanal 0–255), Bereichs-Guards (slot/universe/channel out-of-range = No-op), Payload-Fehlertoleranz (nach WEB-02/03), Routing (GO/Back/Blackout/Fader/clear an die richtigen Ziele), Leerer-CueStack-Guard. |

---

## Querschnitts-Thema: Cross-Thread-Zugriff

`start_server` startet Flask/SocketIO in einem **eigenen Thread** (`sio.run(...)`, `app.py:170`);
der DMX-Renderer läuft mit 44 Hz im Output-Thread, die UI im Qt-Hauptthread. **Alle** Routen/
Handler greifen **direkt** und **ohne Marshalling/Lock** auf den gemeinsamen Zustand zu
(`executors[idx].fader_value=`, `cue_stacks[0].go()`, `set_channel`, `set_blackout`,
`clear_programmer`). Einfache Attribut-/Bytearray-Sets sind durch den GIL grob atomar; die
zusammengesetzten Operationen (`go()`, `back()`, `clear_programmer()`, Status-Iteration) sind es
**nicht** → WEB-04/WEB-05 sind die konkret belegten Ausprägungen. Ein sauberer Fix wäre, die
Web-Kommandos wie MIDI/OSC in den Qt-Thread zu marshallen (Signal/`QMetaObject.invokeMethod`) statt
direkt zu mutieren — größeres Follow-up (als NET-Item notiert).

## Abgeleitete Backlog-Items
NET-01 (P1), NET-02/NET-03/WEB-01 (P2), WEB-02/03/04/05 + WEB-QA (P3) — eingetragen in `BACKLOG.md`.
