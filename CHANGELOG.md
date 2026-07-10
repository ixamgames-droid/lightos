# Changelog

Alle nennenswerten Aenderungen an LightOS werden hier dokumentiert.
Format: [Keep a Changelog](https://keepachangelog.com/de/1.0.0/)

---

## [Unreleased]

### 2026-07-09 — UI-View-/VC-Widget-Smoke vollständig (QA-09 + QA-10)

#### Tests

- **Neue `tests/test_ui_smoke_enumerated.py` (34 Tests):** inventarisiert alle öffentlichen no-arg Views in `src/ui/views` per `pkgutil`/`importlib`/`inspect`; neue oder umbenannte Views lassen den Test rot werden. Jede View wird headless gebaut, alle 19 VC-Widgets durchlaufen ihren Serialisierungs-Roundtrip. Die acht bislang komplett ungetesteten Editoren bauen mit minimalen echten Engine-Objekten und beweisen je ein zentrales Kind-Widget.
- **Reale Browser-Abnahme des Web-Remote:** gegen die laufende lokale Anwendung verbinden, STOP sowie Blackout AN/AUS bedienen; WebSocket-ACK und sichtbares Log wurden bestätigt. Der restliche Desktop-/Hardware-Teil von QA-LIVE bleibt im Verifikationsplan.
### 2026-07-10 — Output-Monitor erreicht alle gültigen Universen (QA-10)

#### Behoben / Tests

- **Universe 17–32 waren im Output-Monitor nicht auswählbar:** `OutputView` begrenzte seinen Universe-Spinbox auf 16, während Patch, Validierung und Output-Konfiguration bis 32 arbeiten. Der Monitor akzeptiert jetzt U1–32. `tests/test_output_view.py` baut die View headless, steuert die Spinbox mit echten Tastaturereignissen bis U32 und prüft die 512 Zellen inklusive DMX-Refresh.
### 2026-07-10 — MIDI-Ansicht räumt ihre Hintergrund-Subscriber auf (QA-10)

#### Behoben / Tests

- **`MidiView` hinterließ Callbacks nach dem Schliessen:** Nachrichten-, Log- und MTC-Subscriber blieben beim jeweiligen Manager registriert und konnten in eine geschlossene Qt-View senden. Die View behält ihre Callbacks jetzt explizit, stoppt ihren Port-Refresh-Timer und meldet alle beim `closeEvent` ab. `MidiManager` kann Log-Subscriber gezielt entfernen und iteriert sie mutationssicher. `tests/test_midi_view.py` prüft den echten Qt-Monitor-/Toggle-Pfad mit isolierten MIDI-/MTC-Fakes sowie den vollständigen Teardown.
### 2026-07-10 — Audio-Editor: Editieren und wiederholtes Popout abgesichert (QA-10)

#### Tests

- `tests/test_audio_editor.py` baut den `AudioEditor` mit einer Minimal-`AudioFunction`, steuert Lautstärke, Loop und Name über echte Qt-Ereignisse und führt drei Popout-/Andock-Zyklen aus. Der Editor-Körper bleibt dabei vollständig bedienbar und wird zuverlässig zurückgedockt.

### 2026-07-09 — Backlog-Arbeitswarteschlange und Roadmap bereinigt

#### Doku / Prozess

- **Der autonome Loop hat jetzt eine kanonische Arbeitswarteschlange:** `BACKLOG.md` trennt ausführbare Arbeit, notwendige Produktentscheidungen und externe Hardware-Blocker von den detaillierten Befundregistern. Veraltete Status wurden korrigiert (u. a. VIZ-PULL/#201, LAS-03, QA-16), die doppelte STAB-11-ID auf STAB-21 aufgelöst und QA-10 auf die tatsächlich noch acht ungetesteten Views präzisiert.
- **Die Roadmap spiegelt umgesetzte Funktionen:** Preset-Browser, Quick-Recording und sACN-Ausgabe sind als erledigt markiert; Hardware-Abnahmen bleiben im Backlog.

### 2026-07-09 — Audio-Input-Startfehler sichtbar (AUDIO-START-WARN)

#### Behoben / Geändert

- **Audio-Input-Tab scheitert nicht mehr still bei fehlendem/ungültigem Loopback-Gerät:** `AudioCapture.start()` setzt jetzt `last_error()` auch bei fehlendem `soundcard`-Backend oder fehlendem Default-Gerät, und `AudioInputView` zeigt diese Meldung direkt im Statuslabel. Stirbt der Capture-Thread erst nach einem zunächst erfolgreichen Start (z. B. Geräte-ID-Mismatch: „no device with id …"), bleibt der Tab nicht mehr stumm auf „Status: gestoppt", sondern zeigt den konkreten Capture-Fehler wie der BPM-Manager. Test: `tests/test_audio_input_view.py`.

### 2026-07-08 — OSC-Blackout & MTC-Frame robuster (OSC-04 + MTC-02, aus AUD-08)

#### Geaendert / Fixes

- **OSC `/lightos/blackout` invertiert nicht mehr bei String-Argumenten (OSC-04):** `val = bool(args[0])` machte aus einem String-Typetag „0"/„off" ein `True` (jeder nicht-leere String ist truthy) → Blackout **AN** statt AUS. Neu: `OscServer._as_on()` interpretiert typ-tolerant — numerische Args über die Schwelle `>= 0.5`, Strings gegen die Aus-Token `{"","0","off","false","no"}`. Getypte int/float von TouchOSC/Lemur (0/1) verhalten sich unverändert korrekt.
- **MTC feuert nur bei vollständigem Quarter-Frame-Satz (MTC-02):** `_handle_quarter_frame` feuerte bedingungslos bei `piece==7` → bei Mid-Stream-Attach oder einem verlorenen Piece wurde ein Frame aus **gemischten** alten+neuen Nibbles zusammengesetzt (kurz falscher Timecode). Neu: eine Bitmaske `_qf_seen` verfolgt die empfangenen Pieces; gefeuert wird nur, wenn alle 8 (`0xFF`) seit dem letzten Feuern kamen — ein unvollständiges Fenster wird verworfen, der nächste komplette 0..7-Satz feuert mit frischem Puffer.
- **Tests:** NEU `tests/test_osc_mtc_robustness.py` (8) — Blackout-Coercion für String-/typed-Args; MTC feuert nicht bei unvollständigem/lückenhaftem Satz, feuert genau einmal bei vollständigem (Sekunden korrekt dekodiert), erholt sich nach einem unvollständigen Fenster. Herkunft: AUD-08 (`docs/OSC_TIMECODE_AUDIT_2026_07_08.md`). MTC-01 (Frame-Wrap, Drop-Frame) + MTC-03 (Torn-Read) bleiben als dokumentierte P3.

### 2026-07-08 — OSC- & Timecode/MTC-Remote-Eingang-Audit (AUD-08)

#### Doku / Audit

- **Verifizierter Audit des OSC- und MTC-Eingangs** (`osc_server.py`, `mtc_reader.py`, beide 0 Tests): NEU [`docs/OSC_TIMECODE_AUDIT_2026_07_08.md`](docs/OSC_TIMECODE_AUDIT_2026_07_08.md). 4-Dimensionen-Workflow, jedes Finding adversarial verifiziert — **22 Agenten, 7 CONFIRMED**.
- **Positiv bestätigt (kein Bug, kein neuer P1/P2):** OSC-Handler robust gekapselt (int/float-Guards, geklemmt); Cross-Thread sauber (alle mutierten Ziele gelockt); MTC-Dekodierung spec-konform; MTC-Lifecycle sauber.
- **Die 2 P2 sind Parität** zu bekannten Web-Items: OSC-01 = **WEB-01** (`/lightos/ch` schreibt am 44-Hz-Renderer vorbei), OSC-02 = **NET-01** (`0.0.0.0:7770` ohne Auth) — beide dort als querschnittliche externe-Eingang-Themen vermerkt (gemeinsamer Fix, Produkt-Entscheidung).
- **Neu nur P3:** OSC-04 (`_handle_blackout` `bool()`-Inversion bei String-Args), MTC-01 (`+2`-Frame ohne Wrap), MTC-02 (Feuern ohne Vollständigkeitsprüfung), MTC-03 (Torn-Read, latent). Reine Doku-Änderung.

### 2026-07-08 — DMX-Eingang: RX-Thread erholt sich nach Netz-Blip (NET-06, aus AUD-06)

#### Geaendert / Fixes

- **Kein dauerhaft stummer DMX-Eingang mehr nach einem transienten Netzwerkfehler:** Starb der RX-`_loop` eines Receivers über einen `break` (transienter `OSError` aus `recvfrom` — Adapter-Reset, VPN-Toggle, Kabel raus/rein — oder ein unerwarteter Fehler), wurde `self._running` **nicht** zurückgesetzt. `is_running()` (das nur das Flag las) log daraufhin dauerhaft `True` → der UI-Auto-Restart-Guard `if not rx.is_running(): rx.start()` feuerte nie und `start()` no-oppte → der Eingang blieb **permanent stumm**, obwohl das Status-Label „Aktiv" zeigte (Erholung nur durch manuelles Ab-/Wieder-Anhaken). Jetzt setzen **beide** `break`-Pfade `self._running = False`, und `is_running()` prüft zusätzlich `self._thread.is_alive()` → nach einem Blip meldet der Receiver ehrlich „nicht laufend" und der UI-Guard startet ihn (inkl. Multicast-Re-Join) neu. Betrifft `artnet_input.py` **und** `sacn_input.py`.
- **Tests:** NEU `tests/test_dmx_input_rx_lifecycle.py` (6) — `is_running()` ist nur mit lebendem Thread True; der `_loop` setzt `_running=False` bei `OSError` und bei unerwartetem Fehler (beide Receiver). Herkunft: AUD-06 (`docs/DMX_INPUT_AUDIT_2026_07_08.md`).

### 2026-07-08 — DMX-Eingang: verlorene Quelle friert Kanäle nicht mehr ein (NET-05, aus AUD-06)

#### Geaendert / Fixes

- **Source-Timeout für Art-Net/sACN-Eingang:** Hörte eine externe Konsole auf zu senden (abgezogen/abgestürzt), blieben ihre zuletzt empfangenen Werte in `input_layer` und der 44-Hz-Renderer mischte sie **für immer** weiter → betroffene Kanäle hingen dauerhaft (bei HTP als Boden, bei REPLACE eingefroren) und ließen sich **nicht per Blackout** herunterziehen (der externe Eingang wird nicht vom Submaster/Blackout skaliert). `apply_input_merge` stempelt jetzt pro `out_univ` den Empfangszeitpunkt (`time.monotonic()`), und `_render_frame` (Schritt 4b-Input) verwirft Quellen, die länger als `INPUT_SOURCE_TIMEOUT_S` (2,5 s, E1.31 Network Data Loss) nichts mehr gesendet haben — der Kanal fällt dann auf Default/0 zurück. `clear_input_merge` räumt den Zeitstempel mit auf. `clear_input_merge` war bereits für genau diesen Zweck dokumentiert, wurde aber nie produktiv aufgerufen.
- **Tests:** `tests/test_input_layer.py` (2 neu) — eine backdatierte Quelle wird verworfen (Kanal fällt auf 0, Universe aus `input_layer` entfernt); eine frische Quelle bleibt. Herkunft: AUD-06 (`docs/DMX_INPUT_AUDIT_2026_07_08.md`).

### 2026-07-08 — DMX-Eingang- & RX-Thread-Audit (AUD-06)

#### Doku / Audit

- **Verifizierter Audit des DMX-Eingangs** (Art-Net/sACN-RX-Threads + Merge): NEU [`docs/DMX_INPUT_AUDIT_2026_07_08.md`](docs/DMX_INPUT_AUDIT_2026_07_08.md). 5-Dimensionen-Workflow, jedes Finding adversarial verifiziert — **15 Agenten, 5 CONFIRMED**.
- **Positiv bestätigt (kein Bug):** beide RX-Parser robust gegen manipulierte/zu kurze/lange Pakete (kein Crash/Thread-Tod); Lock-Disziplin sauber (RX liest GIL-atomar); Multicast-Join korrekt (die UI joint immer das konfigurierte In-Universe).
- **Echte Defekte** als Backlog-Items abgeleitet: **NET-05** (P1, kein Source-Timeout → verlorene externe Quelle friert Kanäle dauerhaft ein; Blackout greift dort nicht — sicherheitsrelevant), **NET-06** (P2, RX-Thread-Tod ohne `_running`-Reset → Eingang bleibt nach Netz-Blip stumm, `is_running()` lügt), **NET-07/08** (P3, Merge in nicht-konfiguriertes Universe / alte Merge-Config bleibt beim Umkonfigurieren). Reine Doku-Änderung.

### 2026-07-08 — Output-Typ-Wechsel & „Disabled" schließen den Alt-Adapter (OUT-05, aus AUD-03)

#### Geaendert / Fixes

- **Kein Phantom-/Doppel-Output mehr nach einem Output-Typ-Wechsel, „Disabled" schaltet ein Universe wirklich stumm:** `add_enttec/add_artnet/add_sacn` schrieben nur in ihre **eigene** Adapter-Registry; es gab **kein** Remove/Disable und `apply_output_config` keinen „Disabled"-Zweig. Wer ein Universe von ArtNet auf sACN umstellte, dessen alter ArtNet-Sender blieb offen → `_send_all` sendete dasselbe DMX über **beide** Adapter (und flutete das alte Ziel weiter); ein als „Disabled" markiertes Universe gab **weiter Licht** aus (nur per App-Neustart stoppbar); das Alt-Handle (Socket/Serial) wurde nie geschlossen (Leak). Neu: `OutputManager.remove_output(universe)` popt alle drei Registries unter `_io_lock` und schließt die Geräte (Muster wie `_swap_device`); `apply_output_config` ruft es **vor** dem Einrichten des neuen Typs → pro Universe genau ein (oder bei „Disabled" kein) aktiver Adapter.
- **Tests:** `tests/test_output_manager.py` (2 neu) — `remove_output` popt+schließt alle Adapter eines Universums (andere unberührt); Typ-Wechsel (ArtNet→sACN via remove+add) lässt genau einen Adapter zurück. Herkunft: AUD-03 (`docs/DMX_OUTPUT_AUDIT_2026_07_08.md`).

### 2026-07-08 — DMX-Output-/Netzwerk-Sender-Audit (AUD-03)

#### Doku / Audit

- **Verifizierter Audit des DMX-Output-Pfads** (ArtNet/sACN/Serial/OutputManager): NEU [`docs/DMX_OUTPUT_AUDIT_2026_07_08.md`](docs/DMX_OUTPUT_AUDIT_2026_07_08.md). 5-Dimensionen-Workflow, jedes Finding adversarial verifiziert — **19 Agenten, 6 CONFIRMED + 1 PLAUSIBLE**.
- **Positiv bestätigt (kein Bug):** Bytes beider Protokolle spec-konform; der 44-Hz-Output-Loop ist **doppelt** gegen Sende-Fehler abgesichert (kein Loop-Tod — Hypothese adversarial widerlegt); Lock-Disziplin robust; Universe→Wire-Abbildung korrekt.
- **Echte Defekte** als Backlog-Items abgeleitet: **OUT-05** (P2, kein Remove/Disable pro Universe → Typ-Wechsel/„Disabled" sendet weiter + Handle-Leak), **NET-04** (P3, kein explizites Egress-Interface/Broadcast-Default), **SERIAL-01/02** (P3, Port-Diagnose/Reconnect), **OUT-06** (P3, sACN-CID/Stream-Termination). Reine Doku-Änderung.

### 2026-07-08 — Show-Laden: Farbpaletten bleeden nicht mehr aus der Vorshow (STAB-19a, aus AUD-04)

#### Geaendert / Fixes

- **Paletten einer palettes-losen Show überschreiben nicht mehr still die vorherigen:** `load_show` lud den `palettes`-Block nur, wenn der Key vorhanden war (`if "palettes" in data`) — **ohne** `else`-Zweig. Beim Laden einer Show ohne `palettes`-Key blieben so die Farbpaletten der **vorigen** Show hängen (Bleed; `palettes` war der einzige Manager mit diesem Muster). Jetzt wird bei fehlendem Key `pm.from_dict({})` aufgerufen (wie in `reset_show`).
- **Tests:** `tests/test_show_file.py` (2 neu) — Show ohne palettes-Key → Paletten geleert; mit Key → genau diese geladen. Herkunft: AUD-04 (`docs/SHOW_FILE_AUDIT_2026_07_08.md`). Der reset-first/Rollback-Aspekt (STAB-19b) bleibt als P3 mit geringem Restrisiko dokumentiert offen (`load_show` setzt bereits alle State-Felder inline zurück).

### 2026-07-08 — Show-Laden: robuster gegen alte/korrupte `.lshow` (STAB-20, aus AUD-04)

#### Geaendert / Fixes

- **Non-Object-JSON liefert eine saubere Fehlermeldung** statt eines Absturzes: ein gültiges JSON, das kein Objekt ist (Liste/Zahl/String/`null` — korrupte oder fremde Datei), führte beim ersten `data.get(...)` zu einem ungefangenen `AttributeError`. `load_show` prüft jetzt `isinstance(data, dict)` und gibt sonst `(False, "…kein Objekt")` zurück.
- **Versions-Gate:** Ist die Datei-`version` **neuer** als das unterstützte Format (`SHOW_VERSION`), wird jetzt gewarnt und best-effort weitergeladen (statt die Datei still als aktuelles Format zu deuten). Robuste Tupel-Vergleich (`"1.10" > "1.2"`).
- **Legacy-EFX/RGB-Migration pro Eintrag isoliert:** Die einmalige Migration alter `efx`/`rgb_matrix`-Blöcke in Funktionen brach beim **ersten** kaputten Eintrag ab und verlor **alle folgenden**. Jetzt ist jeder Eintrag in ein eigenes `try/except` gekapselt — nur der kaputte fällt weg.
- **Tests:** `tests/test_show_file.py` (3 neu) — Non-Object-JSON → saubere Fehlermeldung; zu neue Version → lädt best-effort; kaputter Legacy-EFX-Eintrag → der gute danach wird weiter migriert. Herkunft: AUD-04 (`docs/SHOW_FILE_AUDIT_2026_07_08.md`).

### 2026-07-08 — Show-Laden: ein kaputter Wert löscht nicht mehr ganze Blöcke (STAB-18, aus AUD-04)

#### Geaendert / Fixes

- **Ein einzelner falsch-typisierter Wert verwirft nicht mehr den GESAMTEN programmer/base_levels-Block:** Beim Laden wandelten `{str(a): int(v) for …}`-Comprehensions die Werte um — ein einziger `None`/Listen-/nicht-numerischer Wert (z. B. aus hand-editierter oder alter `.lshow`) warf und der äußere `except` setzte `state.programmer = {}` bzw. `state.base_levels = {}` → **alle** Fixtures verloren (still). Jetzt ist `int(v)` **pro Wert** gekapselt (analog zur schon vorhandenen fid-/attrs-Isolation): nur der kaputte Wert fällt weg, der Rest bleibt.
- **Ein Render-Plan-Fehler verwirft nicht mehr die geladenen base_levels:** `state._rebuild_render_plan()` stand **innerhalb** des `base_levels`-`try` (nach der Zuweisung) → ein aus **unabhängigem** Grund werfender Rebuild landete im `except` und löschte die eben geladenen `base_levels` + kippte `implicit_brightness` auf True. Der Rebuild ist jetzt **aus dem `try` gezogen** (eigener, separat behandelter Aufruf).
- **Tests:** `tests/test_show_file.py` (3 neu) — kaputter Programmer-/base_levels-Wert lässt die guten Werte/Fixtures stehen; ein werfender `_rebuild_render_plan` lässt `base_levels`/`implicit_brightness` unangetastet. Herkunft: AUD-04 (`docs/SHOW_FILE_AUDIT_2026_07_08.md`).

### 2026-07-08 — Show-Speichern: atomar + kein stiller Funktions-Verlust (STAB-16/17, aus AUD-04)

#### Geaendert / Fixes

- **Speichern zerstört bei einem Fehler nicht mehr die vorhandene Show (STAB-16):** `save_show` öffnete bisher die Ziel-`.lshow` direkt (`zipfile.ZipFile(path,"w")` — truncatet sofort auf 0 Byte) und serialisierte `json.dumps` **erst danach** im offenen Handle. Ein Absturz, ein voller Datenträger oder ein Serialisierungsfehler hinterließ eine **korrupte** Datei und die vorherige Show war weg. Jetzt wird **zuerst serialisiert**, dann in eine **Temp-Datei im selben Verzeichnis** geschrieben und per **`os.replace()` atomar** über den Zielpfad gezogen; bei jedem Fehler bleibt die vorhandene Datei unangetastet und die Temp-Datei wird entfernt. `programmer`/`base_levels` werden zudem vor der Serialisierung unter `_prog_lock` defensiv gesnapshottet (kein „dict changed size" durch nebenläufiges Live-Editing).
- **Ein kaputter Effekt löscht nicht mehr still alle Funktionen (STAB-17):** Der `functions`-Block (in dem seit dem Programmer-Umbau auch **alle EFX-/RGB-Matrix-Instanzen** leben) wurde bei einem `to_dict()`-Fehler still auf `{"functions": []}` gesetzt und leer gespeichert → Totalverlust beim nächsten Laden. Der Fehler wird jetzt **nicht mehr geschluckt**: die Serialisierung darf abbrechen (dank STAB-16 bleibt die alte Datei dabei erhalten), statt eine leere Show zu schreiben.
- **Tests:** `tests/test_show_file.py` — Serialisierungsfehler lässt die vorhandene `.lshow` byte-identisch + ohne Temp-Leiche; normaler Save hinterlässt keine `.tmp`; `functions`-Block wird nicht still geleert. Herkunft: AUD-04 (`docs/SHOW_FILE_AUDIT_2026_07_08.md`).

### 2026-07-08 — Show-Datei-Persistenz-Audit `.lshow` (AUD-04)

#### Doku / Audit

- **Verifizierter Audit der `.lshow`-Persistenz** (`save_show`/`load_show`/`reset_show`, Datenverlust-Fokus): NEU [`docs/SHOW_FILE_AUDIT_2026_07_08.md`](docs/SHOW_FILE_AUDIT_2026_07_08.md). 5-Dimensionen-Workflow (Round-Trip · `_lenient`-Ganzblock-Verlust · Reset/Stale-State · Schema/Migration · Save-Integrität), jedes Finding adversarial verifiziert — **33 Agenten, 12 CONFIRMED, 2 zurückgewiesen → 9 distinkte Defekte**.
- **Positiv bestätigt (kein Bug):** der **Round-Trip ist vollständig** (alle 29 Keys + Feld-Ebenen symmetrisch, kein stiller Verlust), `reset_show` leert sauber; das „leer speichern bei to_dict-Fehler"-Muster ist bei `executors`/`tempo_buses` toter Defensiv-Code (kein erreichbarer Wurf).
- **Echte Defekte** als Backlog-Items abgeleitet: **STAB-16** (P1, nicht-atomarer Save korrumpiert die vorige Show), **STAB-17** (P1, `functions`-Block leer gespeichert bei `to_dict()`-Fehler → Totalverlust inkl. EFX/Matrix), **STAB-18** (P2, ein kaputter Wert löscht ganzen programmer/base_levels-Block), **STAB-19** (P2, `load_show` nicht reset-first/atomar + palettes-Bleed), **STAB-20** (P3, Robustheit gegen alt/korrupt). Reine Doku-Änderung.

### 2026-07-08 — Render-Thread: Engine-Extra-Roh-Kanal beim Repatch freigeben (STAB-14, aus AUD-02)

#### Geaendert / Fixes

- **Kein Roh-Kanal-Zombie mehr nach Patch-Change:** Schreibt eine `ScriptFunction` per `setdmx` einen **nicht gepatchten** Roh-Kanal, committet der Renderer ihn und merkt ihn in `_engine_extra_prev`, um ihn später (wenn das Skript stoppt) wieder auf 0 freizugeben. Ein Patch-Rebuild (`_rebuild_render_plan`, `app_state.py`) setzte dieses Tracking bisher **hart auf `{}`** — ohne die Live-Werte zu nullen. Stoppte das Skript danach, blieb `prev` leer, die `prev-cur`-Freigabe feuerte nie → der Roh-Kanal blieb **dauerhaft an** (bei Strobe/Shutter/Beam sicht- und sicherheitsrelevant). **Fix:** neuer Helfer `_release_engine_extra()` gibt die gemerkten Roh-Adressen im Live-Universe aktiv auf 0 frei, bevor das Tracking geleert wird (`list()`-Snapshot gegen den Render-Thread; `set_channel` per Universe-Lock thread-safe). Wird die Adresse jetzt gepatcht/weiter beschrieben, setzt der nächste Frame sie neu — höchstens 1 Frame Dip.
- **Tests:** `tests/test_render_frame.py::test_engine_extra_released_on_repatch` — Roh-Kanal committen → Repatch → Skript stoppt → Adresse wird auf 0 freigegeben (und bleibt es). Herkunft: AUD-02 (`docs/RENDER_AUDIT_2026_07_08.md`).


#### Geaendert / Fixes

- **Kein Dropped-Frame-Stutter mehr durch Feature-Dimmer:** Der Per-Frame-Renderer (Schritt 4b², `app_state.py`) iterierte `feature_dimmers` als **einzige** Ebene über die live `.values()`-View (ohne Lock-Snapshot, anders als Programmer/Simple-Desk/Input). Änderte ein UI-Thread währenddessen die dict-**Größe** (Slider-Slot anlegen/entfernen beim Schwellen-Crossing, `clear_feature_dimmers` beim Show-Load), warf CPython `RuntimeError: dictionary changed size during iteration` → der Block war nicht gekapselt, die Exception verwarf den ganzen Frame (Commit entfiel, alle Universen behielten den Vorframe) → sichtbarer Micro-Stutter. **Fix:** neuer `_fd_lock`; `set_feature_dimmer`/`clear_feature_dimmers` schreiben darunter, der Renderer zieht davor **einen** Snapshot (`list(feature_dimmers.values())`) — die Slot-Objekte sind unveränderlich, der Snapshot also stabil.
- **Tests:** `tests/test_feature_dimmer.py` — neuer `FeatureDimmerConcurrencyTest` (Writer-Thread oszilliert die Slot-Größe, 400 Render-Frames laufen fehlerfrei durch; + Positiv-Test, dass der Snapshot weiterhin korrekt dimmt). Herkunft: AUD-02 (`docs/RENDER_AUDIT_2026_07_08.md`).

### 2026-07-08 — Render-Pfad-Audit `_render_frame` (AUD-02)

#### Doku / Audit

- **Verifizierter Audit des heißesten Threads** (Per-Frame-Renderer, historische AV-Quelle STAB-07): NEU [`docs/RENDER_AUDIT_2026_07_08.md`](docs/RENDER_AUDIT_2026_07_08.md). 6-Dimensionen-Workflow (Concurrency/Lock · Exception-Isolation · Clamp/Overflow · Merge-Reihenfolge · Commit/Freigabe · Coverage), jedes Finding adversarial gegen den echten Code verifiziert — **36 Agenten, 6 CONFIRMED, 2 PLAUSIBLE, 7 zurückgewiesen**.
- **Positiv bestätigt (kein Bug):** Clamp lückenlos (`set_channel` zentral), kein Thread-Death (Callback-Isolation), Grand-Master/WP-6-Merge **by design** (2× adversarial widerlegt), und die Test-Coverage ist **breit** (≥8 dedizierte Suiten — die Backlog-Annahme „nur test_render_frame.py" war veraltet; fünf gemeldete „Lücken" waren bereits abgedeckt).
- **Echte Defekte** als Backlog-Items abgeleitet: **STAB-13** (P2, `feature_dimmers` ungelockt iteriert → Dropped-Frame), **STAB-14** (P2, Engine-Extra-Zombie beim Repatch), **STAB-15** (P3, nicht-atomarer Plan-Swap), **QA-25** (P3, kleine Coverage-Ergänzung). Reine Doku-Änderung.

### 2026-07-08 — Programmer-Leerzustand: eine Meldung mit Handlungsanweisung (UI-20)

#### Geaendert / Fixes

- **Kein doppeltes „Kein Gerät ausgewählt" mehr:** Im leeren Programmer stand derselbe Text 2× übereinander (Kopf-Label + je aktivem Attribut-Tab ein gleichlautender Platzhalter), ohne Hinweis, was zu tun ist. Der Kopf ist jetzt eine Status-/Handlungszeile („Kein Gerät ausgewählt — links ein Gerät oder eine Gruppe wählen"), der Tab-Platzhalter ein bewusst anders formulierter, beschreibender Hinweis („Attribute erscheinen hier, sobald ein Gerät gewählt ist."). Beide Texte liegen als Konstanten (`_EMPTY_SELECTION_MSG`/`_EMPTY_TAB_HINT`) vor, damit Init und Rebuild synchron bleiben.
- **Tests:** NEU `tests/test_programmer_empty_state.py` (2 Tests) — Kopf trägt die Handlungsanweisung, kein Tab-Platzhalter wiederholt den Kopf-Text wortgleich.
- Datei: `src/ui/views/programmer_view.py`. Herkunft: BACKLOG UI-20.

### 2026-07-08 — Web-Remote: robuster gegen fehlerhafte Requests + Tests (WEB-02/03/04/05, aus AUD-05)

#### Geaendert / Fixes

- **Kaputte Remote-Requests werfen keinen HTTP 500 / Handler-Crash mehr:** Die Web-Remote-Endpunkte konvertierten `level`/`value` aus dem JSON-Body ungeschützt per `float()`/`int()` — ein nicht-numerischer (oder `Infinity`/`NaN`) Wert erzeugte eine ungefangene Exception (WEB-02). Neuer Helfer `_num(...)` fängt das ab und nutzt den Default; verdrahtet in `api_fader`, `api_channel`, `on_fader`. Die SocketIO-Handler `on_fader`/`on_blackout` crashten zudem bei einem Emit **ohne** Payload (`data=None`) — jetzt `data=None`-Default + `data = data or {}` (WEB-03).
- **Nebenläufigkeit gehärtet:** `/api/go`, `/api/back` und die SocketIO-Pendants greifen die Cue-Stack-Liste über eine lokale Referenz statt `if …: …[0]` (kein TOCTOU-`IndexError`, wenn eine Show währenddessen geladen wird; WEB-04). `/api/status` iteriert die Cue-Stacks über eine Snapshot-Kopie (kein „changed size during iteration"; WEB-05).
- **Tests:** NEU `tests/test_web_app.py` (17 Tests) — der bislang komplett ungetestete externe Steuer-Eingang ist jetzt gegen Clamping, Bereichs-Guards, Payload-Fehlertoleranz und Routing abgesichert.
- Datei: `src/web/app.py`. Herkunft: AUD-05-Audit (`docs/WEB_REMOTE_AUDIT_2026_07_08.md`); die Security-Befunde NET-01/02/03 + WEB-01 bleiben als offene Items (brauchen Produkt-Entscheidungen).

### 2026-07-08 — Ausgabe: Art-Net/sACN „Übernehmen" zerschießt nicht mehr andere Universen (OUT-04)

#### Geaendert / Fixes

- **„Übernehmen" wirkt jetzt nur auf das gewählte Universum:** In der Ausgabe-Konfiguration überschrieben die Art-Net- und sACN-„Übernehmen"-Buttons bisher **alle** Universen — sie liefen in einer Schleife über `state.universes` und setzten für jedes den Adapter (live UND in `universes.json`). Wer z. B. einen Enttec auf Universe 1 und dann Art-Net auf Universe 2 einrichten wollte, dessen Enttec-Zuweisung (und jede andere) wurde beim Art-Net-„Übernehmen" mit überschrieben. Neu: Art-Net- und sACN-Tab haben je ein **„Universe:"-Feld** (wie der Enttec-Tab); `_apply_artnet`/`_apply_sacn` belegen nur dieses eine Universum (legen es bei Bedarf an), und `_persist_output` aktualisiert nur dessen Zeile in `universes.json` — bestehende Zuweisungen anderer Universen bleiben erhalten.
- Datei: `src/ui/widgets/output_config.py`; Test NEU `tests/test_output_config.py` (4 Tests: Art-Net/sACN nur ein Universum, deaktiviert = No-op, fehlendes Zieluniversum wird angelegt).

### 2026-07-08 — Tests: Multi-Universe-Output abgesichert (QA-07 + QA-08)

#### Tests / QA

- **Der zentrale Multi-Universe-Send-Pfad ist gegen Regression gesichert (QA-07):** neuer `tests/test_output_manager.py::TestOutputManagerMixedSend` patcht einen Fake-Enttec auf Universe 1 und einen Fake-Art-Net-Sender auf Universe 2, setzt unterschiedliche Kanalwerte und prüft nach einem `_send_all()`-Durchlauf, dass jeder Adapter **genau seine** Universe-Daten bekommt (keiner die fremden) und der Art-Net-Sender die erwartete externe Universe-Nummer (`univ_num - 1`) sieht. Nagelt das Routing in `output_manager._send_all` (Enttec/Art-Net/sACN je Universum) fest.
- **Die Start-Rekonstruktion aus `universes.json` ist abgesichert (QA-08):** `tests/test_output_manager.py::TestApplyOutputConfigRoundtrip` schreibt eine temporäre `universes.json` (Enttec/Art-Net/sACN auf U1/U2/U3) und prüft, dass `AppState.apply_output_config` jeden Adapter im **richtigen** Registry-Dict für sein Universum einrichtet (keine Kreuz-Einträge); ein zweiter Test belegt, dass ein Adapterfehler (Enttec ohne Port) den Loop **nicht abbricht** (die folgenden Adapter werden weiter eingerichtet). Deckt die zuvor ungetestete „Output kommt nach Neustart nicht"-Klasse ab.
- Kein Produktcode geändert (reine Regressions-Wächter).

### 2026-07-08 — Tests: Regressions-Wächter für VC-Widget-Drag (VC-WIDGET-DRAG)

#### Tests / QA

- **Kern-Drag-Interaktion der Virtual Console abgesichert:** Zum live gemeldeten (aber headless nicht reproduzierbaren) Effekt „VC-Widgets lassen sich im Bearbeiten-Modus nicht ziehen" nagelt ein neuer Guard-Test `tests/test_vc_widget_drag.py` das korrekte Verhalten fest — Fader, Button und SpeedDial (jeweils selbst-gezeichnet, im Edit-Modus an die Basis-`VCWidget`-Drag-Logik delegierend) verschieben sich per simuliertem Press+Move, **auch als Kind eines VCFrame**. Kein Produktcode geändert; der ursprünglich gemeldete Live-Effekt bleibt offen für eine Live-/Computer-Use-Repro (vermutlich szenario-spezifische Event-Zustellung im echten Fenster).

### 2026-07-08 — 3D-Panel: Zahlenfelder akzeptieren Punkt und Komma (VIZ-FIX-DECIMAL)

#### Geaendert / Fixes

- **Kein Dezimal-Datenverlust mehr in den 3D-Panels:** Die Zahlenfelder im 3D-Visualizer (Fixture „Position & Ausrichtung", Bühnen-Element-Größe/-Position, Raster) waren Standard-`QDoubleSpinBox` und damit an das System-Locale gebunden. Auf deutschem Locale erwartet die Spinbox das Komma als Dezimaltrenner; tippte man „5.7" mit Punkt, war die Eingabe ungültig und wurde verworfen bzw. geklemmt (stiller Verlust der Nachkommastellen). Neu: ein wiederverwendbares `LocaleTolerantDoubleSpinBox` (`src/ui/widgets/decimal_spinbox.py`) läuft intern auf C-Locale und normalisiert Komma→Punkt beim Validieren und Auslesen — beide Schreibweisen (`5.7` und `5,7`) werden korrekt übernommen. Alle 14 betroffenen Felder in `visualizer_window.py` sind umgestellt.
- Nebeneffekt: behebt den Dezimal-Aspekt der Stage-Größenfelder aus **VIZ-STAGE-PANEL** (Teilpunkt a); dessen übrige Punkte (ENTER-Commit, Panel-Sync, Resize-Toggle) bleiben offen.
- Dateien: `src/ui/widgets/decimal_spinbox.py` (NEU), `src/ui/visualizer/visualizer_window.py`; Test NEU `tests/test_decimal_spinbox.py` (5 Tests, deutsches Locale erzwungen, inkl. Regressionsbeleg gegen die Standard-Spinbox).

### 2026-07-08 — Live-View: Gerätezähler stimmt sofort beim Öffnen (UI-21)

#### Geaendert / Fixes

- **Kopfzeilen-Gerätezähler wird beim Bau initial gefüllt:** Der Zähler „N Geräte im Patch" oben in der Bühnen-/Live-Ansicht wurde ausschließlich über einen 500 ms-Timer (`_info_timer`) aktualisiert — `LiveView.__init__` rief `_refresh_info()` nie selbst. Öffnete man die Ansicht mit einer bereits gepatchten Show, zeigte die Kopfzeile bis zum ersten Timer-Tick „0 Geräte im Patch". Fix: `__init__` ruft `_refresh_info()` am Ende einmal aktiv auf (Initial-Pull) — der Zähler (und das Auswahl-Label) stimmen ab dem ersten Frame. Gleiche Bug-Klasse wie UI-05/UI-09 (fehlender Initial-Pull nach `__init__`).
- Datei: `src/ui/views/live_view.py`; Test NEU `tests/test_live_view_fixes.py::test_info_label_initial_pull`.

### 2026-07-08 — ShowBuilder: Skript-gepatchte Fixtures erben den fixture_type des Profils (VIZ-BUILDER-FIXTYPE)

#### Geaendert / Fixes

- **3D-Visualizer färbt/bewegt Skript-gebaute Shows jetzt korrekt:** `ShowBuilder.patch()` ließ `fixture_type` auf dem Model-Default `'other'` — der 3D-Visualizer (`registry.js`) fällt für `'other'` auf den PAR-Builder zurück und mappt DMX **nicht** auf Farbe/Pan/Tilt, sodass Effekte in per-Skript gebauten Shows die Geräte weder färbten noch bewegten. Fix: `patch()` liest über den neuen Helfer `_lookup_profile()` neben der Profil-ID auch den `fixture_type` des `FixtureProfile` und setzt ihn direkt beim Anlegen der `PatchedFixture`. Das spiegelt die bereits existierende `sync.py`-Auto-Fix-Semantik (generischer Typ → Profil-Typ übernehmen), nur schon beim Patchen statt erst bei einer Validierungs-/Sync-Runde.
- **Aufräumen:** Der dadurch redundante manuelle Nachzieh-Block in `tools/build_grosses_rig.py` (loopte nach `patch()` über alle Fixtures und setzte den Typ per `update_fixture`) wurde entfernt.
- Dateien: `src/core/show/showbuilder/builder.py`, `tools/build_grosses_rig.py`; Test NEU `tests/test_showbuilder.py::test_patch_inherits_fixture_type_from_profile` (querabgesichert gegen den echten Profil-Typ aus der Bibliothek, unabhängig von der Implementierung).

### 2026-07-08 — VC-Fader „Playback": dediziertes playback_slot-Feld statt function_id-Zweckentfremdung (DQ-2)

#### Geaendert / Fixes

- **Sauberere Datenhaltung für Playback-Fader:** Ein VC-Fader im Modus „Playback (Executor)" speicherte den Ziel-Executor-Slot bisher in `function_id` — demselben Feld, das alle anderen Modi als echte Funktions-ID nutzen (Zweckentfremdung). Jetzt gibt es ein dediziertes `playback_slot`: eine eigene Spinbox „Playback Executor-Slot" im Eigenschaften-Dialog (nur im Playback-Modus sichtbar, „nicht gesetzt" = leer) mit eigenem Persistenz-Schlüssel. Der `_apply()`-Pfad routet Playback jetzt über `playback_slot` — inkl. Guard `0 <= slot < len(executors)` gegen negative/zu große Slots (vorher nur obere Grenze).
- **Rückwärtskompatibel:** Alt-Shows, die den Slot noch in `function_id` (im Playback-Modus) hielten, migrieren beim Laden automatisch nach `playback_slot`, falls der neue Schlüssel fehlt. Nicht-Playback-Fader bleiben unberührt (keine Slot-Migration); ein explizit gesetztes `playback_slot` gewinnt immer.
- Datei: `src/ui/virtualconsole/vc_slider.py`; Test NEU `tests/test_vc_slider_playback_slot.py` (7 Tests: Roundtrip, Migration, Nicht-Playback-unberührt, explizit-gewinnt, Apply-Ziel korrekt, None-/Out-of-Range-Slot safe).
- _Hinweis: löst die geparkte Design-Entscheidung **DQ-2** zugunsten der sauberen Trennung auf (vorheriger Default war „nur dokumentieren"); trivial revertierbar._

### 2026-07-07 — Patch → Fixture-Gruppen (Grid-Editor): Auswahl bleibt stabil, Drop rastet ein (PATCH-GRP-01)

#### Geaendert / Fixes

- **Gewählte Gruppe springt nicht mehr zurück:** `_reload_group_list` setzte die aktive Gruppe bei jedem Neuaufbau hart auf die alphabetisch **erste** (`groups[0]`). Da jedes „Speichern" über `GROUP_CHANGED` genau dort landet und `+ Neu` ebenfalls neu lud, wechselte die Auswahl unbemerkt (z. B. von „Spiders" zurück auf „MovingHeads") — folgende Drags/Speichern trafen dann die **falsche** Gruppe und überschrieben sie. Fix: die gewählte Gruppe wird per **ID** erhalten (`select_gid`), `+ Neu` selektiert gezielt die **frisch angelegte** Gruppe. Damit bleibt die Auswahl über „+ Neu"/Drag/„Speichern" hinweg stabil.
- **Drag-Drop aufs Raster rastet ein statt still zu überschreiben:** ein externer Drop landet jetzt in einer **freien** Zelle — die Zielzelle unter dem Cursor, oder bei Belegung die per Distanz **nächste freie** (`place_fixture`/`_nearest_free_cell`), statt die vorhandene Belegung lautlos zu ersetzen. Randnahe Drops werden auf die Randzelle **geklemmt** (verpuffen nicht mehr). Ein grünes Live-**Ziel-Highlight** (`resolve_drop_cell`, identisch für Vorschau und echten Drop) zeigt beim Ziehen exakt, wohin es einrastet. Ein einzelner fehlender PAR lässt sich so ohne Überschreiben nachtragen.
- **Neuer Shortcut „Alle → Raster":** übernimmt alle gepatchten Fixtures in Patch-Reihenfolge ins Raster (freie Zellen zuerst, Reihen wachsen bei Bedarf; bereits platzierte bleiben) — „alle auswählen → in Gruppe übernehmen" mit einem Klick (danach „Speichern").
- Datei: `src/ui/views/fixture_group_view.py`; Test NEU `tests/test_fixture_group_grid_ux.py` (16 Tests: Zielfindung/Nearest-Free/Clamp/Full-Grid, Auswahl-Stabilität inkl. End-to-End-Save, „Alle → Raster").

### 2026-07-07 — Tests: Autosave-Recovery-Dialog blockte headless nicht mehr (QA-23)

#### Geaendert / Fixes

- **Grüne Test-Baseline wiederhergestellt:** Lag auf dem Rechner eine `%APPDATA%/LightOS/auto_save.lshow` neuer als alle zuletzt geöffneten Shows, öffnete der Wiederherstellungs-Check beim Start des Hauptfensters ein modales Dialogfeld — headless (offscreen) beantwortet das niemand, sodass die zwei Tests, die das Hauptfenster bauen, in den Timeout liefen (zustandsabhängiger Bruch, unabhängig vom eigentlichen Testinhalt). Fix: `main_window._recovery_prompt_suppressed()` (Env `LIGHTOS_NO_RECOVERY_PROMPT`, von `conftest.py` gesetzt, oder `QT_QPA_PLATFORM=offscreen`) unterdrückt den Prompt in Tests/Tools **vor jedem Dateizugriff** und plant den Start-Timer gar nicht erst. In der echten App ist beides nie aktiv → die Absturz-Wiederherstellung funktioniert unverändert. Neuer Regressionstest `tests/test_autosave_recovery_headless.py` nagelt beides fest (headless fragt nie; Live-Logik fragt genau einmal und stellt bei „Ja" wieder her); die echte Autosave-Datei des Nutzers wird von den Tests nie angefasst.
- Dateien: `src/ui/main_window.py`, `tests/conftest.py`; Test NEU `tests/test_autosave_recovery_headless.py`.

### 2026-07-07 — 3D-Visualizer: On-Demand-Rendering (VIZ-13 3c-2 — Phase 3 damit komplett)

#### Geaendert / Fixes

- **Der 3D-Visualizer rendert nur noch bei Änderung** statt bedingungslos ~60×/s: neues Modul `scene_src/scene/render_loop.js` mit `requestRender()`-Dirty-Flag und `hasLiveAnimation()`-Proben; die rAF-Kette läuft weiter (Absturz-Selbstheilung aus VIZ-10 bleibt), aber `renderer.render()` feuert nur bei Dirty oder aktiver Dauer-Animation (Stage-Selektions-Puls, FPS-Overlay). Bei statischer Szene fällt die Render-Last damit auf ~0 — passend zur Python-Seite, die seit VIZ-12 nur noch geänderte Fixtures pusht.
- **Alle Änderungsquellen verdrahtet** (an Wurzel-Flaschenhälsen: `updateCamera`/`resizeOrtho`, `updateOutlines`, `applyBrightness`, dmxBatch-Handler, Stage-CRUD/Resize, View-Mode, Settings, Drag-Zweige, Docking-Highlight, Resize/PixelRatio) inkl. Setter-Sicherheitsnetz; Verdrahtungs-Karte + dokumentierte fragile Deckungspfade (D1–D3) als Kommentarblock in `render_loop.js`.
- **Beweis-Test** `tests/test_viz13c2_ondemand.py` (11 Tests, echte Page offscreen): Idle rendert nicht, DMX/Kamera/Selektion/Brightness/Settings/Edit-Mode/Stage-Update/Transform/2D-Pan-Drag triggern sofort, Selektions-Puls hält den Loop live, `requestRender` koalesziert. 5 Trigger-Tests stammen aus der Parallel-Session „3D Visualizer placement/movement", die den Zwischenstand-Bug (3D-Editing kurzzeitig eingefroren, Schritt 2 vor Schritt 3) unabhängig diagnostiziert und den Fix verifiziert hat.
- Dateien (18, +714/−47): NEU `scene_src/scene/render_loop.js`; `app.js`, `bridge/bridge.js`, `state.js`, `camera/cameras.js`+`presets.js`, `fixtures/fixtures.js`, `interaction/pointer.js`+`tools.js`+`touch.js`+`gizmo.js`, `scene/renderer.js`+`lights.js`+`model_loader.js`, `stage/stage_objects.js`+`view_mode.js`+`docking.js`; Tests NEU `tests/test_viz13c2_ondemand.py`.

### 2026-07-06 — 3D-Visualizer: DMX-Update-Pfad in die FixtureType-Registry zerlegt (VIZ-13 3c Registry Teil 2)

#### Geaendert / Fixes

- **`updateFixture`-Monolith aufgelöst (reiner Refactor, verhaltens-identisch):** der ~190-Zeilen-DMX-Update-Pfad in `scene_src/fixtures/fixtures.js` ist in **pro-Typ-`updateDmx`-Handler der FixtureType-Registry** zerlegt — `updateSpiderDmx`/`updateParBarDmx`/`updateMoverBarDmx`/`updateMovingHeadDmx` (auch Scanner)/`updateGenericDmx` plus geteilte Helfer (`applyGenericColor`/`applyPanTilt`/`applyFloorAim`/`syncIconPos`) in `builders.js`. Alle 12 Registry-Einträge tragen jetzt `build` **und** `updateDmx`; unbekannte Typen fallen wie bisher auf den PAR-Pfad zurück. Die Fassade `updateFixture(fid, r, g, b, …)` und beide Aufrufer (dmxBatch-Handler, `addFixture`) bleiben unverändert.
- **Verhaltensgleichheit festgenagelt:** neuer Golden-Parity-Test `tests/test_viz13c_updatedmx_registry.py` (echte Page, offscreen QWebEngine) — 14-Fixture-Rig über alle Typen inkl. Multihead, Pixel-Bar und unbekanntem Fallback-Typ; Beam/Spot/FloorSpot/Lens/Lamp/Laser-Linien, Pan/Tilt-Rotationen, `_lastPanRad` und Icon-Färbung werden gegen die **vor dem Umbau eingefrorenen** Referenzwerte (`tests/test_viz13c_updatedmx_golden.json`) verglichen; gelöschte Golden-Datei friert nie still neu ein (Pflicht-Fail).
- Vorarbeit für 3c-2 (On-Demand-Render) und die restlichen Registry-Felder (`dispose`/`icon`); Design laut `docs/VIZ3D_OVERHAUL_PLAN.md` §e.
- Dateien: `scene_src/fixtures/builders.js` (+245), `fixtures/fixtures.js` (−210), `fixtures/registry.js`; Tests neu `tests/test_viz13c_updatedmx_registry.py` + `tests/test_viz13c_updatedmx_golden.json`.

### 2026-07-05 — 3D-Visualizer: 2D-Plan poliert (VIZ-13 3c-1 Ortho-2D-Polish)

#### Neu / Hinzugefuegt

- **2D-Icons überall klar sichtbar:** jede Icon-Form trägt jetzt eine permanente helle Umriss-Linie und unbelichtete Geräte füllen heller (vorher Dunkelgrau auf dunklem Boden = fast unsichtbar). Umrisse/Glyphen zeichnen zuverlässig über den durchscheinenden Bühnenflächen.
- **Eigene 2D-Symbole für PAR-Bar & Mover-Bar:** Balken mit N Einzel-Zellen (Mover-Bar zusätzlich mit Richtungs-Pfeil), die Zellen färben **pro Kopf** mit dem Live-DMX (Paritaet zu den FM-6-Symbolen der 2D-Live-View; vorher fielen beide auf den namenlosen Default-Kreis). Spider-Icon färbt seine zwei Bars einzeln; PAR bekommt einen Linsen-Ring. Zentrales `tintTopDownIcon()` ersetzt vier kopierte Farb-Blöcke.
- **Bühnen-Grundriss:** Boden/Plattformen/Trassen/Wände zeigen im 2D-Plan eine klare Footprint-Umriss-Linie in ihrer Typ-Farbe (folgt Position/Rotation live, vom Raycast ausgenommen — Picking/Docking bleiben präzise).

#### Geaendert / Fixes

- **Footer-Gesten-Hint folgt dem Modus:** im 2D-Plan stehen jetzt die 2D-Gesten (Schwenken/Zoom/Verschieben/Reset) statt dauerhaft des 3D-Texts.
- Selektionsring der Bar-Icons ist größer als die Bar (vorher komplett von der Form überdeckt) und vom Raycast ausgenommen (der unsichtbare Ring stahl Klicks neben dem Icon).
- Glyph-Linien rendern im Transparent-Pass — vorher übermalte der Body-Fill die Glyphen bei voller Intensität (vorbestehend, in der adversarialen Review gefunden).
- Icons übernehmen ihre Y-Rotation schon beim Erzeugen — längliche Icons (Bars/Spider) lagen nach dem Show-Reload quer, bis zur ersten Rotations-Geste (vorbestehend).
- `scene_src/three/three.js`-Wrapper exportiert zusätzlich `EdgesGeometry`/`LineLoop`.
- Dateien: `scene_src/fixtures/topdown_icons.js`, `fixtures/fixtures.js`, `stage/view_mode.js`, `stage/stage_objects.js`, `three/three.js`; Tests `tests/test_viz13c1_topdown_polish.py` (echte Page, offscreen QWebEngine).

### 2026-07-04 — Laser-Support: Werksmuster-Picker für DMX-Muster-Laser (LAS-18b)

#### Neu / Hinzugefuegt

- **Werksmuster als Kacheln:** neue Box „Werksmuster (Gerät)" in der Laser-Steuerseite (nur für reine DMX-Muster-Laser wie den Ehaho L2600, Klassen-Gate über `laser_capability`). „➕ Muster merken…" nimmt die aktuellen Bank-/Muster-Programmerwerte, fragt einen Namen und optional ein **Foto vom realen Laser-Output** (die Werksmuster sind herstellerseitig unbenannt — die Vorschau-Bibliothek baut sich der Nutzer selbst). Kacheln zeigen das Foto oder eine B/M-Nummer; Linksklick ruft das Muster ab (kopf-korrekt Gruppe A/B), Rechtsklick löscht den Slot. Show-persistent als additiver `.lshow`-Block. NEU `src/core/laser/pattern_slots.py`; `app_state.py`, `show_file.py`, `laser_view.py`; Tests `tests/test_laser_pattern_picker.py` + Show-Roundtrip.

### 2026-07-04 — Laser-Support: Zeichen-Studio komplett + L2600-Bedienung (LAS-11…LAS-19, Sammel-Eintrag)

#### Neu / Hinzugefuegt

- **Laser-Steuerseite aufgeräumt (LAS-11, PR #160):** Regler nach Bedeutung gruppiert (Muster/Farbe/Bewegung & Geschwindigkeit/Zeichnen + einklappbare „Weitere Kanäle"), Shutter nur noch als „Betriebsart"-Kacheln.
- **Fähigkeits-Klassifikator (LAS-12, PR #161):** `laser_capability()` entscheidet je Laser ehrlich, ob eine gemalte Figur exakt ausgebbar ist (Netz/ILDA) oder nur Werksmuster gehen (L2600) — eine Wahrheitsquelle für alle Laser-UIs.
- **Laser-Zeichen-Studio (LAS-13…LAS-17, PRs #162/#163/#166/#167/#171/#173):** Vollbild-Popout mit Ehrlichkeits-Banner, Formwerkzeuge (Kreis/Rechteck/Linie/Polygon/Stern) per Aufziehen mit Live-Vorschau, Freihand mit RDP-Glätten, Undo/Redo (Strg+Z/Y) + Raster-Einrasten, Figuren-Bibliothek mit Vorschau-Kacheln.
- **VC-Muster-Abruf (LAS-18, PR #169):** ButtonAction „Laser-Muster abrufen" ruft eine gespeicherte Laser-Palette auf Knopfdruck (Sicherheits-Härtung: nur die aufgenommenen Fixtures).
- **VC-Laser-Speed (PR #175):** der „Programmer-Attribut"-Fader mappt 0–100 % auf ein Wert-Teilband (z. B. `gobo_rotation` 192–223) — hält den L2600 im Dreh-Modus und regelt nur das Tempo.
- **Bild-Import → Vektor (LAS-19, PR #178):** „🖼️ Bild importieren…" im Studio vektorisiert ein Bild (Komponenten + Moore-Tracing + RDP) zur editierbaren Figur.

#### Geaendert / Verifiziert

- **L2600-Profil vollständig am Handbuch verifiziert (PRs #179/#181):** 34 Kanäle bestätigt (Herstellerseite „32ch" falsch), CH18-Semantik geklärt (Shutter-Default 0 korrekt), CH20 leer bestätigt, `laser_y`-Bewegungs-Labels ans Handbuch angeglichen.

### 2026-07-04 — Laser-Support: Sicherheit von der Virtual Console bedienbar (LAS-10)

#### Neu / Hinzugefuegt

- **Laser Scharfschalten + Not-Aus als VC-Buttons:** zwei neue Aktionen für Virtual-Console-Tasten (auch per MIDI-Pad auslösbar) — „Laser scharf/unscharf" (`LASER_ARM`, Toggle; Farbbalken lila wenn scharf) und „Laser NOT-AUS" (`LASER_ESTOP`, roter Balken). Der Not-Aus verriegelt, entwaffnet und öffnet die Session wieder (dieselbe sichere Reihenfolge wie in der Laser-Steuerseite). Damit lässt sich der Laser-Not-Aus auf eine feste, immer erreichbare Taste legen. Die Laser-Steuerseite spiegelt Scharf/Unscharf-Änderungen von der Konsole (`_sync_arm_from_manager`). `src/ui/virtualconsole/vc_button.py`, `src/ui/views/laser_view.py`, Tests `tests/test_laser_vc_safety.py`.

### 2026-07-04 — Laser-Support: Interaktiver Zeichen-Editor + Muster-Persistenz (LAS-07b)

#### Neu / Hinzugefuegt

- **Laser-Muster zeichnen:** neuer XY-Zeichen-Editor (`src/ui/widgets/laser_draw_editor.py`) — über den „✏️ Zeichnen…"-Knopf in der Laser-Steuerseite. Punkte per Klick setzen, ziehen zum Verschieben, aus einer 7-Farb-Palette einfärben, einzelne Punkte als „unsichtbaren Sprung" (Blank) markieren, offene Linie oder geschlossenes Polygon. Normierte −1..+1-Zeichenfläche (0,0 = Mitte, +y = oben) mit Live-Vorschau der Linien in Punktfarbe. **Beim Zeichnen wird das Muster live an scharf geschaltete Netzwerk-Laser gestreamt** — sichtbar nur, wenn der Laser über die Sicherheits-Sektion bewusst scharf ist (das Arming aus LAS-07a bleibt die alleinige Licht-Freigabe).
- **Gezeichnete Muster sind Show-persistent:** gespeicherte Figuren (`AppState.laser_figures`) landen in der `.lshow` (save/load/reset in `show_file.py`) und erscheinen mit ★ in der Ausgabe-Auswahl der Laser-Steuerseite — abrufbar wie die eingebauten Grundfiguren. Tests `tests/test_laser_draw_editor.py` + Show-Roundtrip in `test_show_file.py`.

### 2026-07-04 — Laser-Support: Zeichenmodus-Fundament — Arming-Safety + Figuren (LAS-07a)

#### Neu / Hinzugefuegt

- **Laser-Scharfschalten (Safety-Ebene):** Die Netzwerk-Laser-Ausgabe startet jetzt **unscharf** — solange nicht bewusst scharf geschaltet, wird jeder Streaming-Frame geblankt (Vorschau ohne Lichtaustritt). Umgesetzt im `LaserOutputManager` (`armed`/`set_armed`, im `_tick`-`dark`-Flag neben BLACKOUT und Not-Aus). In der Laser-Steuerseite gibt es dafür eine **Sicherheits-Sektion** (nur bei Netzwerk-Lasern): großer Scharf/Unscharf-Umschalter mit Warnfarbe, prominenter **Not-Aus-Button** (löst `estop_all` aus und schaltet zurück auf unscharf) und ein Warnhinweis. Ein Show-Load entwaffnet automatisch. `src/core/laser/laser_output.py`, `src/ui/views/laser_view.py`.
- **Laser-Zeichenfiguren (`LaserFigure`):** neues Modell `src/core/laser/figure.py` — eine benannte, normierte Punktliste (Position −1..+1, Farbe je Punkt, Blank-Segmente, offen/geschlossen) mit `to_frame`-Resampling (gleichmäßige Abtastung + Offset/Scale aus den Programmer-Werten), Serialisierung und eingebauten Startfiguren (Kreis/Dreieck/Quadrat/Linie). Der `LaserOutputManager` kann per `set_figure(fid, …)` eine Figur als Framequelle setzen (statt des Kreis-Testmusters); die Laser-Steuerseite bietet die Auswahl an. Grundlage für den interaktiven Zeichen-Canvas (LAS-07b). Tests `tests/test_laser_figure.py`.

### 2026-07-03 — Laser-Support: IDN-Stream-Backend (LAS-06)

#### Neu / Hinzugefuegt

- **IDN-Netzwerk-Laser (ILDA Digital Network):** zweites Punkt-Streaming-Backend neben Ether Dream, `src/core/laser/idn.py`. Voller IDN-Stream/-Hello-Treiber in reinem `struct`/`socket`-Python, Wire-Format gegen die offizielle ILDA-Spezifikation (IDN-Stream Rev001/Rev002) **und** die DexLogic-Referenzimplementierung (helios_openidn) verifiziert: UDP-Port 7255, 4-Byte-IDN-Hello-Header + Channel-Message-Header + Channel-Configuration mit dem Standard-Tag-Dictionary für X:16/Y:16/R:8/G:8/B:8 + Sample-Chunk, durchgehend Big-Endian; session-freies Streaming (Realtime-Channel-Message 0x40 mit hochzählender Sequence), Graceful Close (0x44) und Abort (0x46) als Not-Aus, optionale Geräte-Discovery per Scan (0x10/0x11). `IDNConnection` teilt die Connection-Schnittstelle mit Ether Dream, sodass der **`LaserOutputManager` beide Backends über eine Protokoll-Weiche** (`_factory_for`) bedient — Safety (BLACKOUT-Blanking, E-Stop, Backoff) und Framequelle bleiben backend-neutral. Der Patch-Dialog bietet Laser nun drei Protokolle (DMX / Ether Dream / **IDN**). v1: ein Frame = ein UDP-Paket; zu punktreiche Frames werden geometrie-erhaltend heruntergerechnet (App-Fragmentierung folgt mit dem Zeichenmodus). Tests `tests/test_laser_idn.py` (Wire-Format-Golden-Bytes, Fake-UDP-Empfänger, Manager-Protokoll-Weiche).

### 2026-07-03 — Laser-Support: Ether-Dream-Punkt-Streaming (LAS-05)

#### Neu / Hinzugefuegt

- **Netzwerk-Laser-Streaming (Ether Dream):** neues Paket `src/core/laser/` — `frame.py` (neutrales `LaserFrame`/`LaserPoint`-Modell + **Safety-Clamping** `clamp_frame`/`LaserLimits`: Scan-Ausschlag-, Punktraten- und Helligkeits-Limits, Mindest-Punktzahl gegen stehende Strahlen), `etherdream.py` (vollständiger Treiber für das offene Ether-Dream-Protokoll: TCP-Befehle prepare/begin/data/stop/**E-Stop/Clear**, UDP-Discovery, reine struct/socket-Implementierung, ohne Hardware testbar) und `laser_output.py` (`LaserOutputManager`: eigener 30-fps-Streaming-Thread getrennt von der 44-Hz-DMX-Pipeline; v1-Framequelle = Kreis-Testmuster aus den Programmer-Werten mit **Shutter-Gate**; **BLACKOUT blankt jeden Frame**, `estop_all()` verriegelt; Reconnect-Backoff je Gerät).
- **`PatchedFixture.net_host`** (IP/Hostname der DAC) mit Migration, `.lshow`-Serialisierung und Undo-Integration; **Protokoll-Auswahl im Patch-Dialog** für Laser (DMX ↔ Ether Dream): bei Netzwerk werden Universe/Adresse deaktiviert, das IP-Feld aktiviert und Adress-Konfliktwarnungen unterdrückt. Lifecycle: Start in `AppState.start_playback` (Env-Gate `LIGHTOS_NO_OUTPUT_THREAD`), Stop im MainWindow-Shutdown. Tests `tests/test_laser_etherdream.py` (Fake-DAC-Server, Clamping, Blackout/E-Stop/Backoff, net_host-Roundtrip).

### 2026-07-03 — Laser-Support: Pangolin-FB4-Profile (LAS-08-Teil 1)

#### Neu / Hinzugefuegt

- **Pangolin FB4 als Builtin-Fixture** (`PANGFB4`, Hersteller Pangolin, Typ laser): offizielles **16-Kanal-„FB3"-Profil** (Moduswahl auf Ch1, Seiten/Cues, Dimmer/Zoom/Größe/Position, Scan-Rate, Cue-Freigabe, Farbscrollen) und **39-Kanal-Profil** (Setup-Block Ch2-13 mit 16-bit-Paaren + Playback-Block Ch14-39 inkl. RGB-Override, Punkt-Trimming und Strobe) — Charts aus dem Pangolin-Wiki (`hardware:fb4:dmx16`/`dmx39`). Setup/Playback-Duplikate laufen als Mehrkopf (Kopf 1/2), Feinkanäle als `raw`. **Safety-Defaults:** Ch1 = Blackout/Safe, Dimmer = 0, kontinuierliche Z-Rotation = Stillstand. Damit sind Profi-Laser hinter FB4/QuickShow/BEYOND ab sofort über die bestehende DMX/Art-Net-Pipeline fernsteuerbar (inkl. Laser-Tab). Neues Kanal-Attribut `laser_scan_rate`. `src/core/database/fixture_db.py`, Vokabular-Dateien, Tests `tests/test_pangolin_fb4_profile.py`.

### 2026-07-03 — Stabilität: Repo-weiter GC-Teardown-Sweep über src/ui (STAB-10)

#### Behoben / Geändert

- **Owner-Zyklen gebrochen (native-AV-Klasse aus STAB-09):** starke Kind→Owner-Referenzen zykelten Top-Level-Views über Shibokens GC-sichtbare Parent→Kind-Wrapper-Kante — der Owner starb dann nur in der zyklischen GC (PySide6 6.11/Py 3.14: Access Violation beim GC-Teardown, faulthandler „Garbage-collecting"). Per weakref + Property + None-Guards gefixt: `EfxPopoutDialog._view` (+ alle internen Slots/Preview-Callback), `AttributeSlider._owner` (programmer_view), `_AspectRow._parent` (vc_drop_panel), `EfxView`-Preview-Geometrie-Callback sowie `status_cb` des RenderCrashGuard (visualizer_view/-window).
- **Lambda-Slot-Sweep (`src/ui/`):** self-fangende Lambda-Slots in langlebigen, nicht-modalen Widgets werden von der C++-Connection STARK und GC-unsichtbar gehalten (Wrapper-Pin → Leak + Use-after-free-Fenster). Repo-weit durch Bound-Method-Slots (bindet PySide6 schwach), sender()-Adapter bzw. die neuen Helfer `weak_slot`/`weak_slot_fwd` ersetzt (~90 Sites in 38 Dateien; `functools.partial` pinnt übrigens genauso — empirisch verifiziert). Bewusst unangetastet: transiente Kontextmenü-Lambdas (menu.exec), modale exec()-Dialoge und `self.destroyed`-Teardown-Slots (dort ist der Pin gewollt und funktional nötig).
- **Neu:** `src/ui/weak_slots.py` (Slot-Adapter mit weakref-Receiver, inkl. Fallback für Qt-Builtin-Methoden ohne `__func__`) + Regressionstests `tests/test_ui_teardown_gc.py` (Refcount-Tod von EfxView/Popout und AttributeSlider-Owner per gc.disable-Probe, None-Guards nach View-Tod, weak_slot-Semantik; der EfxView-Test crashte auf dem Stand VOR dem Preview-Callback-Fix nativ und beißt damit nachweislich).
- **Canary-Verifikation:** Die 6 unter dem weak-sync-Zwischenstand (#142, per #145 zurückgestellt) nativ crashenden Testdateien (Matrix-Views + Programmer-Editor) laufen mit dem Sweep zu 5/6 sogar auf dem weak-sync-Stand grün; `test_matrix_dirty_save` deckt eine verbleibende Zerstörungs-Fragilität der RgbMatrixView auf (unter dem aktuellen starken Bus nicht erreichbar) — dokumentiert als Blocker für das künftige sync-Re-Landing.

### 2026-07-02 — Laser-Support: Netzwerk-Laser-Grundlagen (LAS-04)

#### Neu / Hinzugefuegt

- **`PatchedFixture.protocol`** (`'dmx'` Default | `'etherdream'` | `'idn'`): Fundament für die zweite Laser-Klasse (Netzwerk-Laser ohne DMX-Adressraum). Idempotente ALTER-TABLE-Migration, `.lshow`-Serialisierung beidseitig (Alt-Shows laden als `'dmx'`), Undo-/`update_fixture`-Integration. Neuer Helper **`fixture_uses_dmx()`** gated ALLE vier Adress-Schreibstellen (`_rebuild_render_plan` Defaults/Spans/GM-Maske, `_flush_programmer_to_dmx`, `_apply_fixture_map`, Executor-`_flush_to_dmx`): Die Platzhalter-Adresse eines Netzwerk-Lasers kann nie in die DMX-Spans echter Geräte schreiben; seine Programmer-Werte bleiben erhalten und werden später vom `LaserOutputManager` (LAS-05) gelesen. `src/core/database/models.py`, `src/core/app_state.py`, `src/core/show/show_file.py`, `src/core/engine/executor.py`, Tests `tests/test_laser_protocol_field.py`.

### 2026-07-02 — Laser-Support: Laser-Tab im Programmer (LAS-02 + LAS-03-Grundlage)

#### Neu / Hinzugefuegt

- **Laser-Tab im Programmer (`LaserView`):** neue Steuerseite `src/ui/views/laser_view.py`, eingebettet als Programmer-Tab nach dem EFX/Matrix-Muster (`follow_selection=True`), sichtbar nur wenn die Auswahl Laser enthält (`fixture_type='laser'` oder `laser_*`-Kanäle). Inhalt: **Mustergruppe A/B/A+B**-Umschalter (Mehrkopf `attr#N`, Kopf-B-Schreibschutz für Einzel-Attribute nach ENG-03-Muster), **Modus-Schnellwahl** (Shutter-Ranges Aus/Auto/Sound/Muster als Kacheln), **Range-beschriftete Regler** je Laser-Kanal (Slider + Spin + Bereichs-Combo aus den ChannelRanges) und **Muster-Paletten**. `src/ui/views/programmer_view.py` (Tab + Sichtbarkeit in `_rebuild_attr_editor`), Tests `tests/test_laser_view.py`.
- **Laser-Muster-Paletten (`PaletteType.LASER`):** neuer Paletten-Typ in der Palette-Engine (erfasst `laser_*` + Shutter/Muster/Zoom/Rotation/Farbrad/Makro/Speed), eigener „Laser"-Tab in der Paletten-View, „💾 Muster speichern…" direkt in der LaserView (speichert pro Mustergruppe/Kopf). `src/core/engine/palette.py`, `src/ui/views/palette_view.py`.

### 2026-07-02 — Laser-Support: Ehaho-L2600-Builtin + Laser-Vokabular (LAS-01)

#### Neu / Hinzugefuegt

- **Ehaho L2600 („3D Partylight") als Builtin-Fixture:** Modi „6-Kanal (Simple DMX)" und „34-Kanal (Professional DMX)" mit allen Wertebereichen aus dem offiziellen Manual (ManualsLib #3494357; DMXControl-DDF als Gegenprobe). Im 34ch-Modus sind Mustergruppe A (Ch1-17) und B (Ch18-34) über die Mehrkopf-Konvention als Kopf 1/Kopf 2 getrennt steuerbar. **Laser-Safety-Default:** On/Off-Kanäle defaulten auf 0 (aus) — ein frisch gepatchter Laser feuert nicht. `src/core/database/fixture_db.py` (Seed + idempotentes `ensure_builtins`), Tests `tests/test_ehaho_l2600_profile.py`.
- **Laser-Attribut-Vokabular:** 13 neue Kanal-Attribute (`laser_boundary`, `laser_bank`, `laser_x/y`, `laser_zoom_x/y`, `laser_color`, `laser_color_change`, `laser_dots`, `laser_draw`, `laser_draw_mode`, `laser_twist`, `laser_grating`) in `CHANNEL_ATTRS`, exakt in `ATTR_GROUPS['Effect']` (Schutz vor Color-Substring-Fehlklassifikation → kein Feature-Dimmer auf Range-Select-Kanälen) und mit deutschen Labels. `src/ui/widgets/fixture_editor.py`, `src/core/attr_groups.py`.
- **Fixture-Klassen-Audit festgenagelt:** Test sichert, dass jedes Builtin eine echte Klasse trägt (nie `other`) und Schlüsselgeräte (PAR/Moving-Head/LED-Bar/Laser) korrekt klassifiziert sind.
- **Laser-Fahrplan:** `docs/LASER_PLAN.md` (L2600-Recherche, Netzwerk-Protokoll-Marktlage Ether Dream/IDN/Pangolin/ShowNET, Zwei-Klassen-Architektur DMX vs. Punkt-Streaming, Safety-Konzept) + Backlog-Epic LAS-01…LAS-09.

### 2026-07-01 — Live-Edit-Fenster + VC-Aufräumen (Davids VC-Umbau)

#### Neu / Hinzugefuegt

- **Live-Edit-Fenster (`VCMultiLiveEditor`):** ein frei schwebendes, größenveränderliches, **nicht in der Show gespeichertes** Fenster (Toolbar-Knopf „Live-Edit", auch im Live-Betrieb), in das man mehrere Effekte (Matrix / EFX-Bewegung / Chaser) per Drag&Drop zieht und mit Dropdown + „– / +" durchblättert. Pro Effekt: **Vorschau je Typ** (Matrix-Pixel / EFX-Bewegungspfad mit laufendem Punkt / Chaser-Schrittleiste), ein **Checkbox-Parameter-Editor** (anhaken → nur dafür erscheint ein Regler; live über `effect_live`, baseline-geschützt = flüchtig) und ein **Tempo-Modus** (Aus = freie Geschwindigkeit direkt, BPM = Master-Bus + Tempo-×-Faktor, Tap = eigener Takt pro Effekt auf festem Bus A–D). Alle Änderungen sind LIVE, aber **nicht persistent** (Show-Speichern schreibt die Preset-Werte). 4 PRs: [#119](https://github.com/ixamgames-droid/lightos/pull/119), [#120](https://github.com/ixamgames-droid/lightos/pull/120), [#121](https://github.com/ixamgames-droid/lightos/pull/121), [#122](https://github.com/ixamgames-droid/lightos/pull/122). Doku `docs/LIVE_EDIT_FENSTER.md`. `src/ui/virtualconsole/vc_multi_live_editor.py`.

#### Entfernt

- **Chase Builder (`VCChaseBuilder`):** das All-in-One-Chase-Widget komplett entfernt (Widget + Registry + Toolbar-Quick-Add + Inspector-Label + 10 Show-Generatoren + Doku). Alte Shows laden tolerant (unbekannter Widget-Typ wird beim Laden übersprungen). [#116](https://github.com/ixamgames-droid/lightos/pull/116)
- **Editor-Bausteine „⌗ Controller / 🎨 Color-Chase / 🟦 Chase-Bereich":** die drei edit-only Toolbar-Knöpfe oben rechts + ihre Handler und das Canvas-Aufzieh-Werkzeug (Rubber-Band/`area_selected`) entfernt; `controller_templates.py` auf das APC-Pad-Panel reduziert (Color-Chase-Baukasten gestrippt). [#118](https://github.com/ixamgames-droid/lightos/pull/118)

### 2026-06-30 — Neu

#### Neu / Hinzugefuegt

- **Feature-Dimmer-Master (F-26 + F-26b):** Ein effekt-**unabhängiger** per-Slot-Submaster, der die gewählte **Feature-Gruppe** (Intensity/Color/Gobo/Beam/Position/Effect) einer festen Fixture-Gruppe multiplikativ am fertig gerenderten Output skaliert (Render-Schritt 4b², NACH allen Effekten/Programmer). Mehrere Slots stapeln (Produkt) mit eigener Identität — anders als der flache `fixture_dimmers` („last writer wins"). **Backend** (`FeatureDimmer`-Dataclass, `AppState.feature_dimmers`, `set_feature_dimmer`/`clear_feature_dimmers`, Render 4b²) koordiniert von einem parallelen Branch übernommen. **VC-Bindung (F-26b):** neuer `SliderMode.FEATURE_DIMMER` (Fader-Modus „Feature-Dimmer (Gruppe)") mit Gruppen- + **Feature-ComboBox aus den Fixture-Capabilities** der gewählten Gruppe; Slot-Sync beim Properties-Dialog (enter/leave), Re-Apply beim Show-Laden (analog VCB-32), Slot-Räumung beim Löschen des Faders und `clear_feature_dimmers()` bei Show reset/load. +13 Backend- +9 VC-Tests (`tests/test_feature_dimmer.py`, `tests/test_feature_dimmer_vc.py`). `src/core/app_state.py`, `src/ui/virtualconsole/vc_slider.py`, `src/core/show/show_file.py`.

- **VC-Button: quadratische Standard-Größe (UI-13):** Neu hinzugefügte Buttons sind jetzt **quadratisch** (72×72, grid-aligned) statt länglich (120×60) — der Pad-Look, den der Demo-Show-Generator schon immer baut, ist damit die Standardgröße beim Hand-Platzieren. Bestehende Shows laden ihre eigene Geometrie und bleiben unverändert (nur die Neuanlage betroffen). `src/ui/virtualconsole/vc_button.py`.
- **VC-Button: Farb-/Effekt-Vorschau-Badge oben rechts (UI-13):** Ein Button mit gebundenem Farb-Effekt oder Farb-Snap zeigt jetzt — analog zum Gobo-Icon — oben rechts einen kleinen Farb-Kreis. Steuert der Effekt **mehrere Farben** (Farbwechsel), **wechselt das Eck-Icon zyklisch** durch die Farben (animiert, Timer nur aktiv solange das Widget sichtbar UND mehrfarbig ist → keine Off-Bank-CPU). Nicht-farbige Effekte (Dimmer-/Shutter-Style → `has_colors=False`) bekommen bewusst kein Badge. `src/ui/virtualconsole/vc_button.py`, `tests/test_vc_button_color_badge.py`.

#### Behoben

- **Show-Generatoren bauen den Patch wieder vollständig (DEMO-02):** Auf Windows re-importierte ein vom OutputManager via `multiprocessing`-`spawn` gestarteter Serial-Worker-Kindprozess das ungeschützte Generator-Skript als `__mp_main__` → der Build-Code lief ein zweites Mal, zwei Prozesse bauten auf derselben Show-DB, der FLD-FID-Guard wich aus → **nur ein Teil der Fixtures** landete im Patch (Symptom: `python -c` baut sauber, `python tools/build_x.py` nur teilweise). Neues Single-Point-Bootstrap `tools/_gen_env.py` setzt beim Import — vor `app_state`/`output_manager` — `LIGHTOS_SERIAL_INPROC=1` (kein Spawn, In-Prozess-Enttec) + `LIGHTOS_NO_OUTPUT_THREAD=1` + `LIGHTOS_NO_AUDIO_AUTOSTART=1` (wie die Test-conftest), `import _gen_env` in alle 30 bauenden `tools/build_*.py` ergänzt (`_builder`-basierte Generatoren über `tools/_builder.py` automatisch; `build_hardstyle_vc.py` ist per `__main__`-Guard schon sicher). `tools/_gen_env.py`, `tools/_builder.py`, `tools/build_*.py`, `tests/test_generator_spawn_safe.py`.
- **`reset_show()` räumt verwaiste Patch-Zeilen jetzt hart (DEMO-03):** Nach einem abgestürzten Generator-Lauf konnten Patch-Zeilen in `current_show.db` liegen bleiben; `reset_show()` (via `_replace_patch_from_data(state, [])`) löschte sie nicht garantiert hart — schlug das interne `clear_patch()` fehl, räumte der Fallback nur über den Cache auf, sodass verwaiste DB-Zeilen den FLD-FID-Guard auf `next_fid()` ausweichen ließen (überraschend verschobene fids). `reset_show()` ruft jetzt zusätzlich explizit `state.clear_patch()` (hartes `DELETE` der Patch-Tabelle), wie `load_show` es schon tut. `src/core/show/show_file.py`, `tests/test_reset_show_clear_patch.py`.
- **`ColorSequence` ist iterierbar/indexierbar (DEMO-05):** `for c in matrix.colors` / `list(matrix.colors)` / `matrix.colors[i]` warf `TypeError` (nur `len()`/`set_color` gingen) — erschwerte Tools/Debugging. Neue `__iter__`/`__getitem__` liefern die `(r,g,b)`-Tupel (rein additiv, kein bestehender Code verlässt sich auf „nicht iterierbar"). `src/core/engine/rgb_matrix.py`, `tests/test_color_sequence_iter.py`.
- **Bus-gekoppelte Matrix friert nicht mehr dunkel ein (DEMO-04):** Ein an einen Tempo-Bus gekoppelter Matrix-Effekt fror auf der (statischen) Bus-Position ein, wenn der Bus zwar eine BPM>0 hatte, seine Position aber nicht vorrückte — z. B. in Render-Pfaden **ohne** laufende `advance_frame`-Schleife (Effekt-Vorschauen, Capability-`render_probe`, Show-Validierung, Generatoren, Headless-Selbsttests) oder bei pausierter Bus-Uhr. Bei **Dimmer-Style** bedeutet „eingefroren" = Intensität 0 = **Fixtures dunkel**. `RgbMatrixInstance._advance_step` erkennt den stehenden Bus jetzt am Positions-Delta über einen echten Zeitschritt (`dt>0`, Position unverändert) und fällt auf **Free-Run** (`matrix_speed`) zurück statt einzufrieren; bei Bus-Wiederanlauf snappt der nächste Frame zurück auf Bus-Sync. Live (Render-Thread tickt jeden Frame) bleibt die Position in Bewegung → **byte-identisch**; `dt==0`-Re-Evaluationen (z. B. direkt nach „Jetzt synchronisieren") rechnen weiter sauber den Bus-Sync-Wert. Globaler Freeze (F5) hält bewusst weiter an. `src/core/engine/rgb_matrix.py`, `tests/test_demo04_bus_freerun.py`.
- **Weiß-Erkennung bei RGBW (UI-13):** Reines RGBW-Weiß (W-Kanal=255, RGB=0) wurde als **schwarzer Knopf** dargestellt, weil die Kachel-/Swatch-Farbe nur `color_r/g/b` las und den Weiß-Kanal ignorierte. Neuer zentraler Qt-freier Helfer `color_utils.rgbw_to_display`/`display_rgb_from_attrs` faltet den Weißanteil additiv zurück in die Anzeige-RGB → Weiß erscheint als Weiß (Snap-Swatch + neues Badge). Zusätzlich faltet die **VC-Farbkachel beim Senden an Effekt-Farb-Ziele** (`add_color`/`set_selected_color`/`color1..3`) den Weiß-Kanal ein — eine als RGBW-Weiß definierte Kachel landete sonst als Schwarz in der Color-Sequence (Wurzel von „weißer Effekt = schwarzer Knopf"). `src/core/color_utils.py`, `src/ui/virtualconsole/vc_button.py`, `src/ui/virtualconsole/vc_color.py`, `tests/test_vc_button_color_badge.py`.
- **GROUP_DIMMER/SUBMASTER-Fader beim Show-Laden wieder wirksam (VCB-32):** Die `apply_dict`-Direktzuweisung an `_value` umging den `@value.setter` (der `_apply()` ruft) — ein gespeicherter Gruppen-Dimmer/Submaster unter 100 % wurde beim Laden nicht angewendet (`fixture_dimmers` wird seit VCB-05 bei load/reset geleert), die Show kam **zu hell** hoch, bis der Nutzer den Fader bewegte. `apply_dict` ruft jetzt für GROUP_DIMMER/SUBMASTER nach dem Laden `_apply()` nach. Codex-Folgebefund auf [PR #100]. `src/ui/virtualconsole/vc_slider.py`, `tests/test_vc_codex_followups_101.py`.
- **`range_max=0` bleibt erhalten (VCB-33):** Ein bewusst auf `range_max=0` gesetzter Fader (Kappung/Stummschaltung; `_effective_value` erlaubt min==max) wurde vom `or 255`-Fallback als „fehlt" gewertet und beim Reload auf 255 gesetzt → Ausgabe statt Stille. Nur noch echtes `None`/Fehlen fällt auf 255 zurück. Codex-Folgebefund auf [PR #101]. `src/ui/virtualconsole/vc_slider.py`, `tests/test_vc_codex_followups_101.py`.
- **GROUP_DIMMER-Retarget lässt keine Geister-Gruppe zurück (VCB-34):** Wird ein Gruppen-Dimmer-Fader von Gruppe A auf B umgehängt (beide bleiben GROUP_DIMMER), blieb A weiter gedimmt — das VCB-19-`elif` traf den Retarget-Fall nicht. Die Slot-Synchronisierung nach dem Properties-Dialog wurde in `_post_dialog_mode_sync` ausgelagert (testbar) und setzt die alte Gruppe vor dem Anwenden der neuen zurück. Codex-Folgebefund auf [PR #101]. `src/ui/virtualconsole/vc_slider.py`, `tests/test_vc_codex_followups_101.py`.
- **Effekt-Farb-Badge im Aktiv-Effekt-Modus repaintet (UI-14c):** VCColor/VCEffectColors ohne feste `function_id` (Aktiv-Effekt-Modus) riefen `refresh_effect_badges(None)`, was am `int(None)`-Guard scheiterte → das UI-14b-Badge des gebundenen Buttons aktualisierte sich nach einem Live-Color-Edit nicht. `refresh_effect_badges` löst `None` jetzt zentral auf den aktiven Effekt auf (fixt VCColor **und** VCEffectColors). Codex-Folgebefund auf [PR #101]. `src/ui/virtualconsole/vc_canvas.py`, `tests/test_vc_codex_followups_101.py`.
- **Test-Gate: `create_all` idempotent gegen vorhandenes Schema (QA-06):** `test_vc_tempo_live_coupling` errorte (zuletzt deterministisch) im `reset_show`-Teardown mit `OperationalError: table manufacturers already exists`. `Base.metadata.create_all(checkfirst=True)` reflektiert vor jedem `CREATE` das `sqlite_master`; greifen zwei Verbindungen/Läufe auf dieselbe SQLite-Datei zu (neu aufgebaute Engine bei noch offener alter Verbindung, paralleler Lauf), liegt zwischen Reflexion und `CREATE` ein TOCTOU-Fenster, in dem der eigene `CREATE` mit „already exists" kollidiert. Neuer Helfer `create_all_idempotent` schluckt genau diesen harmlosen Fall (die Tabellen sind dann bereits da) und lässt jeden anderen `OperationalError` weiterfliegen; verdrahtet in `app_state.open_show`, `models.create_db` und `fixture_db.get_engine`. `src/core/database/models.py`, `src/core/app_state.py`, `src/core/database/fixture_db.py`, `tests/test_qa06_create_all_idempotent.py`.
- **XY-Pad: 8-bit-Ausgabe rundet statt abzuschneiden (VCB-11):** `VCXYPad._write_axis` schrieb im 8-bit-Pfad `int(frac*255)` (Abschneiden) → systematischer -0,5-LSB-Bias über den ganzen Pad-Bereich; jetzt `int(round(...))` wie der 16-bit-Pfad. `src/ui/virtualconsole/vc_xypad.py`.
- **Speed-Dial: BPM-Bereich wird persistiert (VCB-12):** `_min_bpm`/`_max_bpm` wurden weder in `to_dict` geschrieben noch in `apply_dict` gelesen → ein konfigurierter BPM-Bereich fiel beim Show-Reload still auf 20–600 zurück. Beide Felder werden jetzt serialisiert/deserialisiert. `src/ui/virtualconsole/vc_speedial.py`.
- **Speed-Dial: Live-Anzeige invert-korrekt (VCB-13):** Im `TEMPO_BUS_MULT`-Modus zeigte `_live_bpm_probe` `bus.bpm × _active_factor` (roh), während `_apply()` den invert-bewussten `_effective_mult()` als `tempo_multiplier` schreibt → bei aktivem Invert wich die angezeigte BPM vom tatsächlich geschriebenen Wert ab. Die Anzeige nutzt jetzt denselben `_effective_mult()` (ohne Invert unverändert). `src/ui/virtualconsole/vc_speedial.py`.
- **Stepper: Label zeigt per-Fixture-Wert (VCB-14):** `VCStepper._current_value` las den Parameter mit dem generischen `param_key` statt mit dem per-Fixture-Key (`_key_for(_fid())`, wie `step_by`/`_spec`) → bei Multi-Fixture-Bindungen mit eigenem Key je Effekt zeigte das Label den falschen Wert. `src/ui/virtualconsole/vc_stepper.py`.
- **Slider: kein Crash bei winziger Höhe (VCB-15):** `VCSlider.mouseMoveEvent` teilte durch `_track_rect().height()` (= Höhe − 40); ein auf ≤ 40 px geschrumpfter Fader führte beim Ziehen zu `ZeroDivisionError`. Jetzt mit `> 0`-Guard. `src/ui/virtualconsole/vc_slider.py`.
- **VC-Farbkachel: Live-Edit-Baseline für Effekt-Pfade (VCB-16):** `VCColor._apply` rief in den `EFFECT`/`EFFECT_ADD`/`color1..3`-Pfaden — anders als das symmetrische `VCEffectColors` — kein `effect_live.begin_live_edit()` → inkonsistenter Live-Edit-Zustand. Jetzt wird die Baseline vor jeder Mutation gesetzt. `src/ui/virtualconsole/vc_color.py`.
- **VC-Farbkachel: negative function_id abgelehnt (VCB-17):** Das Eingabefeld parste über `lstrip("-").isdigit()` → „-5" ging als gültige (negative) Bindung durch. Neuer Helfer `_parse_function_id` akzeptiert nur nicht-negative Ganzzahlen (leer/negativ → None), symmetrisch zu `VCEffectColors`. `src/ui/virtualconsole/vc_color.py`.
- **Slider-Effekt-Master: function_id nicht mehr verworfen (VCB-20):** `VCSlider._effect_targets`/`_autostart_targets` ignorierten das einzelne `function_id`, sobald `function_ids` gesetzt war (anders als `_all_target_fids()`, das beide vereint). Beide nutzen jetzt `_all_target_fids()` → die Einzel-Bindung geht nicht verloren. `src/ui/virtualconsole/vc_slider.py`.
- **MIDI-Teach: Sentinel statt None beim Entfernen (VCB-24):** `VCWidget._teach_midi` übergab beim Löschen einer Bindung `None` als `msg_type`; die Overrides räumen zwar am `data1<0`-Guard, aber ein None-`msg_type` ist eine stille Falle für künftige/`super()`-aufrufende Overrides. Jetzt Sentinel `"none"`. `src/ui/virtualconsole/vc_widget.py`.
- **Effekt-Param-Spec robust (VCB-25):** `effect_live._spec_for` fing eine Exception aus `fn.list_params()` nicht ab → konnte VC-Parametersteuerungen mitreißen. Jetzt `try/except` → `None`. `src/core/engine/effect_live.py`.
- **VC-Farbliste: Klick trifft den sichtbaren Swatch (VCB-26):** `VCColorList._hit_swatch` nutzte eine gleichförmige Float-Division, während `paintEvent` pro Swatch `int(round(x))` rundet → Klicks an Rändern trafen den Nachbar-Swatch. Der Hit-Test spiegelt jetzt exakt die gerundeten Paint-Grenzen. `src/ui/virtualconsole/vc_color_list.py`.
- **Speed-Dial: BPM robust deserialisiert (VCB-28):** `VCSpeedDial.apply_dict` wandelt `_bpm` jetzt defensiv nach `float` (ältere Shows konnten den Wert als String speichern → späterer `TypeError` in der Dial-Arithmetik). `src/ui/virtualconsole/vc_speedial.py`.
- **Live-Controls: Button-Reihe dynamisch positioniert (VCB-29):** `VCCanvas.add_live_controls` legte die Aktions-Buttons fix 200 px unter die Fader → Überlappung (hohe Fader) bzw. Leerraum (kleine Stepper, 72 px). Jetzt unter die tatsächliche Höhe der erzeugten Regler. `src/ui/virtualconsole/vc_canvas.py`.
- **Widget-Typ-Tausch: kein Phantom-Undo bei Fehlschlag (VCB-30):** `VCCanvas.replace_widget_type` pushte den Undo-Snapshot vor `_add_widget`; schlug das Anlegen fehl (`new is None`), blieb ein leerer Undo-Schritt zurück. Der Snapshot wird jetzt erst nach erfolgreichem `_add_widget` gepusht. `src/ui/virtualconsole/vc_canvas.py`.
- **VC-Button: kein stale snap_id beim Action-Wechsel (VCB-31):** `apply()` leerte beim Wechsel weg von `LIBRARY_SNAP` nur `snap_ids`, nicht `snap_id` → eine Phantom-Snap-ID wanderte in `to_dict` (Show-Korruption). Neuer Helfer `_snap_binding_for_action` leitet beide zentral aus der Aktion ab. `src/ui/virtualconsole/vc_button.py`.

#### Verbessert (VC-Audit)

- **Tempo-Toggle-Pads zeigen ihren Zustand (VCI-01):** `FREEZE`/`AUTO_SYNC`/`BPM_MODE_TOGGLE`-Buttons bekommen — wie `AUDIO_BPM` — einen Aktiv-Indikator (amber Rahmen + aufgehellter Hintergrund), abgeleitet aus `is_frozen()`/`auto_sync`/`mode==MANUAL`. `src/ui/virtualconsole/vc_button.py`.
- **Assign-Modus-Hinweise vervollständigt (VCI-02):** Der Canvas zeigt jetzt auch im **Funktions-** und **Bibliothek-Snap-Assign** einen Overlay-Hinweis („Klicke einen Button an…"), bisher nur bei MIDI-Learn/Snapshot. `src/ui/virtualconsole/vc_canvas.py`.
- **`normalize_color_target` meldet Unbekanntes (VCI-03):** ein nicht auflösbarer Ziel-String wird jetzt geloggt (statt still tote Kachel) und fällt sicher auf den Default-RGB-Pfad. `src/ui/virtualconsole/vc_color.py`.
- **Encoder `midi_mode` validiert (VCI-04):** ein korrupter/zukünftiger Wert fällt auf `RELATIVE` zurück statt undefiniertes Verhalten zu aktivieren. `src/ui/virtualconsole/vc_encoder.py`.
- **Slider: unbekannter Modus sichtbar (VCI-05):** `apply_dict` meldet einen unbekannten `mode` und fällt auf `LEVEL` zurück, statt ein wirkungsloses Widget zu erzeugen. `src/ui/virtualconsole/vc_slider.py`.
- **`mappable_param_choices` konsistent (VCI-06):** schließt `tempo_multiplier`/`phase_offset` aus (haben dedizierte Tempo-Controls), wie `control_options`. `src/ui/virtualconsole/vc_effect_meta.py`.
- **Toter Code entfernt (VCI-07):** das nie gelesene `VCButton._lp_fired` ist raus. `src/ui/virtualconsole/vc_button.py`.
- **`aspect_caption`: konsistenter Präfix-Check (VCI-08):** `in`-Prüfung nutzt denselben Token (`"Parameter: "`/`"Aktion: "`) wie der Split. `src/ui/virtualconsole/vc_effect_meta.py`.
- **VCColor-Swatch faltet Weiß (VCI-10):** `color()` faltet den W-Kanal additiv in die Anzeige-RGB → reines RGBW-Weiß erscheint im Picker/Swatch nicht mehr schwarz. `src/ui/virtualconsole/vc_color.py`.
- **Kommentar + Guard (VCI-11/VCI-12):** `VCCanvas.to_dict` erklärt das `FindDirectChildrenOnly` (kein Doppel-Serialisieren von Frame-Kindern); `VCWidget._notify_effect_highlight` prüft `_effect_ids_of` explizit per `hasattr`. `src/ui/virtualconsole/vc_canvas.py`, `src/ui/virtualconsole/vc_widget.py`.
- **`snap_ids` auch beim Speichern dedupliziert (VCI-14):** `VCButton.to_dict` entfernt Duplikate + die `snap_id` selbst, konsistent zum Lade-Pfad. `src/ui/virtualconsole/vc_button.py`.
- _Nicht umgesetzt:_ **VCI-09** (gegen den Code als False-Positive verifiziert — `set_param_normalized` hat keine Loop-Closure) und **VCI-13** (bewusst ausgelassen: `_result_for` ist Instanz-Methode mit vielen Test-/internen Callern; ein statischer Umbau wäre unverhältnismäßig riskant für eine vernachlässigbare Einsparung).

### 2026-06-29 — Neu

#### Neu / Hinzugefuegt

- **Cue-Verzögerung pro Attribut jetzt auch beim Ausfaden (ENG-01):** Cues hatten bereits eine Pro-Attribut-Verzögerung beim Hineinfaden (`attr_delays`); neu ist das symmetrische Gegenstück `attr_delays_out` für den Rückwärts-/Ausfade-Pfad (BACK). `CueStack._fade_to` wählt jetzt **richtungsabhängig** Fade-Zeit, Cue-Delay-Basis **und** die Pro-Attribut-Delays: GO nutzt `fade_in`/`delay_in`/`attr_delays`, BACK nutzt `fade_out`/`delay_out`/`attr_delays_out`. Die Attribut-Ebene ergänzt sich damit spiegelbildlich zu den schon vorhandenen Cue-Delays `delay_in`/`delay_out`. Nebenbei behoben: der BACK-Fade nahm bisher fälschlich `delay_in` (statt `delay_out`) als Verzögerungs-Basis. Alt-Shows ohne den neuen Schlüssel verhalten sich unverändert (defensive Deserialisierung). `src/core/engine/cue.py`, `src/core/engine/cue_stack.py`, `tests/test_cue_substack_and_attrdelay.py`.

### 2026-06-28 — Neu

#### Neu / Hinzugefuegt

- **Tempo standardmäßig taktgleich + direkt im Programmer:** Neue RGB-/Dimmer-Matrizen, EFX-Bewegungen, Chaser und Sequenzen folgen standardmäßig dem globalen Tempo-Bus; Auto-Sync ist bei neuen bzw. nicht ausdrücklich anders gespeicherten Shows aktiv. Matrix- und EFX-Programmer zeigen Tempo-Bus, Multiplikator und Phasenversatz direkt. Bewusste Abwahl bleibt über „Frei (nicht taktgebunden)" möglich.
- **Tempo-Bedienfeld jetzt auch im Chaser- und Sequence-Editor:** Beide Editoren bekommen — wie Matrix/EFX — **Tempo-Bus**, **Tempo-Multiplikator (×)** und **Phasenversatz** direkt im Editor. Damit lässt sich pro Chaser/Sequenz bewusst zwischen **beatgenau** (an einen Tempo-Bus gekoppelt) und **Free-Run** (zeitbasierter Crossfade zwischen den Schritten) umschalten. Default neuer Funktionen bleibt „Global". `src/ui/views/chaser_editor.py`, `src/ui/views/sequence_editor.py`, `tests/test_chaser_sequence_tempo_editor.py`.

#### Behoben

- **Speed-Dial „Jetzt synchronisieren" greift auch bei bus-gekoppelten Effekten:** `RgbMatrixInstance.sync_phase()` setzt die Animationsphase (`_step`) jetzt auch im Bus-Zweig auf 0 zurück — vorher übersprang der Bus-Re-Anchor das Reset, sodass bus-synchrone Effekte beim Sync nicht auf den gemeinsamen Startpunkt sprangen. `src/core/engine/rgb_matrix.py`, `tests/test_speed_dial.py`.
- **Chaser crossfadet wieder verlässlich im Free-Run:** Der Render-Probe-Diagnosehelfer (`render_probe.render_diff`) gibt den nur für die Probe gesetzten Tempo (`request_bpm(..., "diag")`) wieder frei, statt ihn in Folge-Tests/-Läufe leaken zu lassen; der Crossfade-Test ist zusätzlich explizit auf Free-Run gepinnt. `src/core/capability/render_probe.py`, `tests/test_chaser_crossfade.py`.
- **Capability-Manifest neu erzeugt:** `docs/capability_manifest.json` + `docs/CAPABILITIES.md` an die geänderte Tempo-Bus-Optionsreihenfolge angeglichen (`tools/gen_capabilities.py`).
- **Fixture-Kopieren überträgt `spider_dual_tilt`:** `_copy_fixture` kopiert das Dual-Tilt-Flag mit (ging beim Kopieren bisher verloren). `src/ui/views/patch_view.py`, `tests/test_patch_copy_offset.py`.

### 2026-06-25 — Neu

#### Neu / Hinzugefuegt

- **ADJ Dotz TPar System in der Fixture-Library:** Das komplette 4-fach RGB-COB-T-Bar-System ist als Builtin-Profil mit allen offiziellen DMX-Modi hinterlegt: **3, 5, 9, 12 und 18 Kanaele**. Die Pixel-Modi steuern alle vier PAR-Koepfe einzeln; Vollmodi enthalten zusaetzlich Farbmakros/Programme, Master-Dimmer/Programm-Speed, Strobe, Dimmerkurven und die zwei schaltbaren Zusatzlicht-Ausgaenge. Bestehende Fixture-Datenbanken werden durch `ensure_builtins()` idempotent nachgeruestet. `src/core/database/fixture_db.py`, `tests/test_adj_dotz_tpar_profile.py`.

- **ADJ Flat Par QWH12X in der Fixture-Library:** Der 12×5 W RGBW-PAR von ADJ (Art.-Nr. 1226100244) ist jetzt als Builtin-Profil hinterlegt. DMX-Layout faithful aus dem ADJ-Handbuch der baugleichen QA12X-Serie (gleiche Platine, Amber→Weiß) verifiziert. Modelliert sind die für die Software-Farbmischung nutzbaren Direkt-RGBW-Modi: **4-Kanal** (RGBW), **5-Kanal** (RGBW+Dimmer), **7-Kanal** (RGBW+Dimmer+Strobe+Farb-Makros) und **8-Kanal Voll** (zusätzlich Modus-Wahl + Programme). Strobe 0–15 = aus (Dauerlicht, kind `open`), 16–255 = langsam→schnell; 16 Farb-Makros als `color_wheel`-Slots → Farbrad-Kacheln im Programmer. Registriert in `_seed()` und `ensure_builtins()` (rüstet bestehende DBs idempotent nach). `src/core/database/fixture_db.py`, `tests/test_adj_flatpar_profile.py`.

#### Behoben

- **Solo-Frame schaltet wirklich auf genau einen aktiven Button um:** Der Container wertet nicht mehr nur den kurzzeitigen Tastendruck (`_pressed`) aus, sondern deaktiviert laufende Funktions-Toggles und aktive Bibliothek-Snaps gezielt. Beim Wechsel Rot → Grün wird Rot sofort beendet/zurückgenommen und nur Grün bleibt aktiv; ein erneuter Druck auf Grün schaltet es weiterhin aus. Gilt zentral für alle Shows, Banks sowie Maus-, MIDI- und Tastaturauslösung. Multi-Effekt-Buttons werden vollständig gestoppt. `src/ui/virtualconsole/vc_button.py`, `src/ui/virtualconsole/vc_frame.py`, `tests/test_vc_frame_solo.py`.

### 2026-06-24 — Neu

#### Neu / Hinzugefuegt

- **Dimmer-Sequenz für den Dimmer-Chase (ENG-08):** Ein Dimmer-Chase kann jetzt durch **explizite Dimmerwerte** (z. B. 255, 50, 100) schalten — pro Runde die nächste Stufe, genau wie die Color-Sequence pro Runde die Farbe wechselt. Neue Engine-Klasse `DimmerSequence` (Liste `[level 0–255, an/aus]`, `active_index`, `enabled_levels/next/prev/toggle/move`), eine Checkbox „Dimmer pro Runde wechseln" (`dimmer_cycle`) mit `dimmer_order` (normal/random/pingpong) + `dimmer_interval`, und ein neues Graustufen-Widget `DimmerSequenceField` (Popout, Eingabe 0–255) in der Farben-Gruppe — nur beim Dimmer-Chase sichtbar; bei aktiver Sequenz wird der feste Min/Max-Bereich ausgeblendet. Im Cycle-Modus werden die Stufen **direkt** auf den Dimmer geschrieben (kein Min/Max-Remap, kein Doppel-Dimmen); ohne Cycle bleibt exakt das alte Verhalten → abwärtskompatibel. Persistenz über `dimmer_sequence`/`dimmer_active`. `src/core/engine/rgb_matrix.py`, `src/core/engine/rgb_matrix_meta.py`, `src/ui/widgets/dimmer_sequence_editor.py`, `src/ui/views/rgb_matrix_view.py`, `tests/test_matrix_dimmer_sequence.py` (PR #60).

#### Geaendert

- **„Farbe pro Runde wechseln" in die Farben-Gruppe (UI-12):** Die `color_cycle`-Checkbox sitzt jetzt fest direkt beim Color-Sequence-Editor (statt ganz unten im dynamischen Param-Block „Bewegung & Parameter") und ist auf Farb-Styles (RGB/RGBW) gegated. Wirkt identisch im eingebetteten Tab und im „großen Fenster". `src/ui/views/rgb_matrix_view.py`, `tests/test_matrix_meta_view.py` (PR #60).

### 2026-06-23 — Neu

#### Neu / Hinzugefuegt

- **Preset-Browser: Paletten & Gruppen durchsuchen (UI-01):** Neuer Sub-Tab „Preset-Browser" in der Programmer-Sektion mit einem Suchfeld über **Paletten UND Fixture-Gruppen** zugleich. Live-Filter über Name, Typ (Color/Position/…), Ordner und Tags (mehrere Begriffe = UND, case-insensitiv); Doppelklick oder Enter wendet den Treffer an — eine Palette geht in den Programmer (aktuelle Auswahl, sonst alle Geräte), eine Gruppe wählt ihre Fixtures aus. Die Filterlogik liegt Qt-frei in `preset_search.py` und ist mit 14 Tests headless abgedeckt. `src/core/engine/preset_search.py`, `src/core/app_state.py` (`list_fixture_groups`), `src/ui/views/preset_browser_view.py`, `src/ui/main_window.py`, `tests/test_preset_browser.py`.

### 2026-06-22 — Fixes

#### Behoben

- **Dimmer-Matrix wirkt ohne Master-Hochziehen (ENG-02):** Treibt eine Funktion (Dimmer-Matrix/EFX) einen Intensitaets-/Dimmer-Kanal DIREKT, besitzt sie ihn jetzt wert-unabhaengig (Write-Log) — der per-Fixture Programmer-Intensity-Wert greift nicht mehr ein. Vorher wurde eine reine Dimmer-Matrix unsichtbar, sobald der Programmer (oft beim Auswaehlen auto-gesetzt) `intensity=0` hielt, und ein hochgezogener Master invertierte den Chase (gerade dunkle Pixel leuchteten voll). „Aktiver Tab gewinnt": nur wenn der **Intensity-Tab** aktiv UND die Lampe **selektiert** ist, gewinnt die manuelle Intensitaet absolut. Globaler Submaster/Grand-Master/Fixture-Dimmer bleiben echte Master; reine Farb-Effekte unveraendert (EE-02-Multiply dort erhalten). Bewusste Semantik-Aenderung: das alte EE-02 „Programmer-Dimmer multipliziert einen intensitaets-treibenden Effekt" entfaellt zugunsten der Tab-Regel. `src/core/app_state.py`, `src/ui/views/programmer_view.py`, `tests/test_matrix_dimmer_master.py`, `tests/test_dimmer_master.py` (PR #9).
- **EFX-Tab: „▶ Start" lief stumm ohne Geräte (UI-04):** Eine im Standalone-EFX-Tab neu angelegte Bewegung (z. B. Kreis/Circle) hatte keine Geräte zugewiesen; `EfxInstance.write()` bricht bei leerer Fixture-Liste sofort ab → **null DMX-Output, nichts im Simple Desk, keine Bewegung** (Symptom in „Test 1 2 3": Circle erzeugte keine Ausgabe). Neu: `_add_efx` befüllt eine frische Bewegung sofort mit Geräten (aktuelle Auswahl, sonst alle gepatchten Movingheads mit Pan+Tilt bzw. Dual-Tilt-Spider), und `_start_efx` weist vor dem Start sicherheitshalber nach; sind gar keine beweglichen Geräte gepatcht/ausgewählt, erscheint eine klare Warnung statt eines stummen No-Ops. `src/ui/views/efx_view.py`, `tests/test_efx_autoassign.py`.

### 2026-06-21 — Grosses Update: zentraler BPM-Leader & Tempo-Buses, BPM-Generator mit Beatgrid, geführte Virtuelle Konsole, Effekt-Sync & Multikopf, Capability-Validierung, neues Anleitungs-Kit

Dieses Update überarbeitet das Tempo/BPM-Subsystem von Grund auf (zentraler Leader, Tempo-Buses, Offline-Beatgrid-Analyse), baut die Virtuelle Konsole zu einem geführten Drag&Drop-Werkzeug mit Multi-Effekt-Steuerung aus und führt eine neue Capability-Ebene ein, die Shows vor stillen Lade-Fehlern schützt. Dazu kommen tiefgreifende Engine-Erweiterungen (Tempo-Sync, Layer-Priorität, Hüllkurven, Mehrkopf-Geräte), zahlreiche Robustheits- und Touch-Fixes sowie ein komplett neues bebildertes Anleitungs-Kit.

#### Neu / Hinzugefuegt

- **Zentraler BPM-Leader mit AUTO/MANUAL und Live-Monitor:** Der BPMManager ist jetzt ein zentraler Tempo-Leader mit klarer Quellen-Praezedenz — MANUAL (Tap/Nudge/Fader/Eingabe) und ein Lock blocken alles, im AUTO-Modus treibt der Audio-Detektor die BPM (OS2L/Datei nur als Fallback). Neuer Tab mit Live-Monitor (grosse BPM, Takt 1-2-3-4, Beat-Flash, Confidence, Spektrum, aktive Quelle) und Einstellungen. `src/core/engine/bpm_manager.py`, `src/ui/views/bpm_manager_view.py`, `src/core/audio/bpm_settings.py`.
- **BPM-Generator: ganzes Lied offline analysieren:** Neuer Generator-Tab analysiert komplette Dateien (MP3/M4A/FLAC/OGG/WAV via Qt-Decoder) zu einer zeitgestuetzten BPM-Kurve und einem phasen-genauen Beatgrid mit Downbeats. Auswaehlbare Engines (eingebaut/numpy, librosa, Beat This!) degradieren sauber, wenn nicht installiert; Ergebnis als BPM-Quelle nutzbar oder als JSON exportierbar. `src/ui/views/bpm_generator_view.py`, `src/core/audio/offline_timeline.py`, `src/core/audio/analysis_engines.py`.
- **Beatgrid-Editor mit Vorhoeren und Ordner-Stapelanalyse:** Das erkannte Grid laesst sich wie bei VirtualDJ/Serato korrigieren (½×/2×, Beats nudgen, Downbeat per Klick setzen); "Vorhoeren" spielt den Song mit Metronom-Klick auf jedem Beat. Eine Stapelanalyse verarbeitet ganze Ordner und legt die Ergebnisse im Cache ab. `src/ui/views/bpm_generator_view.py`, `src/core/audio/bpm_cache.py`.
- **Taktgenaue Beat-Wiedergabe aus dem Beatgrid:** Spielt der In-App-Player einen analysierten Track, feuert ein neuer Grid-Treiber (15-ms-Timer, Wall-Clock-interpoliert) taktgenaue Beats samt echten Downbeats; der globale Timer pausiert dann (genau eine Beat-Quelle). MANUAL/Lock und Live-Audio behalten Vorrang; per `phase_accurate_beats` abschaltbar. `src/core/audio/music_show.py`, `src/core/engine/bpm_manager.py`.
- **Genre-Presets fuer treffsichere BPM-Erkennung:** Pro Stil (House, Techno, Trance, Hardstyle, Frenchcore, DnB, Dubstep, Trap, Pop, Allgemein) ein Parametersatz aus Tempo-Fenster, Tempo-Prior, Empfindlichkeit, Glaettung und Taktart — behebt den haeufigsten Fehler (75 statt 150 BPM). Wirkt auf Live-Detektor und Offline-Generator. `src/core/audio/genre_presets.py`, `src/core/audio/offline_timeline.py`.
- **Tempo-Bus-System mit Master/Sub und Grand-Master:** Benannte, unabhaengige Tempo-Uhren liefern eine kontinuierliche Beat-Position (statt nur diskreter Beats), sodass Effekte phasenkohaerent koppeln (×2/×½). Default-Bus spiegelt den globalen Leader, feste Buses A/B/C/D fuer die VC, Master/Sub-Hierarchie, Grand-Master-Override mit eigenem Tap, Auto-Sync, Freeze-Toggle und Persistenz in der Show. `src/core/engine/tempo_bus.py`, `src/ui/views/bpm_manager_view.py`.
- **BPM aus eingebetteten Datei-Tags (ID3/MP4):** Neuer Tag-Reader (reines stdlib) liest die gespeicherte BPM aus ID3v2-TBPM bzw. iTunes-tmpo-Atom; in der Music View per Knopf "BPM aus Datei-Tags" nachziehbar und mit Etikett markiert. Greift nicht in den BPM-Manager ein. `src/core/audio/tag_reader.py`, `src/core/audio/media_player.py`, `src/ui/views/music_view.py`.
- **Per-Song-Auto-Show und Spektrum in der Music View:** Jedem Lied lassen sich Funktionen zuweisen, die beim Abspielen automatisch starten und bei Track-/Pause-Wechsel sauber getauscht werden (neue Spalte "Auto-Show"); die Now-Playing-Box zeigt ein 8-Band-Spektrum/VU. `src/ui/views/music_view.py`, `src/core/audio/music_show.py`, `src/ui/views/spectrum_bars.py`.
- **Konfigurierbares Takt-Raster:** Der BPMManager kennt nun `beats_per_bar` (1..64) mit Downbeat-/Bar-Events (`subscribe_bar`) und eine `subdivision` (1..16 Sub-Ticks pro Beat, opt-in `subscribe_tick`) fuer feinere Effekt-Aufloesung, plus Helfer `is_downbeat()`/`beat_phase_in_bar()`. `src/core/engine/bpm_manager.py`, `src/core/audio/bpm_settings.py`.
- **Tempo-Bus-Synchronisation fuer alle zeitbasierten Effekte:** EFX, RGB-Matrix, Chaser und Sequence koennen an einen gemeinsamen Bus (Global/A-D) gekoppelt werden und leiten ihre Phase/ihr Stepping aus der Bus-Position ab (`effect_pos = (bus.position - anchor) × tempo_multiplier + phase_offset`) statt aus dt zu akkumulieren — phasenkohaerent, mit freien Verhaeltnissen (×0.0625..16) und Beat-Versatz. "Sync" re-ankert eine sync_group, Freeze (F5) haelt die Position an. `src/core/engine/function.py`, `src/core/engine/efx.py`, `src/core/engine/rgb_matrix.py`, `src/core/engine/chaser.py`, `src/core/engine/sequence.py`.
- **Layer-Prioritaet beim Engine-Merge:** Funktionen haben ein neues Feld `priority` — hoehere Prioritaet tickt zuletzt und gewinnt bei Kanal-Ueberschneidung (LTP). Der FunctionManager sortiert stabil und erfasst geschriebene Kanaele ueber ein Write-Log (statt Wert-Diff), damit eine hoeher priorisierte Funktion auch mit identischem Rohwert gewinnt. Einstellbar im EFX- und Matrix-Editor. `src/core/engine/function.py`, `src/core/engine/function_manager.py`.
- **Ein-/Ausblend-Huellkurve (Fade) fuer Effekte:** Optionale `env_fade_in`/`env_fade_out` plus Kurvenform (`env_curve`: linear/scurve/ease/snap) wirken als Output-Multiplikator ueber ALLE Kanaele; beim Stoppen blendet die Funktion aus (release) statt hart zu stoppen, Blackout bleibt Sofort-Stopp. `src/core/engine/function.py`, `src/core/engine/function_manager.py`.
- **Neuer Matrix-Algorithmus "Schachbrett" (Checker):** Benachbarte Zellen abwechselnd Farbe A/B mit einstellbarer Kachelgroesse (`tile`) und optionalem Umschalten pro Beat (`blink`). `src/core/engine/rgb_matrix.py`, `src/core/engine/rgb_matrix_meta.py`.
- **Sequence-in-Sequence und Pro-Attribut-Verzoegerung in Cues:** Cues koennen ueber `sub_stack_ref`/`sub_stack_mode` eine andere Cueliste mitlaufen lassen (LTP-Merge, zyklensicher), und ueber `attr_delays` einzelne Attribute zusaetzlich zeitversetzt einfaden (`_blend_per_attr`). `src/core/engine/cue.py`, `src/core/engine/cue_stack.py`.
- **Neuer Snap-Editor:** Bibliotheks-Snaps lassen sich tabellarisch bearbeiten (aufgeloester Kanalname + DMX-Adresse, Werte 0..255 aendern, Eintraege entfernen, "Vorschau senden") ueber die neue SnapLibrary-API `set_snap_value`/`remove_snap_attr`/`set_snap_values`. `src/ui/views/snap_editor.py`, `src/core/engine/snap_library.py`.
- **Fade-Kurven-Bibliotheks-Ansicht:** Die show-weite Kurven-Bibliothek erhaelt eine eigene Verwaltung (Liste mit Vorschau, Neu/Bearbeiten/Duplizieren/Umbenennen/Loeschen); Presets sind schreibgeschuetzt, ein Edit legt eine User-Kurve an. `src/ui/views/curve_library_view.py`.
- **Geführter Smart-Drop in der VC statt stummem Toggle-Button:** Zieht man einen Effekt auf das Canvas, oeffnet eine Ankreuz-Karte (VCDropPanel) mit je einer Checkbox pro steuerbarem Aspekt (An/Aus, Tempo, Helligkeit, Farben, Bewegung, Tempo-Bus, Parameter, Aktionen). Mehrere Haken erzeugen mehrere vorverdrahtete Widgets in EINEM Undo-Schritt; die sinnvollen Aspekte leitet `vc_effect_meta` Qt-frei aus den Live-Faehigkeiten ab. `src/ui/virtualconsole/vc_drop_panel.py`, `src/ui/virtualconsole/vc_effect_meta.py`, `src/ui/virtualconsole/vc_canvas.py`.
- **Grafische Widget-Galerie und Widget-Typ-Tausch:** Wo mehrere Bedien-Elemente passen, zeigt eine Kachel-Galerie mit gemalter Vorschau (VCWidgetGallery) die Auswahl; ueber "↔ Widget ändern…" laesst sich der Typ eines vorhandenen Widgets bindungserhaltend tauschen (function_id(s), param_key(s), Caption, Position bleiben). `src/ui/virtualconsole/vc_widget_gallery.py`, `src/ui/virtualconsole/vc_widget.py`.
- **Undo/Redo fuer das Konsolen-Layout:** Hinzufuegen, Loeschen, Verschieben, Skalieren und Eigenschafts-Aenderungen von VC-Widgets sind rueckgaengig machbar (Snapshot-Verlauf, max. 50), mit Toolbar-Pfeilen und Strg+Z / Strg+Y / Strg+Umschalt+Z; Kit-Aufbauten zaehlen als ein Undo. `src/ui/virtualconsole/vc_canvas.py`, `src/ui/views/virtual_console_view.py`.
- **Doppelbelegungs-Schutz beim Drop auf belegte Regler:** Zieht man einen Effekt auf einen schon belegten Fader/Speed-Rad, erscheint eine Erklaer-Karte (VCConflictCard) mit drei Wegen: "Ersetzen", "Dazu koppeln" oder "Neues Widget daneben". `src/ui/virtualconsole/vc_conflict_card.py`, `src/ui/virtualconsole/vc_canvas.py`.
- **Multi-Effekt-Kopplung an einem Regler:** Fader, Speed-Rad, Encoder, Stepper und Buttons koennen mehrere Effekte gleichzeitig steuern (`function_ids`), je gekoppeltem Effekt mit eigenem Parameter (`param_keys_per_id`); eine nach Namen gefuehrte "Steuert"-Liste (TargetListEditor) ersetzt die rohen ID-Felder. `src/ui/virtualconsole/target_list_editor.py`, `src/ui/virtualconsole/vc_slider.py`, `src/ui/virtualconsole/vc_speedial.py`.
- **Effekt-Gruppen-Hervorhebung (oranger Glow):** Im Bearbeiten-Modus leuchten alle Widgets, die denselben Effekt steuern, gemeinsam in Amber auf — sichtbar "was beeinflusst diesen Effekt"; Container leuchten als Einheit, im Betrieb ist es aus. `src/ui/virtualconsole/vc_widget.py`, `src/ui/virtualconsole/vc_canvas.py`, `src/ui/virtualconsole/vc_frame.py`.
- **Neue VC-Bedien-Widgets — Stepper, Effekt-Farben, Effekt-Vorschau:** VCStepper (+/− fuer ganzzahlige Parameter wie Laeufer-Anzahl, mit relativem MIDI-CC), VCEffectColors (Swatch-Reihe der lebenden ColorSequence, Klick = Farbe waehlen, Rechtsklick = Slot an/aus) und VCEffectDisplay (Live-Pixel-Render des gebundenen Effekts). `src/ui/virtualconsole/vc_stepper.py`, `src/ui/virtualconsole/vc_effect_colors.py`, `src/ui/virtualconsole/vc_effect_display.py`.
- **Beweglicher Effekt-Editor-Container mit Live-Vorschau:** Beim Smart-Drop kann "Als Effekt-Box gruppieren" gewaehlt werden — alle erzeugten Regler landen in einer verschiebbaren VCEffectEditor-Box mit eingebetteter Vorschau und automatisch beschrifteten Reglern (Speed/Intensität/Size). `src/ui/virtualconsole/vc_effect_editor.py`, `src/ui/virtualconsole/vc_frame.py`.
- **VC-Tempo-Sync: Bus-Auswahl, BPM-Anzeige und Speed-Knoten:** VCBusSelector schaltet den aktiven Bus (A/B/C/D) scharf und zeigt die Bus-BPM, VCBpmDisplay zeigt globale oder Bus-BPM gross plus Quelle/Modus; das Speed-Rad ist ein vollwertiger Speed-Knoten mit QLC+-Paritaet (Master oder Sub mit Faktor ¼..×4, Sync/Downbeat, einstellbarem Erscheinungsbild). `src/ui/virtualconsole/vc_bus_selector.py`, `src/ui/virtualconsole/vc_bpm_display.py`, `src/ui/virtualconsole/vc_speedial.py`.
- **Neue Button- und Fader-Aktionen fuer Tempo und Show-Steuerung:** VCButton kennt BPM ±1 nudgen, AUTO/MANUAL umschalten, Tap/Sync/Arm pro Bus sowie globale Aktionen "Alles Weiß", "Freeze", "Effekte stoppen" und "Auto-Sync"; der BPM-Fader erzwingt beim Ziehen MANUAL, ein neuer Modus "Tempo-Bus (BPM)" steuert die BPM eines benannten Bus. `src/ui/virtualconsole/vc_button.py`, `src/ui/virtualconsole/vc_slider.py`.
- **Live-Mini-Editor und Pfad-Zeichnen:** Langes Druecken auf einen Effekt-Button im Live-Modus oeffnet einen kompakten Editor (VCLiveEditor) mit DEFERRED APPLY (Aenderungen wirken erst beim "Anwenden"); das XY-Feld hat einen "Pfad"-Modus, der eine live gezeichnete Bahn als Custom-EfxPath auf den Ziel-EFX legt. `src/ui/virtualconsole/vc_live_editor.py`, `src/ui/virtualconsole/vc_xypad.py`.
- **Capability-Validierung gegen stille Lade-Fehler:** Neue Ebene `src/core/capability/` reflektiert die wirklich existierenden Bausteine (Widget-Typen, Matrix-/EFX-Algorithmen, Param-Keys, Funktionstypen, Carousel-Pattern, Kurven) direkt aus dem Code und lintet ein show.json dagegen — jeder Punkt, den der tolerante Loader sonst verschluckt, wird als Finding mit difflib-Vorschlag und echter file:line laut. `assert_lshow` wirft vor `save_show`, `validate_show_live` prueft bindungsgenau gegen die laufende Engine. `src/core/capability/reflect.py`, `src/core/capability/validate.py`, `src/core/capability/render_probe.py`.
- **Strict-Modus fuer Show-Laden (LIGHTOS_STRICT):** Opt-in `src/core/strict.py` — mit gesetzter Umgebungsvariable re-raisen Loader und FunctionManager kaputte Subsysteme/Funktionen mit vollem Traceback statt sie still zu ueberspringen; standardmaessig aus. `src/core/strict.py`.
- **ShowBuilder-DSL: Shows per Skript bauen, die nur echte Bausteine nutzen koennen:** Neues Paket `src/core/show/showbuilder/` prueft jeden Algorithmus/Action/Param/Style/Fixture at call time gegen die reflektierten Capabilities und wirft bei Halluzination sofort BuildError (mit "meintest du"-Vorschlag); Funktions-Builder geben Handles zurueck, die man direkt an Widget-Builder uebergibt, sodass ein Widget nie an eine nicht-existente Funktion binden kann. `save()` validiert doppelt (statischer + Live-Lint). `src/core/show/showbuilder/builder.py`, `src/core/show/showbuilder/errors.py`.
- **Strikte Trennung Farbe/Dimmer als Show-Option (implicit_brightness):** Neues Flag (Default True) — True setzt eine aktive Farbe ohne getriebenen Dimmer automatisch auf voll (Alt-Verhalten), False haelt reine Farbe dunkel, Helligkeit kommt nur aus Dimmer-Effekten. Wird in `_render_frame` ausgewertet und mit der Show gespeichert. `src/core/app_state.py`, `src/core/show/show_file.py`.
- **Mehrkopf-Geraete (Spider) im Programmer einzeln ansteuerbar:** `set_programmer_value`/`get_programmer_value` akzeptieren jetzt `head>0` und adressieren ueber `attr#N` das N-te Vorkommen eines Attributs (z.B. die 2. Tilt-Bank eines Spiders); head=0 bleibt byte-genau, nicht gesetzte Koepfe spiegeln Kopf 0. `src/core/app_state.py`.
- **BPM-Sektion mit AUTO/MANUAL/Lock-Badge in der Top-Bar:** Neue Hauptsektion "BPM" (Tabs Manager + Generator); die Top-Bar zeigt ein klickbares Modus-Badge, Modus-/Quellenwechsel werden thread-sicher aus dem Audio-Thread in die UI marshallt, AUTO ist per `bpm_settings.boot()` standardmaessig an. `src/ui/main_window.py`, `src/core/midi/apc_mk2_feedback.py`.
- **DMX-Monitor zeigt Kanalfunktion:** Gepatchte Zellen toenen dezent in der Kanal-Funktionsfarbe und zeigen ein Geraete-Kuerzel + Kanal-Funktion (z.B. "PAR 1 R") plus Tooltip mit vollem Namen und aktuellem Wert. `src/ui/views/dmx_monitor_view.py`.
- **Quick-Rec und Kurven-Tab im Playback-View:** Ein "Quick-Rec"-Button nimmt dialogfrei sofort als neue Cue auf der aktuellen Cueliste auf (Auto-Nummer/-Label); die Playback-Sektion bekam zusaetzlich einen "Kurven"-Tab. `src/ui/views/playback_view.py`, `src/ui/main_window.py`.
- **Programmer: Gruppensuche und direkter Sprung in die Matrix-Ansicht:** Eine Such-/Filterleiste filtert die Gruppenliste nach Name/Ordner (flache Trefferliste), ein Gruppenklick springt direkt in den Matrix-Tab; dieselbe Suchleiste kam in den Paletten-Editor. `src/ui/views/programmer_view.py`, `src/ui/views/palette_view.py`.
- **Effekt-Assistent: neue Presets, Gruppen-Schnellauswahl und Farbverlaeufe:** Vier neue Presets (Wipe, Komet, Random-Strobe, VU-Meter), additive Gruppen-Buttons und optionale Farb-Zwischenstufen (N interpolierte Zwischenfarben) fuer sanfte Verlaeufe; die Mini-Vorschau passt ihr Raster an die echte Geraetegeometrie an. `src/ui/widgets/effect_wizard.py`, `src/ui/widgets/effect_mini_preview.py`.
- **Umbrechendes FlowLayout fuer Toolbars:** Neues `src/ui/widgets/flow_layout.py` — Widgets fliessen links nach rechts und brechen bei Platzmangel sauber um (statt Text-Abschneiden), u.a. fuer die VC-Toolbar bei 200%-Skalierung. `src/ui/widgets/flow_layout.py`.
- **Audio-Quellenwahl Loopback/Mikrofon:** AudioCapture unterstuetzt explizit "loopback" (PC-Wiedergabe) oder "input" (Mikro/Line-In) inkl. Liste echter Eingaenge; der Aufnahme-Loop gibt nach ~2 s durchgehender Fehler auf und meldet `last_error` statt stumm "laeuft" anzuzeigen. `src/core/audio/capture.py`, `src/ui/views/audio_input_view.py`.
- **Auskoppelbare Editoren in grosse, scrollbare Fenster:** Audio-Editor und ColorPicker lassen sich per "Grosses Fenster" in ein eigenes scrollbares Fenster auskoppeln und wieder andocken; jede Farb-Tab-Seite scrollt fuer sich, Zahlenfelder haben eine Mindestbreite (92px). `src/ui/views/audio_editor.py`, `src/ui/widgets/color_picker.py`.

#### Geaendert / Verbessert

- **Genau eine Beat-Quelle statt konkurrierender BPM-Writer:** OS2L, Media-Player und MusicShowDirector setzen die BPM nicht mehr direkt (`set_bpm`), sondern via `request_bpm()` mit Quellen-Kennung — der Leader entscheidet zentral nach Praezedenz; `_sync_emitter()` stellt unter Lock sicher, dass immer genau eine Beat-Quelle laeuft (Timer XOR Audio XOR Grid), der Timer-Thread prueft per Identitaet gegen Doppel-Beats. `src/core/engine/bpm_manager.py`, `src/core/audio/os2l.py`, `src/core/audio/media_player.py`.
- **Art-Net/sACN-Eingang als eigene Render-Schicht (F-20):** Die Empfaenger schreiben ihre gemergten Werte nicht mehr direkt ins Live-Universe (das ueberschrieb der Renderer auf gepatchten Kanaelen), sondern via `apply_input_merge` in einen eigenen Puffer; `_render_frame` mischt diesen pro Frame je Universe mit dem konfigurierten Modus (HTP/LTP/REPLACE), nach dem Dimmer-Master und vor Simple Desk. `src/core/app_state.py`, `src/core/dmx/artnet_input.py`, `src/core/dmx/sacn_input.py`.
- **Tempo-Buses mit der Show gespeichert und pro Frame fortgeschrieben:** `save_show`/`load_show`/`reset_show` sichern benannte Buses und den Grandmaster (Default-Bus nicht persistiert, alt-kompatibel); `_render_frame` schreibt die Buses einmal pro Frame (`advance_frame`) fort, bevor Funktionen rendern, sodass alle beat-synchronen Effekte im selben Frame dieselbe Bus-Position lesen. `src/core/show/show_file.py`, `src/core/app_state.py`.
- **Tolerantes Show-Laden mit optionalem Strict-Modus:** Alle strukturellen Schluck-Punkte laufen jetzt ueber `_lenient()` — standardmaessig tolerant, im Strict-Modus laut re-raised; eine einzelne kaputte Cueliste verwirft nicht mehr ALLE Cuelisten, die Show-DB ist per `LIGHTOS_SHOW_DB` umlenkbar. `src/core/show/show_file.py`, `src/core/app_state.py`.
- **RGBW-Matrix: echtes Weiss statt doppeltem Weissanteil:** Bei Style RGBW wird der Weissanteil `cw=min(r,g,b)` automatisch auf den W-Kanal gelegt und vom RGB-Anteil abgezogen — pures Weiss laeuft rein ueber den weissen Chip; der manuelle `white_amount`-Slider entfaellt. Carousel macht dieselbe Subtraktion (`adapt_color_payload`). `src/core/engine/rgb_matrix.py`, `src/core/engine/carousel.py`.
- **EFX: gegenphasiger 2. Kopf und Mehrkopf-Kanalverteilung:** Fixtures mit zwei Tilt-Kanaelen (Spider) schwenken den zweiten Kopf gegenphasig (`tilt#1 = 255-tilt`), sodass die Bars zu-/voneinander weg fahren; generell verteilt der EFX-Output Werte korrekt auf mehrfach vorhandene Attribute (`attr`, `attr#1`, `attr#2`). `src/core/engine/efx.py`.
- **QXF-Import deutlich genauer:** Der QLC+-Importer kennt viele weitere Channel-Presets (Fine als raw, CMY, HSV, CTO/CTB, Zoom/Focus/Iris-Richtungen, Speed-Varianten), vergibt jedem Capability-Bereich ein maschinenlesbares `kind` (open/closed/strobe/color/gobo/shake/rotate/reset), setzt sinnvolle Defaults (Pan/Tilt mittig 128, Shutter auf "offen") und ist ueber savepoint-basierte Nested-Transactions duplikat- und fehlerrobust. `src/core/database/qxf_import.py`, `src/core/database/fixture_db.py`.
- **Editoren gruppiert, scrollbar und auskoppelbar:** EFX-, Matrix-, Chaser-, Sequence-, Szenen-, Carousel- und Effekt-Layer-Editor wurden gegen das Platzproblem umgebaut — thematische QGroupBox-Gruppen in EINEM Scrollbereich plus Knopf "Grosses Fenster", der den ganzen Editor auskoppelt. `src/ui/views/rgb_matrix_view.py`, `src/ui/views/efx_view.py`, `src/ui/views/chaser_editor.py`, `src/ui/views/sequence_editor.py`.
- **Matrix-Editor: Folgemodus und Gruppen-Scope:** Beim ersten Wechsel auf den Matrix-Tab leitet sich das Grid sofort aus der aktiven Auswahl/Gruppe ab; die Auto-Zuweisung nutzt bevorzugt `active_scope_fids` und faellt nur ohne Auswahl auf den ganzen Patch zurueck. Beim CHASE-Algorithmus werden Laeufer-Anzahl/After-Fade nur bei `movement=normal` angezeigt. `src/ui/views/rgb_matrix_view.py`, `src/core/engine/rgb_matrix_meta.py`.
- **Sequence-Editor: Schritt-Name statt Roh-Werte:** Die Step-Tabelle zeigt den Step-Namen statt des Roh-Werte-Dumps (Werte im Tooltip und ueber einen "Werte..."-Dialog); der Chaser-Editor bekam einen Inline-Funktions-Picker, der die Selbstreferenz ausschliesst. `src/ui/views/sequence_editor.py`, `src/ui/views/chaser_editor.py`.
- **Color-Chase-Baukasten mit Zielgruppen-Auswahl:** Der Baukasten fragt die Ziel-Gruppe ab ("Alle Fixtures" oder eine Fixture-Gruppe) statt immer ueber alle gepatchten Fixtures zu laufen; die COLORFADE-Matrix wird explizit auf `MatrixStyle.RGB` gesetzt und traegt den Gruppennamen. `src/ui/views/virtual_console_view.py`.
- **Umbrechende VC-Toolbar und entdoppelte Bibliothek-Sidebar:** Die VC-Toolbar nutzt das FlowLayout und bricht bei schmalem Fenster um, mit neuen Schnell-Zugriff-Buttons (Effekt-Farben, Musik, BPM, Tempo-Bus); die Bibliothek-Sidebar unterdrueckt den doppelten Panel-Header. `src/ui/views/virtual_console_view.py`.
- **Snapshot speichern: nur aktive Auswahl und gewaehlte Attribut-Gruppen:** Der Snap-Speicherdialog beruecksichtigt jetzt einen Geraete-Scope (`active_scope_fids`), damit liegengebliebene Programmer-Werte zuvor gewaehlter Gruppen nicht mitgespeichert werden; der Quick-Snapshot fragt ebenfalls die Attribut-Gruppen ab. `src/ui/views/snap_file_panel.py`, `src/ui/main_window.py`.
- **Sub-Cuelisten-Aufloesung nach Show-Laden verdrahtet (F-16):** AppState bietet `_resolve_cue_stack` und `wire_cue_stack_resolvers`, die allen Cuelisten den Sub-Cuelisten-Resolver geben — aufgerufen in `new_cue_stack` und nach jedem `load_show`, sodass Verweise auch nach Reloads gueltig bleiben. `src/core/app_state.py`, `src/core/show/show_file.py`.
- **Visualizer: leere Buehne als einziger Start, nicht-modaler Farb-Picker:** Die fest verdrahteten Buehnen-Presets wurden entfernt — der Visualizer startet immer mit leerer Buehne; der Element-Farbdialog ist jetzt nicht-modal mit Live-Vorschau (Abbrechen stellt die Ausgangsfarbe wieder her). `src/ui/visualizer/stage_scene.html`, `src/ui/visualizer/visualizer_window.py`.
- **Function-Manager: hilfreiche Hinweise statt "Editor kommt bald":** Fuer EFX- und RGB-Matrix-Funktionen zeigt der Function-Manager jetzt konkret, wo sie zu bearbeiten sind (Programmer → Tab EFX bzw. Matrix); der generische Fallback bleibt nur fuer unbekannte Funktionstypen. `src/ui/views/function_manager_view.py`.
- **Stabilere Live-BPM-Erkennung:** Der BeatDetector liefert die BPM aufbereitet — rohe BPM via Median und Ausreisser-Verwerfung ueber ein kurzes Fenster, Oktav-Faltung in die Ziel-Range mit Kontinuitaet (kein Half/Double-Springen) und EMA-Glaettung; neu sind `set_bounds`/`set_smoothing`, eine Confidence-Schaetzung und ein Stille-Reset, der nach ~3 s ohne Beat den Lock verwirft. `src/core/audio/beat_detector.py`.
- **Touch-/Skalierungs-feste Buttons und durchgaengige Umlaut-Beschriftung:** Transport-Buttons und STOP ALL/BLACKOUT nutzen Mindestbreiten statt Festbreiten; Tab-Namen wurden geschaerft und durchgaengig ASCII-Ersatzschreibungen in echte Umlaute korrigiert. `src/ui/views/show_manager_view.py`, `src/ui/main_window.py`, `src/core/sync.py`, `src/core/stage/stage_definition.py`.
- **APC Mini Feedback vereinfacht:** Der nie sinnvoll genutzte `exclude_note`/`include_note`-Mechanismus wurde aus dem Feedback-Loop entfernt; Executor-/Seiten-LEDs werden jetzt unbedingt gesetzt, was eingefrorene LED-Zustaende vermeidet. `src/core/midi/apc_mini_feedback.py`.

#### Behoben

- **Crash beim Laden/Zuruecksetzen von Shows mit Patch (BUG-01):** Beim Bulk-Ersatz des Patches feuerte jedes `clear_patch()`/`add_fixture()` synchron ein `patch_changed`-Event, woraufhin Views re-entrant im inkonsistenten Zustand refreshten und ueber `QListWidget.clear()` eine Access Violation ausloesten. AppState hat jetzt ein `_suppress_emits`-Flag und macht nach dem Umbau EINEN gebuendelten Refresh. `src/core/app_state.py`, `src/core/show/show_file.py`, Test `tests/test_show_file.py`.
- **U-King Spider: zwei separate Tilt-Motoren statt Pan/Tilt:** Das 14-Kanal-Layout (CH1/CH2) ist auf zwei separate Tilt-Motoren (Bar links = Kopf 0, Bar rechts = Kopf 1) umgestellt, da die zwei Lichtleisten getrennt schwenken; aeltere Datenbanken werden ueber die neue `_SPIDER14_SIGNATURE` beim Start in-place migriert (Tippfehler "Großer Straler" → "Großer Strahler" korrigiert). `src/core/database/fixture_db.py`, Test `tests/test_spider_profile.py`.
- **Attribut-Gruppen-Klassifikation aus einer Quelle (Strobe-Fehlbeschriftung, Bug E):** Die Attribut-zu-Gruppe-Zuordnung liegt jetzt zentral in `src/core/attr_groups.py` und wird von Programmer-Tabs und Speichern-Dialog gemeinsam genutzt — vorher fuehrten zwei abweichende Maps dazu, dass ein im Intensity-Tab geschobener Strobe-Kanal beim Speichern faelschlich als "Beam" beschriftet wurde. `src/core/attr_groups.py`, `src/ui/views/programmer_view.py`.
- **EFX-View: Zombie-Sync-Subscriber beseitigt:** Die View abonniert Sync-Events jetzt ueber `subscribe_widget` statt `subscribe`, sodass sich die Handler beim Zerstoeren automatisch abmelden — vorher sammelten sich bei jedem Programmer-Rebuild Zombie-Subscriber an, was jede `FUNCTION_CHANGED`-Aktualisierung mit der Zeit verlangsamte. `src/ui/views/efx_view.py`.
- **Cue-Laden robuster und Draft-Roundtrip erhaelt Basisfelder:** `Cue.from_dict` liest `values`/`attr_delays` defensiv (kaputte Eintraege werden uebersprungen statt die ganze Cuelisten-Sektion zu verlieren); `RgbMatrix.apply_dict` erhaelt nun `priority` und die Huellkurven-Zeiten, die sonst beim Draft-Roundtrip verloren gingen. `src/core/engine/cue.py`, `src/core/engine/rgb_matrix.py`, `src/core/engine/function_manager.py`.
- **VC: robusteres Laden und Migration alter Farb-Ziele:** Beim Laden bricht ein einzelnes defektes Widget nicht mehr das Laden der restlichen Konsole ab (uebersprungen und protokolliert); alte ASCII-geschriebene ColorTarget-Werte (z.B. "hinzufuegen") werden per ASCII-Faltung auf den kanonischen Wert gemappt, sonst fiele die Farb-Kachel still auf den Default zurueck. `src/ui/virtualconsole/vc_canvas.py`, `src/ui/virtualconsole/vc_color.py`.
- **VC: Frame-Delete-Ownership und uebersichtlicher Farb-Dialog:** In einen VCFrame gelegte Widgets gehoeren nun der Box (`delete_requested` korrekt verdrahtet, Entfernen ist undobar) — vorher blieben sie an der Canvas haengen; der Eigenschaften-Dialog des Farb-Widgets gruppiert die vielen Zeilen in einem Scrollbereich und unterstuetzt Mehrkopf-Geraete. `src/ui/virtualconsole/vc_frame.py`, `src/ui/virtualconsole/vc_color.py`.
- **Doppelbelegungs-Fix am Speed-Dial:** Der Konflikt-Schutz behebt nebenbei einen latenten Bug am Speed-Rad, dessen Kopplungs-Rueckgabewert frueher ignoriert wurde. `src/ui/virtualconsole/vc_canvas.py`.
- **Beat-Indikator Off-by-one behoben:** Der manuelle BPM-Dialog nutzt jetzt `set_manual_bpm`/`reset` statt `set_bpm`, und der Beat-Indikator nimmt den Beat-Index direkt aus dem Callback (frueherer Off-by-one im Takt-1-Akzent behoben). `src/ui/main_window.py`.
- **Programmer: Attribut-Tabs scrollen vollstaendig:** Der gesamte Tab-Inhalt (Schnellwahl, Auto-Bar, Position-Tool, Slider) liegt jetzt in einem gemeinsamen aeusseren Scrollbereich — vorher konnten Schnellwahl/Auto-Bar unter `--touch` abgeschnitten werden. `src/ui/views/programmer_view.py`.
- **Touch-Layout-Korrekturen in Auto-Farbwechsel und Geraete-Gruppen:** In der ColorWheelAutoBar liegen Hardware-Rotation und Software-Simulation in eigenen beschrifteten Gruppen mit gestapelten Von/Bis-Combos (QFormLayout); in den Kanal-/Fixture-Gruppen-Views ersetzt eine Mindestbreite plus kompakteres Stylesheet die feste 60px-Apply-Button-Breite. `src/ui/widgets/preset_tile.py`, `src/ui/views/channel_groups_view.py`, `src/ui/views/fixture_group_view.py`.

#### Tests & Werkzeuge

- **Test-Isolation in conftest.py gehaertet:** Tests laufen jetzt gegen eine separate Wegwerf-Show-DB (`LIGHTOS_SHOW_DB` im Temp-Verzeichnis), der Audio-BPM-Autostart ist unterdrueckt (`LIGHTOS_NO_AUDIO_AUTOSTART`), und nach jedem Test werden MIDI-Threads, der globale BPM-Beat-Timer, geleakter Qt-Fokus und offene modale Dialoge abgeraeumt — das beseitigt sporadische native Access-Violations und Hotkey-Flakies. `tests/conftest.py`.
- **CLI-Linter und Manifest-Generator fuer Shows:** `tools/lint_show.py` prueft eine oder mehrere .lshow/show.json gegen die echten Bauteil-Saetze (Glob, `--strict`, Exit-Code 1, CI-tauglich); `tools/gen_capabilities.py` erzeugt `docs/CAPABILITIES.md` + `docs/capability_manifest.json`, ein Diff-Test erzwingt die Uebereinstimmung mit dem reflektierten Code. `tools/lint_show.py`, `tools/gen_capabilities.py`, Tests `tests/test_show_lint.py`, `tests/test_capability_manifest.py`, `tests/test_capability_live.py`.
- **Gemeinsames Build-Boilerplate und Verifikations-Werkzeuge:** `tools/_builder.py` kapselt den Boilerplate der `build_*`-Skripte hinter der ShowBuilder-DSL plus `build_and_verify()` (statischer + Live-Lint, optionaler Render-Smoke); `tools/verify_color_dimmer_separation.py` und `tools/benchmark_universes.py` belegen die Farbe/Dimmer-Trennung bzw. messen die `_render_frame`-Zeit ueber 8/16/32 Universen. `tools/_builder.py`, `tools/verify_color_dimmer_separation.py`, `tools/benchmark_universes.py`, Tests `tests/test_strict_dimmer_render.py`, `tests/test_benchmark_universes.py`.
- **Grossflaechiger Ausbau der Testabdeckung (rund 75 neue Testdateien):** Neue Suiten ueber alle Subsysteme — Tempo/BPM (Beatgrid, Leader, Bus, Grandmaster, Persistenz, Timeline), Virtuelle Konsole (XY-Pad/MIDI, Speed-Node, Effekt-Editor, Undo/Redo, Drop-Panel, Conflict/Swap), Matrix-RGBW-Weiss, Mehrkopf-Spider, ShowBuilder-DSL, Show-Lint, strikter Loader, gruppen-gescopter Save, Offline-BPM-Analyse und APC-Mini-Feedback. `tests/test_showbuilder.py`, `tests/test_tempo_bus.py`, `tests/test_multihead_spider.py`, `tests/test_offline_analysis.py`, `tests/test_carousel_color.py`, `tests/test_implicit_intensity.py`.
- **Bestehende Tests an API-/UI-Aenderungen angeglichen:** `test_matrix_meta_view` prueft jetzt das Auskoppeln/Andocken des ganzen Editors, `test_chaser_live_build` nutzt einen Subset-Check, damit neue Tempo-Bus-Params den Test nicht brechen, und das Spider-Profil-Test prueft zwei eigenstaendige Tilt-Kanaele. `tests/test_matrix_meta_view.py`, `tests/test_chaser_live_build.py`, `tests/test_spider_profile.py`.

#### Dokumentation & Anleitungen

- **Neues bebildertes Anleitungs-Kit (Hardstyle-Show + Event-Demo 2026):** Umfangreiche deutsche, bebilderte Tutorials entlang zweier roter Faeden mit ~20 Themenordnern (Patchen & Gruppen, Farb-/Dimmer-Matrix, Farbchase, EFX, Moving Heads, Spider, Virtuelle Konsole, APC-Mapping, Musik-Sync, Speed-Dial); die README verlinkt das Kit prominent als Einstieg. `docs/ANLEITUNGEN.md`, `docs/ANLEITUNGEN_EVENT_DEMO.md`, `docs/anleitung_patch_gruppen/ANLEITUNG_PATCH_GRUPPEN.md`, `README.md`.
- **Kern-Anleitungen auf die umgebaute Oberflaeche umgeschrieben:** `docs/ANLEITUNG.md` spiegelt die neue UI (8 Hauptsektionen statt 7; EFX/Matrix/Funktionen/Paletten in den Programmer gewandert, "Patchen" nur noch Patch + Fixture-Gruppen); `docs/EFFEKTE.md` aktualisiert Matrix-/EFX-Effekte und Helper-Tab und konsolidiert die RGB-Matrix-Liste auf 18 Algorithmen. `docs/ANLEITUNG.md`, `docs/EFFEKTE.md`.
- **Neue BPM-/Tempo-Dokumentation:** `docs/EFFEKTE.md` (Abschnitt 9) und `docs/ANLEITUNG.md` (Sektion 8) beschreiben das QLC+-artige Tempo-System (Speed-Dial Master/Sub, Grand-Master, mehrere Tempo-Master); dazu Detailguides zu Speed-Dial, BPM-Manager und BPM-Generator (ganzes Lied → Beatgrid, Analyse-Engines, Beatgrid-Editor). `docs/anleitung_speed/ANLEITUNG_SPEED.md`, `docs/anleitung_bpm_manager/ANLEITUNG_BPM_MANAGER.md`, `docs/anleitung_bpm_generator/ANLEITUNG_BPM_GENERATOR.md`.
- **Capability-Manifest als Agenten-Vertrag:** Neues generiertes `docs/CAPABILITIES.md` + `docs/capability_manifest.json` listet alle real existierenden Bausteine (VC-Widget-Typen, ButtonActions, SliderModes, Matrix-/EFX-Algorithmen mit gueltigen Parametern, Tempo-Buses, Kurven) und warnt vor den zwei Asymmetrien beim Laden (falscher Matrix-Algo → still PLAIN; falscher EFX-Algo/Style → ganze Funktion faellt weg). `docs/CAPABILITIES.md`, `docs/capability_manifest.json`.
- **VC-Widget-Referenz und Smart-Build-Flow dokumentiert:** Neue Referenz aller VC-Bau-Elemente (~21 Einzeldateien) sowie Anleitungen zum anfaengerfreundlichen Aufbau-Flow (Effekt reinziehen → Drop-Karte ankreuzen, Widget-Galerie, Konfliktschutz, Widget-Typ-Wechsel). `docs/anleitung_vc_widgets/README.md`, `docs/anleitung_vc_smartbuild/ANLEITUNG.md`, `docs/tutorial_matrix/TUTORIAL_LICHTSHOW.md`.
- **Show-Dateiformat-Spezifikation erweitert:** `docs/SHOW_FILE_FORMAT.md` dokumentiert die neuen/erweiterten .lshow-Bloecke (playlist, music_autoshow, efx_paths, Function-Param `priority`, Visualizer-Andock-Beziehungen + active_stage, live_view-Meta). `docs/SHOW_FILE_FORMAT.md`.
- **Performance-Benchmark und Programmier-Notizen:** Neue `docs/PERFORMANCE.md` mit Render-Pipeline-Benchmark ueber 8/16/32 Universen (p50/p95/FPS) und Hinweis auf super-lineares Wachstum oberhalb des 44-Hz-Budgets; neue `docs/PROGRAMMING_NOTES.md` buendelt nicht-offensichtliche Fakten fuer Show-/Engine-Arbeit. `docs/PERFORMANCE.md`, `docs/PROGRAMMING_NOTES.md`.
- **Optionale BPM-Engines und Status-Dokumente fortgeschrieben:** `requirements.txt` listet (auskommentiert, nicht erforderlich) die optionalen Analyse-Engines librosa, soundfile, torch und beat_this; `docs/OPEN_POINTS_OVERVIEW.md` wurde mit umgesetzten Punkten fortgeschrieben und `MIDI_CRASH_DEBUG_NOTES.md` als historisch markiert (Crash-Hypothesen durch die Thread-Safety-Fixes adressiert). `requirements.txt`, `docs/OPEN_POINTS_OVERVIEW.md`, `MIDI_CRASH_DEBUG_NOTES.md`.

### Behoben/Hinzugefuegt (2026-06-15 — EFX-Formen, Anzeige-Sync, Geräte-Solo)
- **EFX-Formen mit harten Kanten:** `SQUARE` und `DIAMOND` waren trigonometrische
  Näherungen, die die Ecken diagonal *abschnitten* (ein „Quadrat" erreichte die
  echte Ecke nie → wirkte verschliffen). Jetzt sind Quadrat/Raute/Dreieck **echte
  Polygone** mit scharfen Ecken (gemeinsamer `_polygon`-Helfer, lineare Kanten,
  jede Kante 1/n der Phase). Neue Form **`TRAPEZ`** (schmal oben, breit unten);
  erscheint automatisch im EFX-Editor-Dropdown. `TRIANGLE` bit-identisch zum
  bestehenden Test. Für freie harte Kanten gibt es zusätzlich den Custom-Path
  (Modus „linear"). `src/core/engine/efx.py`, Tests `tests/test_efx_hard_edges.py`.
- **VC-Button spiegelt Laufzustand:** ein FUNCTION_TOGGLE-Pad leuchtete nur
  während des Drucks (`_pressed`), nicht solange seine Funktion lief — es sah aus,
  als liefe nichts mehr, obwohl sich die Moving Heads noch bewegten. Jetzt grüner
  „aktiv"-Rahmen, solange der Effekt läuft (`_function_running`); die VC-View
  zeichnet funktionsgebundene Pads bei jedem Laufzustands-Wechsel neu (UI-Thread-
  Timer, thread-sicher). `vc_button.py`, `virtual_console_view.py`, Test
  `tests/test_vc_button_running_feedback.py`.
- **Geräte-Solo (gegen Bank-übergreifendes Überschreiben):** neue VC-Pad-Option
  **„Andere Effekte auf denselben Geräten stoppen"** — beim Start ersetzt der
  Effekt nur die laufenden Effekte, die DIESELBEN Strahler benutzen (auch aus
  einer anderen Bank), Effekte auf anderen Geräten laufen weiter. Chirurgischer
  als „Exklusiv" (= alles stoppen). Engine: `FunctionManager.affected_fids()`
  (alle Typen, rekursiv über Chaser/Collection/Sequence) +
  `stop_others_sharing_fixtures()`. `function_manager.py`, `vc_button.py`, Test
  `tests/test_function_solo_fixtures.py`.
- **Live-View-Info-Box zeigt EFX/Matrix:** laufende EFX-/RGB-Matrix-Effekte
  wurden nie als „aktiv" am Gerät gelistet (`hasattr(func,'_values')` traf bei
  EFX die gleichnamige *Methode* → Exception). Jetzt korrekt per isinstance-Guard
  über alle Typen (EFX `fixtures`, Matrix `fixture_grid`, Carousel/LayeredEffect
  `fixture_ids`, Scene `_values`). `src/ui/views/live_view.py`.

### Hinzugefuegt (2026-06-14 — Fixture Generator, F-23/X-4)
- **Fixture Generator** (grafisches Anlegen eigener Geraete-Profile, an QLC+ 5
  orientiert): `src/ui/widgets/fixture_generator.py` (`FixtureGeneratorDialog`),
  Start im **Patch-Tab → „Gerät erstellen…"**. Kopf (Hersteller/Modell/Typ/
  Leistung/Notizen), mehrere Modi, gefuehrter Kanal-Editor (Attribut-Combo +
  Freitext, **mehrfache gleiche Attribute** wie zwei Pan/zwei Tilt, Default/
  Highlight, Invert, **8/16-bit mit Fine-Kanal-Kopplung**), Bereichs-Editor je
  Kanal (range_from/to, Name, `kind`, „Art aus Namen", Schnellwahl-Vorschau),
  **nicht-blockierende Live-Validierung** (0–255, Ueberlappung, Luecke,
  doppelte Attribute, Dimmer↔Strobe-Plausibilitaet, fehlender open-Bereich,
  Modus-Vergleich), **echter Live-Test** (Universe + Startadresse, ein Fader pro
  Kanal schreibt direkt ins Universe des OutputManagers, „Wackeln" rampt einen
  Kanal, „Blackout" + sauberes Restore beim Stop/Schliessen), **`.qxf`-Import**
  als Startpunkt und **Markdown-Export** des Kanal-Layouts. Speichert als
  `source="user"` via `fixture_db.create_user_profile` und emittiert
  `REFRESH_ALL`. Kernlogik UI-unabhaengig/testbar
  (`build_profile_payload`/`validate_model`/`LiveTester`/`model_to_markdown`).
  Tests: `tests/test_fixture_generator.py` (18). Doku:
  `docs/FUTURE_FIXTURE_GENERATOR.md`.

### Hinzugefuegt (2026-06-11 — Details: docs/UPDATE_2026-06-11.md)
- **EFX Custom Paths:** eigene Pan/Tilt-Bewegungen im Popout-Editor aufzeichnen
  (Punkte tippen/ziehen/umsortieren, Linear oder Spline, Vorschau), Pfad-
  Bibliothek pro Show (`efx_paths`), Auswahl im EFX-Hauptfenster, Loop/One-Shot
  als EFX-Eigenschaft. Engine: `efx_path.py` (bogenlaengen-parametrisiertes
  Sampling), `EfxAlgorithm.CUSTOM`. Tests: `tests/test_efx_path.py`.
- **EFX ueber VC/MIDI:** `EfxInstance` traegt jetzt die Live-API
  (`list_params`/`set_param`/`do_action`/`list_actions`) — Speed/Groesse/Fan/
  Richtung/Loop/Pfad/Form auf Fader & Tasten mappbar, gleiche Mechanik wie
  Matrix/Chaser; Live-Editor-Dialog zeigt funktionsspezifische Aktionen.
- **Patchen → Gruppenansicht → "Bearbeiten…":** Mitglieder hinzufuegen/
  entfernen, Reihenfolge (Fan/Chase) per ▲▼, Name aendern — touch-tauglich
  ohne Drag&Drop. Tests: `tests/test_group_edit_dialog.py`.
- **Live View Touch:** Mehrfachauswahl-Modus toggelt jetzt auch die linke
  Liste per Antippen (MultiSelection), groessere zoom-unabhaengige
  Trefferflaechen, Naechster-gewinnt-Hit-Test.
- **Programmer-Ordner klappbar:** Gruppen-Ordner-Kopfzeilen antippbar (▾/▸,
  persistiert); Bibliotheks-Ordnerzustand ueberlebt Rebuilds + Neustart.
- **Controller-Datenbank:** JSON-Profil-Bibliothek (`data/controller_library/`
  + Nutzer-Importe) mit 8 Seed-Geraeten (APC mini/mk2, nanoKONTROL2, X-Touch
  Mini, Launchpad Mini MK3, Enttec DMX USB Pro, Art-Net-Node, Makro-Tastatur),
  QLC+-.qxi-Import (CLI + UI), Browser in der MIDI-Konsole. Quellen/Lizenzen:
  `data/controller_library/README.md`. Tests: `tests/test_controller_library.py`.
- **VC-Keyboard-Mapping:** Tasten/Kombinationen auf VC-Buttons lernen
  (Rechtsklick → "Taste zuweisen…"), Konfliktpruefung, Blackout-Warnung,
  Textfeld-/Modal-/AutoRepeat-Schutz, Press/Release wie MIDI-Note, Persistenz
  im VC-Layout. Doku: `docs/KEYBOARD_MAPPING.md`. Tests:
  `tests/test_keyboard_mapping.py`.
- **Demo:** `tools/build_custom_path_demo.py` → `shows/CustomPath_Demo.lshow`
  (selbst-verifizierend; MIDI- + Tastatur-Bindungen, One-Shot + Loop-Pfad).
- **Fixture-Quellen-Doku:** `docs/FIXTURE_SOURCES.md` (OFL/QLC+ legal nutzen).

### Behoben
- **Zombie-Subscriber im Event-Bus (Crash-Klasse aus crash.log, 2026-06-10).**
  Eingebettete Views (EFX-/Matrix-/Paletten-Seite, SnapFilePanel) werden bei jedem
  Programmer-Layout-Wechsel neu gebaut, blieben aber im StateSync registriert —
  der naechste Emit lief in geloeschte Qt-Objekte (RuntimeError bis Access
  Violation, siehe %APPDATA%/LightOS/crash.log). Neu: `StateSync.subscribe_widget`
  (auto-unsubscribe bei `destroyed`) fuer diese Views + Selbstheilung in
  `StateSync.emit` ("already deleted"-Subscriber werden entfernt).
  Tests: `tests/test_sync_safe_subscribe.py`.
- **EFX "Bounce" sprang am oberen Umkehrpunkt auf den Anfang.** Nach dem Klemmen
  der Phase auf 1.0 lief noch das gemeinsame `%= 1.0` -> Phase 0.0 (Saegezahn statt
  Pendel). Betroffen u. a. "MH Bounce" in `Komplett_Demo.lshow`.
  Tests: `tests/test_moving_head_efx.py::EfxBounceTest`.

### Hinzugefuegt
- **UI-Freeze-Watchdog (main.py).** Freezes ("Keine Rueckmeldung") hinterliessen
  bisher keinen crash.log-Eintrag. Ein 1-s-Herzschlag-Timer im UI-Thread + Daemon-
  Watchdog dumpt nach >10 s Stillstand die Stacks ALLER Threads nach crash.log —
  der naechste Freeze ist damit diagnostizierbar.
- **Headless-Verifier fuer die Komplett-Demo** (`tools/verify_komplett_demo.py`):
  laedt die Show ohne UI, prueft Referenz-Integritaet (Timeline/Chaser/VC), tickt
  die AUTO-SHOW >1 Loop durch den echten Renderer und assertet, dass sich die
  Moving-Head-Kanaele in den EFX-Abschnitten bewegen.
- **ZQ02001-Profil: Dimmer/Strobe waren vertauscht (2026-06-10).** Nach realen
  Gerätedaten korrigiert: Strobe liegt VOR dem Dimmer (9ch: CH5/CH6, 11ch: CH7/CH8);
  der 9-Kanal-Modus hatte fälschlich Pan/Tilt-fein statt Pan/Tilt-Speed, Gobo-FX und
  Reset. Farbrad (15 Slots inkl. 6 Split-Farben + Auto), Gobo (7 statisch + 7 Shake +
  Wechsel 128–255) und Strobe (0–9 offen / 10–249 langsam→schnell / 250–255 aus) sind
  jetzt als exakte `ChannelRange`-Bereiche mit `kind` hinterlegt. `ensure_builtins()`
  aktualisiert veraltete builtin-Profile **in-place** (Profil-ID stabil — bestehende
  Patches überleben). Der Reset-Kanal war zudem als zweiter `macro`-Kanal im
  Programmer unsichtbar (Attribut-Dedup) → neue Attribute `gobo_fx` und `reset`.
  Doku: `docs/MOVING_HEADS.md`. Tests: `tests/test_zq02001_profile.py`.
- **Test-Suite-Stabilität:** erzeugte `VCCanvas`-Instanzen blieben beim globalen
  MIDI-Manager registriert (Abmeldung nur bei Zerstörung); über viele Tests häuften sich
  tote Callbacks bis zu einem harten Crash. Neue Autouse-Fixture (`tests/conftest.py`)
  meldet nach jedem Test alle noch lebenden Canvases ab.
- **Simple Desk Roh-Bypass (ISO-03):** Die 512 Fader schrieben direkt ins Live-Universe,
  **am zentralen Renderer vorbei**. Folge: auf gepatchten Kanaelen ueberschrieb der Renderer
  den Wert Frame fuer Frame (Flackern/wirkungslos), auf freien Kanaelen blieb er als
  **unsichtbarer „Zombie"** dauerhaft stehen. Simple Desk ist jetzt eine deterministische
  **Override-Schicht** im `_render_frame` (oberste Ebene): kein Flackern, kein Zombie, und
  die Werte sind sicht- (ISO-01) und loeschbar (ISO-02). Test: `tests/test_iso_simple_desk.py`.
  **Standard = reine Anzeige (Monitor):** die Fader spiegeln die Ausgabe und wirken nicht;
  erst die Checkbox **„Manueller Override"** gibt ihnen absolute Oberhand (im Anzeige-Modus
  sind Fader + „Alles auf …"-Buttons gesperrt).
- Effekt-Layering (LAYER-01): Laufende Funktionen wurden in **ungeordneter** Reihenfolge
  (Set) getickt. Schrieben zwei Effekte denselben DMX-Kanal (z. B. Farb-Matrix mit
  `drive_intensity` + Dimmer-Matrix), gewann ein **zufaelliger** Writer statt der zuletzt
  gestarteten Funktion → Werte wurden unvorhersehbar ueberschrieben. `FunctionManager.tick()`
  laeuft jetzt in Start-Reihenfolge (LTP: zuletzt gestartet gewinnt). Test:
  `tests/test_function_layer_order.py`.
- Virtual Console: Absturz (`KeyError: 0`) beim Bewegen eines Level-Faders. Ursache war
  eine fehlerhafte Universe-Pruefung (`< len()` auf einem dict mit 1-basierten Keys).
  Der Fader legt das Ziel-Universe nun bei Bedarf an; das Universe ist im
  Fader-Eigenschaften-Dialog einstellbar (Default 1).

### Hinzugefuegt
- **Moving-Head-Bedienung im Programmer (2026-06-10):** Strobe liegt jetzt im
  **Intensity-Tab** neben dem Dimmer (Status-Kacheln „Kein Strobe/Strobe aus" +
  stufenloser Speed-Slider + DMX-Bereichslegende; Grand Master fasst den Strobe-Kanal
  weiterhin nicht an). **Color-Wheel-Direktwahl**: farbige Kacheln für alle Voll- und
  Split-Farben (zweifarbig dargestellt) + **Auto-Farbwechsel** als Hardware-Rotation
  (Tempo-Slider) und **Software-Simulation** mit wählbarem Bereich (Von/Bis, „Nur
  Split-Farben"). **Gobo-Tab**: Kacheln mit **grafischer Gobo-Vorschau** (neues
  wiederverwendbares Modul `src/ui/widgets/gobo_icons.py`, 7 QPainter-Muster),
  Shake-Kacheln mit einstellbarer Geschwindigkeit, Gobo-Wechsel-Slider (128–255) mit
  Stopp, Gobo-FX-Fader. **Reset-Button** („Weitere") mit Sicherheitsabfrage und
  automatischem Rücksetzen nach 4 s — bewusst kein Dauer-Slider. Alles generisch aus
  den `ChannelRange`-Daten (kein Raten ohne Capability-Daten). Neue Doku:
  `docs/MOVING_HEADS.md`, `docs/FIXTURE_LIBRARY.md`,
  `docs/FUTURE_FIXTURE_GENERATOR.md` (Idee, bewusst nicht gebaut) und
  `docs/OPEN_POINTS_OVERVIEW.md` (repo-weite Übersicht offener Punkte).
- **Phase-6-Feinschliff:** Matrix-**Versatz**-Parameter (`offset`) + Dimmer/Shutter-Min/Max
  und Weissanteil **live steuerbar** (MXP-02/03); **Simple-Desk-Fader nach Fixture eingefärbt**
  (SDK-01); **Fader-Reichweite „nur Auswahl/Gruppe"** im Programmer-Modus (FDR-01); VC-Toolbar
  entschlackt (UIC-02..05: „⊞ Raster", „Canvas exportieren/importieren", „Aktiver Effekt"-Zeile
  nur bei laufendem Effekt, Canvas-Kontextmenü ohne Save/Load-Dopplung). Tests:
  `test_matrix_offset_style_params.py`, `test_fader_scope.py`, `test_simple_desk_tint.py`.
- **Demo-/Bühnen-Show (DMO-01):** `tools/build_demo_zq_show.py` → `shows/Demo_ZQ_Buehne.lshow`
  mit **4× ZQ01424 (PAR)** + **2× ZQ02001 (Moving Head)**: Farben/Looks, Dimmer-Lauflicht,
  RGB-Matrix, Moving-Head-Positionen/Beam + Sweep-Chaser, **Speed-Dial (Multiplikator)**,
  zwei **VC-Frames** (PARs / Moving Heads) und ein **Multi-Action-Button** „▶ Showtime".
  (Die ursprünglich als „Horhin" bezeichneten Strahler sind ZQ01424, der Moving Head ist ZQ02001.)
- **Paletten + Kurven: Unterordner (FLD-01c):** Paletten und Fade-Kurven haben jetzt ein
  verschachtelbares `folder`-Feld (in der Show gespeichert, rückwärtskompatibel). Die
  Paletten-Ansicht gruppiert nach Ordner (Überschriften) und bietet „In Ordner verschieben…".
  Damit ist FLD-01 („Unterordner überall") abgeschlossen. Test: `tests/test_palette_curve_folders.py`.
- **Fixture-Gruppen: Unterordner (FLD-01b):** Gruppen lassen sich einem verschachtelten
  Ordner zuordnen („Ordner…"-Button, Pfad mit `/`, z. B. „Front/Wash"); die Gruppen-Auswahl
  zeigt den Ordnerpfad und sortiert danach. Neue, **idempotente DB-Migration**
  (`migrate_show_db`) ergänzt die `folder`-Spalte in bestehenden Show-DBs ohne Datenverlust.
  Test: `tests/test_fixture_group_folders.py`.
- **Funktions-Manager zeigt Ordner (FLD-01a):** die rechte Funktionsliste bildet jetzt die
  vorhandene, verschachtelte Ordner-Hierarchie der Funktionen (`folder`-Pfad, z. B.
  „Blau/Sommer") innerhalb jeder Typ-Gruppe ab — erster Schritt von „Unterordner überall".
  Test: `tests/test_function_folders.py`.
- **Snapshots: Kanäle nachträglich ignorieren (SNP-01):** pro Snapshot lassen sich
  einzelne (Fixture, Attribut)-Kanäle vom Anwenden ausschließen — der gespeicherte Wert
  bleibt erhalten, wird aber nicht in den Programmer geschrieben. Editor über „Kanäle
  ignorieren…" (Alle/Keine/Invertieren); rückwärtskompatibel. Test: `tests/test_snapshot_ignore.py`.
- **Kanal-Gruppen pro Show (SDK-02):** Channel Groups werden jetzt in der `.lshow`
  gespeichert/geladen (statt nur global in `data/channel_groups.json`). Test:
  `tests/test_channel_groups_show.py`.
- **Widgets per Drag in Frames ziehen (FRM-01):** ein vorhandenes VC-Widget lässt sich in
  einen Frame ziehen (wird dessen Kind, Position relativ) und wieder heraus auf den Canvas;
  die Zuordnung bleibt beim Speichern erhalten. Frames werden nicht verschachtelt. Test:
  `tests/test_frame_drag.py`.
- **Multi-Actions auf VC-Buttons (BTN-01):** ein Button kann beim Druck — nach seiner
  Primär-Aktion — eine Liste weiterer Aktionen der Reihe nach ausführen (Funktion
  start/stop/toggle, Effekt-Aktion, Snapshot, Bibliothek-Snap, Blackout, Stop-All,
  Programmer/Non-VC leeren, Tap), je mit optionaler Verzögerung. Editor über
  „Mehrfach-Aktionen…" im Button-Dialog; ein „+n"-Marker zeigt die Anzahl. Vollständig
  rückwärtskompatibel (ohne Liste = klassischer Ein-Aktions-Button). Test:
  `tests/test_button_multi_action.py`.
- **Speed Dial: Multiplikator-Modus, Sync, Multi-Ziele, Invertierung (SPD-01/02/03/04):**
  optionaler **Multiplikator-Modus** (Dial als Faktor 0.5/1/2/4× auf die Effekt-Speed statt
  absoluter BPM), **SYNC-Button** (gleicht die Phase aller Ziel-Effekte an), **mehrere
  Ziel-Effekte** (weitere Function-IDs) und eine **Invert-Option** (höher = langsamer).
  Persistiert, rückwärtskompatibel. Test: `tests/test_speed_dial.py`.
- **Matrix-Live-Editor in der Virtual Console (MLV-01/02):** Rechtsklick auf einen an
  einen Effekt gebundenen VC-Button/-Fader zeigt „⚡ Live-Parameter…". Der Dialog listet
  die live steuerbaren Parameter (→ Fader) und Aktionen (→ Tasten) des Effekts; die Auswahl
  wird **automatisch** als korrekt gebundene VC-Bedienelemente erzeugt (EFFECT_PARAM /
  EFFECT_ACTION, an die `function_id` des Effekts). Bearbeiten/Entfernen über die normalen
  Widget-Menüs. Test: `tests/test_matrix_live_vc.py`.
- **Fixture U King ZQ02001 (LIB-01):** Mini-Gobo Moving Head (11-Kanal + 9-Kanal) zur
  Fixture-Library hinzugefügt — `examples/add_zq02001.py`. Kanal-Layout aus dem
  Hersteller-Handbuch; feine Farb-/Gobo-Wertbereiche sind genähert und im Skript markiert.
- **Matrix-Chase „Farbwechsel-Intervall" (MXP-01):** neuer Parameter `color_interval`
  (sichtbar bei aktivem „Farbe pro Runde wechseln") — die Farbe wechselt erst alle N
  Durchläufe (1 = jeder Durchlauf wie bisher, 2/4/8 = langsamer). Live über VC/MIDI
  steuerbar, persistiert, Default 1 für Alt-Shows. Test: `tests/test_matrix_color_interval.py`.
- **Color-Sequence: Swatch-Einzelklick öffnet den Color-Picker (MXP-04):** im kompakten
  Farbstreifen (Matrix-Programmer) öffnet ein Klick auf ein Farbquadrat direkt den Picker
  für diese Farbe (live), ohne erst den Editor öffnen zu müssen.
  Test: `tests/test_color_sequence_swatch.py`.
- **Anzeige aktiver Fremdwerte (ISO-01):** Die obere Leiste zeigt jetzt ein Badge
  „● Programmer n · Simple Desk n", sobald manuelle Werte aktiv sind — damit faellt nichts
  mehr unbemerkt in die Live-Ausgabe.
- **Zentrales Clear (ISO-02):** Button „✖ Clear ▾" in der oberen Leiste mit
  *Programmer leeren · Simple Desk leeren · Alle Nicht-VC-Werte leeren*. Setzt nur aktive
  manuelle Werte zurueck — laufende Funktionen/Effekte/Cues, gespeicherte Effekte, Shows,
  Patches und Fixtures bleiben unangetastet. API: `clear_simple_desk()`, `clear_all_non_vc()`.
- Virtual Console: pro Effekt-Fader einstellbar, ob er **bei 0 den Effekt stoppt** oder
  **nur runterregelt** (Eigenschaft `effect_autostart`, Checkbox im Fader-Dialog). An:
  Wert > 0 startet den gebundenen Effekt, Wert 0 stoppt ihn (wie ein Playback-Fader);
  aus (Default): Fader regelt nur. Gilt fuer *EffectIntensity/EffectSpeed/EffectParam*.
- Visualizer-Persistenz: Fixture-Positionen und die aktive Buehne werden mit der Show
  (`.lshow`) gespeichert und beim Laden wiederhergestellt (T-VIZ-01, T-VIZ-02).
- Unit-Tests fuer Core-Engine: `tests/test_core_engine.py`
  - `Universe` (DMX-Kanalverwaltung, Thread-Safety, Boundaries)
  - `Cue` (Datenmodell, Serialisierung-Roundtrip)
  - `FadeState` / `CueStack` (Fade-Interpolation, Go/Back/Stop/Loop, Callbacks)
  - `ChannelModifier` / `ChannelModifierManager` (alle Kurventypen, apply_to_universe, Save/Load)
  - `SelectionExpr` (Fixture-Selektion, Ranges, Excludes)
  - Command-Line Parser (`parse()` fuer alle Befehle)
  - `UndoStack` (Push/Undo/Redo, MAX_SIZE-Cap, Listener)
- `README.md` um "Quick Start"-Abschnitt erweitert (5-Minuten-Guide fuer neue Nutzer)
- `.github/workflows/ci.yml` — automatisierte Test-Pipeline (Python 3.11 + 3.12)
- `CHANGELOG.md` — diese Datei (Keep-a-Changelog-Format)

### Entfernt
- **Redundanter „Snap"-Button (UIC-01)** aus der oberen Leiste. Die Schnell-Snapshot-Funktion
  bleibt vollstaendig erreichbar ueber Menue *Programmer → Snapshot aufnehmen* (`Strg+Shift+S`),
  die *Snapshots*-Ansicht und die VC-Seitenleiste.

---

## [0.1.0] — 2026-05-26

### Hinzugefuegt
- Vollstaendige DMX-Steuerungs-Engine
  - Enttec DMX USB Pro, Art-Net 4, sACN / E1.31 (bis zu 32 Universen)
  - OutputManager mit 44-Hz-Loop, Grand Master, Blackout, Submasters
  - Channel-Modifier mit 7 Kurventypen + Custom LUT
- Engine (10 Function-Typen)
  - Scene, Chaser, Collection, Show (Timeline), EFX, RGB-Matrix,
    Sequence, Audio, Script, LayeredEffect, Carousel
  - Multi-Page-Playback: 10 Pages × 20 Executors = 200 Slots
  - Cue-System mit Fade-In/Out, Delay, Auto-Follow, Loop
  - Undo/Redo (unbegrenzt, 100er-Cap)
- Programmer
  - Attribut-Gruppen: Intensity, Color, Position, Beam, Gobo, Effect
  - Color Picker (RGB/HSB/CMY, 27 Lee-Rosco Gel-Filter)
  - Position Tool (2D-Pad, 13 Presets)
  - Fan Tool (5 Kurven, Symmetric/Asymmetric)
  - Snapshots (12×4 Quick-Recall)
  - Paletten (Color / Position / Beam)
- Audio / BPM
  - WASAPI Loopback Audio-Capture
  - Beat-Detection (Bass-Energy adaptive Threshold)
  - Tap-Tempo BPM-Manager
  - OS2L Server (VirtualDJ Integration)
  - MIDI Time Code Reader
- Virtual Console
  - Button, Slider, XY-Pad, Cue-List, Speed-Dial, Frame, Label, Solo-Frame
  - Save/Load Layouts pro Show
- 3D Visualizer (Three.js / QtWebEngine)
  - 2D Top-Down + 3D Perspektive, 4 Bühnen-Presets + Custom Stage Builder
  - Echte 3D-Modelle, volumetrische Beam-Cones
- Eingaben
  - MIDI Input mit Profil-Editor (Akai APC mini Default)
  - OSC Server (Port 7770)
  - Keyboard-Hotkeys
  - Web-Remote (Flask + Socket.IO)
- Command-Line (MA-/Avolites-Style)
  - `1 thru 5 @ 80`, `all @ full`, `go 1`, `record cue 2.5`, `page 3`, `blackout`
- Installer/Uninstaller (`install.py`, `uninstall.py`)
  - ARM64/Snapdragon-Erkennung, venv-Management, Desktop-Verknuepfung
- Start-Skripte fuer CMD (`.bat`), PowerShell (`.ps1`), Bash (`.sh`)
- Fixture-Datenbank (SQLAlchemy/SQLite), GDTF-Import
- Show-File-Format `.lshow` (ZIP + JSON, Version 1.1, Legacy-1.0-Support)
- Vollstaendige Dokumentation in `docs/`

---

<!-- Verlinkung fuer die Versionen -->
[Unreleased]: https://github.com/OWNER/lightos/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/OWNER/lightos/releases/tag/v0.1.0
