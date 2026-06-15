# LightOS — Roadmap

> Stand: 2026-05-27 · Priorisierung: Kurzfristig (< 3 Monate) → Mittelfristig (3–9 Monate) → Langfristig (> 9 Monate)

---

## Kurzfristig

### UI / Bedienung
- **Preset-Browser** — Schnellzugriff auf Paletten und Gruppen per Suchfeld
- **Undo im Patch** — Fixture löschen rückgängig machen
- **Fixture-Kopieren mit Offset** — Mehrere Geräte gleichzeitig patchen mit Adress-Abstand
- ✅ **Touch-Keyboard** — On-Screen-Numpad bei Texteingabe auf Touchscreen *(erledigt — `src/ui/touch_keyboard.py`)*

### Engine
- ✅ **Fade-Kurven auswählen** — Linear, Ease-In, Ease-Out, S-Kurve, Snap pro Cue konfigurierbar *(erledigt 2026-06-14 — `Cue.fade_curve`, Combo im Playback-Tab; Default `scurve` = altes Verhalten)*
- **Cue-Delay In/Out** — Separat für jedes Attribut einstellbar (Attribute-Level Delay) *(Cue-Ebene erledigt: `delay_in`/`delay_out`; Attribut-Ebene offen)*
- ✅ **Stack-Loop-Modi** — Einzel, Loop, Bounce, Ping-Pong *(erledigt — `CueStack.mode`)*

### Ausgabe
- **sACN / E1.31 Ausgabe** — Alternative zu Art-Net für Environments mit sACN-Nodes
- **Enttec Open DMX USB** — Stabilisierung des Treibers für lange Sessions (>8h)

### Stabilität
- ✅ **Crash-Report-Dialog** — Bei unbehandelter Exception: Fehlermeldung + Log-Snippet anzeigen *(erledigt 2026-06-14 — `crash_dialog.CrashReporter` an `sys.excepthook`, thread-sicher, mit Traceback + crash.log-Auszug)*
- ✅ **Autosave-Intervall** — Konfigurierbar (1–60 Minuten), Standard 5 Minuten *(erledigt 2026-06-14 — Datei-Menü „Auto-Save-Intervall…", persistiert in ui_prefs.json)*

---

## Mittelfristig

### UI / Bedienung
- **Macro-System** — Abfolgen von Kommandozeilen-Befehlen als Makro speichern und abrufen
- **Multi-Monitor-Layout** — Frei positionierbare Docks auf mehreren Bildschirmen speichern
- **Touch-Optimierung Phase 2** — Pinch-Zoom im Patch, Swipe zwischen Tabs, größere Hit-Targets
- **Quick-Recording** — Ein-Klick-Record direkt im Playback-View ohne Umweg

### Engine
- **Timecode-Import aus Audio** — BPM-Grid automatisch aus WAV/MP3 erkennen
- **Sequence-in-Sequence** — Cuelisten als Schritte in anderen Cuelisten einbetten
- **Effect-Layer-Priorität** — Mehrere gleichzeitige Effekte mit Prioritäts-Stacking

### Netzwerk / Remote
- **Web-Remote Phase 2** — Cuelisten-Ansicht, Patch-Übersicht, Programmierer-Zugriff
- **OSC-Feedback** — Vollständiger Bidirektionaler Status-Feed (TouchOSC-kompatibel)
- **Art-Net-Merge** — HTP/LTP-Merge von externen Art-Net-Quellen (Backup-Pult)

### GDTF / Fixtures
- **GDTF-Import Phase 2** — Vollständige Attribut-Unterstützung inkl. Sub-Attributes
- **Online-Fixture-Share** — GDTF-Share-Datenbank direkt in der App durchsuchen

---

## Langfristig

### 3D-Visualizer
- **Echtzeit-Beam-Rendering** — Lichtkegel mit Nebel, Gobo-Projektion
- **Stage-Setup-Wizard** — Trusses, Bühnenmaße und Fixture-Positionen per Drag & Drop
- **WYSIWYG-Export** — Fixture-Positionen für externe Visualizer exportieren

### Engine
- **Pixel-Mapping** — Fixture-Grid für LED-Strips und Matrix-Effekte
- **Script-Engine Phase 2** — Vollständige Python-API für Show-Automation
- **Netzwerk-Sync** — Zwei LightOS-Instanzen als Master/Backup synchronisieren

### Platform
- **Linux-Port** — Offizielle Unterstützung (Debian/Ubuntu, Raspberry Pi)
- **macOS-Port** — Offizielle Unterstützung (Apple Silicon)
- **Plugin-System** — Drittanbieter-Plugins für proprietäre Controller und Protokolle

---

## Nicht geplant (vorerst)

- Windows 7/8/10 32-Bit Support (Qt6 erfordert 64-Bit)
- Hardware-Dongle / Lizenzschutz
- Cloud-Backup (Show-Dateien bleiben lokal)
