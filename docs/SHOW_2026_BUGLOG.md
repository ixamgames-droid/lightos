# Bug-Log — Testshow-2026-Bau (Live-Session 2026-06-15)

Gesammelt beim Bauen/Filmen der Testshow (8 PAR + 2 MH + 2 Spider). Nach Fertigstellung
der Show der Reihe nach abarbeiten und betroffene Anleitungen aktualisieren.
Schweregrad: 🔴 blockierend · 🟠 stört · 🟡 kosmetisch/UX · 🔵 Verbesserungsidee.

---

## BUG-01 ✅ BEHOBEN (2026-06-16) — Nativer Crash beim **Neuladen** einer Show (load_show → add_fixture → programmer_view)
**Status:** Gefixt. Emit-Koaleszierung umgesetzt: neuer `AppState._suppress_emits`-Guard in
`_emit()` (unterdrückt alle State-Events, solange gesetzt), aktiviert in
`_replace_patch_from_data()` (show_file) während des kompletten Patch-Ersatzes und im `finally`
wieder zurückgesetzt. `load_show()` **und** `reset_show()` machen danach wie bisher EINEN
gebündelten Refresh (`patch_changed` + `sync.refresh_all()`). Damit feuert kein `add_fixture()`
mehr re-entrant `PATCH_CHANGED` mitten im inkonsistenten Patch. **Deckt auch den Autosave-Reload
ab** (läuft über denselben `load_show`-Pfad). Tests: `tests/test_app_state_emit_suppress.py`
(Guard) + `tests/test_show_file.py::test_patch_replace_suppresses_emits_during_rebuild`
(Vertrag) — 9/9 grün, breiterer Show-Lade-Lauf 38/38 grün.

**Symptom:** Ist bereits eine Show geladen und man lädt per `Datei → Öffnen` (Ctrl+O) eine
andere/dieselbe Show, stürzt LightOS **nativ ab** (Prozess verschwindet, kein Python-Traceback,
faulthandler-Dump in `%APPDATA%/LightOS/crash.log`). **Erst-Laden aus leerem Zustand ist harmlos.**

**Crash-Stack (faulthandler):**
```
programmer_view.py:596  _refresh_effects_list   (self._effects_list.clear())
programmer_view.py:179  _sync_refresh
programmer_view.py:151  <lambda>  (SyncEvent.PATCH_CHANGED → _sync_refresh)
core/sync.py:76         emit
core/app_state.py:1306  _emit_impl
core/app_state.py:211   add_fixture
core/show/show_file.py:129  _replace_patch_from_data
core/show/show_file.py:463  load_show
main_window.py:1159     _open_show_path
```

**Ursache:** `load_show()` → `_replace_patch_from_data()` ruft pro Fixture `add_fixture()`, das
**synchron** `PATCH_CHANGED`/`REFRESH_ALL` emittiert. `programmer_view` hängt mit
`_sync_refresh` (→ `_refresh_fixture_list` + `_refresh_group_list` + `_rebuild_attr_editor` +
`_refresh_effects_list`) daran. Bei 12 Fixtures läuft dieser schwere Rebuild **12× re-entrant
mitten im Laden**, während alte Funktionen/Effekte ab- und neue aufgebaut werden →
Access Violation in den QListWidget-Operationen (flaky, GC/Qt-Timing). Deckt sich mit dem
bekannten Muster (früher `_refresh_fixture_list`), siehe Memory `reference_lightos_ui_automation`.

**Repro:** Show A laden → nochmal Ctrl+O dieselbe/andere `.lshow` → Crash (reproduzierbar beim
Neuladen mit laufenden Funktionen).

**Workaround (Session):** Show nur in eine **frisch gestartete** App laden (App neu starten statt
in-place neu laden).

**Fix-Idee (Schluss-Phase):** Während `load_show` die Patch-/Funktions-Emits **koaleszieren**
(einmal am Ende statt pro `add_fixture`), ODER in `programmer_view` einen `_loading`-Guard, der
`_sync_refresh` während des Ladens unterdrückt und **einmalig** per `QTimer.singleShot(0, …)` nach
Abschluss ausführt. (Gleiches Guard-Muster wie im Programmer-Load-Guard-Fix.)

---

## HINWEIS-02 🔵 — APC-LED-Feedback muss manuell aktiviert werden
**Beobachtung:** Nach dem Laden leuchten die APC-Pads erst, nachdem man in der Virtual-Console-
Leiste den Schalter **„APC LEDs"** einschaltet. Für Endnutzer unintuitiv.
**Fix-Idee:** Bei erkanntem APC mini (mk2) das LED-Feedback standardmäßig aktivieren, oder beim
Show-Laden den letzten Zustand merken. Bis dahin: in der **Anleitung apc_mapping** als ersten
Schritt dokumentieren.

---

<!-- Weitere Befunde während des Baus hier anhängen: BUG-03, … -->
