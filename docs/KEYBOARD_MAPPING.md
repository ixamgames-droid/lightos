# Keyboard-Mapping in der Virtual Console (Feature 8)

Tastatur-Tasten lassen sich — zusätzlich zu MIDI — auf VC-Buttons patchen.

## Bedienung

1. Virtual Console → **Edit-Modus** → Rechtsklick auf einen Button →
   **„⌨ Taste zuweisen…"**
2. Im Lern-Dialog die gewünschte Taste/Kombination drücken
   (z. B. `F5`, `Strg+B`, `Shift+Leertaste`). Esc bricht ab.
3. **Übernehmen** — der Button zeigt die Taste klein oben links an
   (`⌨F5`). **„Bindung entfernen"** löscht sie.

Verhalten: Tastendruck = wie MIDI-Note-On, Loslassen = Note-Off. Damit
funktionieren **Toggle** und **Flash** exakt wie über MIDI (Flash bleibt nur
gedrückt aktiv). Die Bindung wird mit dem VC-Layout in der Show gespeichert.

## Konflikte & Sicherheit

- **Konfliktprüfung:** Ist die Taste schon von einem anderen Widget belegt,
  warnt der Dialog (mit Name des Widgets). Bewusste Doppelbelegung ist
  erlaubt — dann lösen beide aus (z. B. Gruppen-Flash).
- **Kritische Aktionen** (Blackout, Stop All) werden im Lern-Dialog rot
  gekennzeichnet: die Taste wirkt sofort und ohne Rückfrage.
- **Textfelder bleiben ungestört:** Hotkeys feuern nicht, wenn der Fokus in
  einem Eingabefeld liegt (QLineEdit/QTextEdit/SpinBox/editierbare Combo)
  oder ein modaler Dialog offen ist.
- Auto-Repeat (Taste halten) löst nicht mehrfach aus.

## Technik

- Zentraler App-Event-Filter: `src/core/input/keyboard_hotkeys.py`
  (`KeyboardHotkeyFilter`, Singleton). Die VC-Canvas abonniert ihn und
  verteilt `(Sequenz, gedrückt)` an die Widgets der **aktiven Bank** —
  identische Architektur wie der MIDI-Pfad.
- Sequenz-Strings sind Qt-`QKeySequence`-PortableText (`"Ctrl+F5"`).
- Release-Zustellung ist robust: auch wenn der Modifier vor der Taste
  losgelassen wird, bekommt der Button sein Release (die beim Press
  gesendete Sequenz wird pro Taste gemerkt).

## Grenzen: zweite USB-/Makro-Tastatur

- **Windows/Qt unterscheidet Tastaturen nicht.** Alle Tastaturen liefern
  denselben Event-Strom; eine zweite USB-Tastatur ist von der Haupttastatur
  nicht unterscheidbar. Das Mapping funktioniert trotzdem — nur eben für
  beide Tastaturen gleich (stabile Fallback-Lösung).
- **Empfehlung für Makro-Boards:** Tasten des Boards auf `F13`–`F24` oder
  ungewöhnliche Kombinationen (`Strg+Alt+F1` …) programmieren — die kommen
  auf der Haupttastatur praktisch nicht vor, damit ist das Board faktisch
  exklusiv.
- **Möglicher Ausbau (nicht implementiert):** Windows Raw Input
  (`WM_INPUT`/`GetRawInputDeviceList`) liefert pro Event ein Geräte-Handle
  und könnte Tastaturen trennen. Das erfordert einen nativen
  Message-Hook neben Qt (z. B. via `ctypes`/`QAbstractNativeEventFilter`)
  und ist als Erweiterung in `keyboard_hotkeys.py` vorgesehen
  (Subscriber-API bleibt dafür stabil).
- Hotkeys sind **app-intern**: sie feuern nur, solange LightOS den Fokus
  hat. OS-globale Hooks wurden bewusst nicht eingesetzt.
