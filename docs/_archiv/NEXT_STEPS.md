# LightOS — Nächste Schritte / Capabilities-Roadmap

> Stand: 2026-05-31. Priorisierte Liste zum gemeinsamen Abarbeiten.
> Legende: 🟢 klein/schnell · 🟡 mittel · 🔴 größerer Umbau · ✅ erledigt

## A. Live-Bedienung & APC mini
- ✅ **Pad-Stil pro Button wählbar** (Spiegel / Wechselfarbe / Welle / Puls) — erledigt 2026-05-31 (`vc_button.pad_style` + `apc_mk2_feedback`).
- ✅ **„Display-only"-Sperre** fürs Touchpanel — erledigt 2026-05-31 (`vc_widget.input_locked` + VC-Toolbar-Toggle).
- ✅ **Page-/Bank-Umschaltung** — erledigt 2026-05-31. VC-Widgets haben ein Feld `bank` (-1 = alle Banks, 0..9 = Executor-Page). Canvas koppelt an `PlaybackEngine.subscribe_page` → APC-Page-Buttons schalten die Pad-/Widget-Seite, blenden Widgets ein/aus und gaten MIDI-Dispatch; APC-LEDs zeigen nur die aktive Bank. Bank-Zuweisung per Widget-Rechtsklick, Bank-Umschalter (◀ Bank N ▶) in der VC-Toolbar. `bank` wird in der Show gespeichert.
- ✅ **MIDI-Learn direkt im Live-Betrieb** — erledigt 2026-05-31. Function-Manager-View: Funktion auswählen → „🎹 MIDI lernen" (Toolbar/Rechtsklick) → Pad/Fader drücken → erzeugt live ein `MidiMapping` (`function:<id>`, Toggle) inkl. Ersetzen vorhandener Bindung, speichert nach `data/midi_mappings.json`. Dabei den latenten Mapper-Bug behoben: Funktions-Ziele (`action="function"`) lösten nie aus (`ACTION_FUNCTION` jetzt in `_execute_binary`).

## B. Effekte
- 🔴 **Freies Effekt-Layering** (zwei Effekte echt übereinander, z. B. Bewegung auf Intensität + Farbe getrennt) — via LayeredEffect/Effekt-Layer.
- ✅ **Per-Effekt-Intensität & -Speed** — erledigt 2026-05-31. Jede `Function` hat `intensity` (0–1) und `speed` (0,1–4×), beide in der Show gespeichert. `FunctionManager.tick` rendert Effekte mit `intensity<1` in ein privates Universum und merged ihre geänderten Kanäle **skaliert** (virtueller Dimmer: skaliert den Dimmer-Kanal, sonst die Farbkanäle; Pan/Tilt unberührt). `LayeredEffect`/`Carousel` honorieren `speed` (Chaser/Sequence schon vorher). Live-Bedienung: VC-Fader-Modi `EFFECT_INTENSITY`/`EFFECT_SPEED` mit Ziel = bestimmter Effekt **oder** (Feld leer) der aktive/zuletzt gestartete Effekt (`FunctionManager.active_function()`). 122 Tests grün (`TestPerEffectIntensity`, `TestEffectSpeedMaster`).
- 🟡 **Live-Vorschau im Effekt-Assistenten** (Effekt schon beim Einstellen sehen).
- 🟢 **Eigene Effekte als Vorlage speichern** (User-Effekte in einer Bibliothek wiederverwenden).
- 🟢 **Mehr Effekt-Typen** im Assistenten (Comet/Schweif, Chase mit Tail, Random-Strobe, VU-Meter-artig).

## C. Show- & Funktions-Verwaltung
- ✅ **Executor-/Cue-Bindung persistieren** — erledigt 2026-05-31. `PlaybackEngine.to_dict/from_dict` + `Executor.to_dict/apply_dict` (Stack-Bindung als Index in `cue_stacks`, pro Page/Slot inkl. Fader/Label/Page-Namen), in `show_file.py` als `"executors"` gespeichert/geladen (nach den cue_stacks, mit Reset stale Bindungen). `playback_view.py` `ExecutorWidget.refresh_from_state` aktualisiert Combo/Fader nach Load/Page-Wechsel. 112 Tests grün.
- ✅ **Snapshots pro Show** statt global — erledigt 2026-06-01. Snapshots werden in die `.lshow` geschrieben (`show.json` Key `snapshots`); beim Laden ersetzt die Show ihren Satz (`SnapshotsView.to_dict`/`load_data`, Bruecke im `main_window` analog zum VC-Layout). Die globale `snapshots.json` bleibt nur noch Live-Puffer zwischen Speichern.
- ✅ **Chaser-Editor: Notiz-Spalte zurückschreiben** — erledigt 2026-06-01. `chaser_editor.py` verbindet `itemChanged` → `_on_note_changed` (schreibt Spalte 6 in `step.note`; via `_step_to_dict` schon serialisiert).
- ✅ **Funktions-Editor: kein Neuaufbau bei Refresh** — erledigt 2026-06-01. `function_manager_view._open_editor` baut den Editor nicht neu, wenn dieselbe Funktion (gleiche fid + Objekt-Identität) bereits offen ist → kein Eingabe-/Fokusverlust bei REFRESH_ALL/FUNCTION_CHANGED.

## D. Stabilität (offene Audit-Befunde, siehe PROJECT_AUDIT.md)
- 🔴 **sACN (C5)** spec-konform neu (E1.31-Paketaufbau defekt) — nur falls sACN-Ausgabe gebraucht wird. Braucht Hardware-/Wireshark-Test.
- 🟡 **Thread-Disziplin (C8)** — `app_state._emit` ruft UI-Callbacks teils direkt cross-thread (MIDI→ProgrammerView) → in den UI-Thread marshallen.
- ✅ **ArtNet-Broadcast-Default** — erledigt 2026-06-01. Default von `2.255.255.255` auf limited broadcast `255.255.255.255` umgestellt (SO_BROADCAST ist gesetzt → erreicht alle Nodes auf dem Link, unabhaengig vom Subnetz). Felder in `artnet.py`, `output_manager.py`, `output_config.py`.
- ✅ **Output-Konfiguration persistieren + beim Start anwenden** — erledigt 2026-06-01. `AppState.apply_output_config()` liest `data/universes.json` und richtet Enttec/ArtNet/sACN beim Start ein (in `get_state()` nach `open_show`); der Universe-Manager wendet beim Speichern sofort an.

## E. Visualizer / Bühne
- 🟡 **Bühnen-Layout der echten Lampen** im Visualizer (Positionen entsprechend der realen Anordnung).
- 🟢 **2D-Top-Down-Ansicht** als schnelle Kontrolle neben der VC.

## F. Kleinere Politur
- ✅ BPM-Beat-Indikator (oben rechts) größer/deutlicher — erledigt 2026-06-01. Runder 26×26-Beat-Punkt (Takt 1 gelb, sonst grün) statt 12×18-Balken (`main_window.py`).
- 🟢 Bessere Default-Farben/Beschriftungen im Panel (laufend).
- ✅ Status-Zeile „aktiver Effekt: …" im VC — erledigt 2026-06-01. Slim-Statuszeile unter der VC-Toolbar, aktualisiert alle 400 ms via `FunctionManager.active_function()` (zeigt Typ · Name + Anzahl weiterer laufender).

---
**Empfohlener nächster Block:** A (Pad-Stil + Display-Lock, schnell & sichtbar) ODER
C (Executor-Persistenz → Fader 1-8 funktionieren dauerhaft). B-Layering ist der größte „Wow"-Schritt, aber aufwändiger.
