# Show-Datei-Persistenz-Audit — `.lshow` Round-Trip (2026-07-08)

**Auftrag:** AUD-04 — verifizierte Bug-/Risiko-Liste für die Persistenz der Show-Datei
(`src/core/show/show_file.py`, 1089 Zeilen): `save_show` (ZIP mit `show.json`), `load_show`,
`reset_show`. **Datenverlust ist das schlimmste Fehlerbild** — eine Show, die beim Speichern/Laden
still Teile verliert oder korrumpiert, kostet Stunden Arbeit.

**Methode:** 5-Dimensionen-Workflow (Round-Trip-Vollständigkeit · `_lenient`-Ganzblock-Verlust ·
Reset/`_suppress_emits`/Stale-State · Schema/Migration · Save-Integrität), jedes Finding
**adversarial gegen den echten Code verifiziert** (je 2 Skeptiker). **33 Agenten, 14 Roh-Befunde →
12 CONFIRMED, 0 PLAUSIBLE, 2 zurückgewiesen** (davon 6 Duplikate über Dimensionen → **9 distinkte
Defekte**). Zeilennummern gegen `show_file.py` @ `main` (`50422d2`).

## Positiv bestätigt (kein Bug)

- **Round-Trip ist vollständig:** Jeder der **29** von `save_show` geschriebenen Keys wird in
  `load_show`/`reset_show` wieder eingelesen; auch die **Feld-Ebenen** der serialisierten Objekte
  (`_fixture_to_dict`↔`_patched_fixture_from_data`, `_collect`↔`_restore_fixture_groups`, PatternSlot,
  `tempo_grandmaster`, `music_autoshow` inkl. Slots) sind symmetrisch. **Kein Key/Feld geht über einen
  Save/Load-Zyklus still verloren.**
- **`reset_show` leert vollständig:** Alle von `save_show` gesicherten Felder/Manager werden bei „Neue
  Show" geleert (kein Alt-Daten-Bleed); `_suppress_emits` wird in `reset_show` **und**
  `_replace_patch_from_data` per `_prev`/try-finally korrekt gesichert und wiederhergestellt.
- **`executors`- und `tempo_buses`-Serialisierung werfen nicht** (adversarial 2× widerlegt): Beide
  `to_dict()` bauen nur Dicts aus Primitiven unter Lock; die einzige potenziell werfende Operation
  (`cue_stacks.index`) ist bereits intern gefangen → das „leer speichern bei Fehler"-Muster ist dort
  **toter Defensiv-Code**, kein erreichbarer Datenverlust. (Der `functions`-Block ist der Gegen-Fall,
  s. STAB-17.)

---

## Befunde (nach Severity)

### 🔴 P1

| ID | Stelle | Befund | Fix-Richtung |
|----|--------|--------|--------------|
| **STAB-16** | `show_file.py:424-425` | **Nicht-atomarer Direkt-Write → korrupte `.lshow` + vorherige Show zerstört.** `save_show` öffnet `zipfile.ZipFile(path, "w")` — das **truncatet die existierende gute Datei sofort auf 0 Byte** — und ruft `json.dumps(show, …)` (ohne `default=`-Handler) **erst danach INNERHALB** des offenen Handles. Jeder Fehler zwischen Truncate und Close — Absturz/Stromausfall/voller Datenträger **oder** ein `TypeError` aus einem nicht-JSON-serialisierbaren Wert (`programmer`/`base_levels` werden per **Referenz** übernommen, Z. 389/390) — hinterlässt die alte Show zerstört und die neue nur halb geschrieben. Kein `temp+os.replace`, kein Backup — auch nicht im **Autosave**-Pfad. | `json.dumps` **vor** dem Öffnen der Ziel-ZIP (Serialisierungsfehler dann harmlos, Zieldatei unangetastet); in eine Temp-Datei im selben Verzeichnis schreiben und per `os.replace()` **atomar** über den Zielpfad ziehen; `programmer`/`base_levels` vor der Serialisierung defensiv kopieren (`dict(...)`). |
| **STAB-17** | `show_file.py:301-305` | **`functions`-Block wird bei `to_dict()`-Fehler still LEER gespeichert → Totalverlust aller Funktionen inkl. EFX + RGB-Matrix.** Laut Kommentar (Z. 307-311) leben EFX-/Matrix-Instanzen **ausschließlich** im `functions`-Block (`efx_data`/`rgb_data` sind hart leer). `state.function_manager.to_dict()` (Z. 303) baut die Liste in **einer** Comprehension **ohne Per-Funktion-Guard** (`function_manager.py:484-488`; `effect_live.serialization_dict` → `fn.to_dict()`/`deepcopy` ungeschützt). Wirft **eine einzige** defekte Funktion, fängt der breite `except` (Z. 304, **kein** `_lenient`, nicht strict-aware) sie ab, `functions_data` bleibt auf `{"functions": []}` — der Save läuft weiter und schreibt (mit STAB-16 direkt über die gute Datei) einen leeren Block. Beim nächsten Laden sind **alle** Funktionen weg. | Bei Serialisierungsfehler eines nicht-leeren Managers den Save **abbrechen** (Exception weiterreichen), statt still `{"functions": []}` zu speichern. Mit dem STAB-16-Fix (serialize-before-open) fällt das automatisch heraus, wenn der `except` entfernt/hart gemacht wird. |

### 🟠 P2

| ID | Stelle | Befund | Fix-Richtung |
|----|--------|--------|--------------|
| **STAB-18** | `show_file.py:711` (programmer) · `722-730` (base_levels) | **Ein einziger falsch-typisierter Wert löscht den GESAMTEN Block still (Verlust-Amplifikation).** Die inneren Comprehensions `{str(a): int(v) for a, v in attrs.items()}` (programmer, Z. 711) bzw. der `base_levels`-Aufbau (Z. 722-725) sind **nicht** pro-Wert geschützt — obwohl die umgebende Schleife kaputte `fid`/Nicht-dict-`attrs` bewusst **pro Eintrag** überspringt (Z. 706-710). `int(None)`/`int([…])`/`int("255.0")` wirft → äußerer `except` (Z. 714/728) → `state.programmer = {}` bzw. `state.base_levels = {}` (Z. 716/730): die Werte **aller** Fixtures gehen verloren, still (`_lenient` druckt im Normalbetrieb nur). **Zusatz (base_levels):** `state._rebuild_render_plan()` (Z. 727) steht **innerhalb desselben try, nach** der `base_levels`-Zuweisung → ein aus **unabhängigem** Grund werfender Render-Plan-Rebuild löscht `base_levels` mit **und** kippt `implicit_brightness`. | `int(v)` pro Wert kapseln (inneres `try/except continue`, analog zur `fid`/`attrs`-Prüfung); Ergebnis erst am Ende zuweisen. `_rebuild_render_plan()` **aus** dem `base_levels`-`try` **heraus** ziehen (eigener Aufruf, damit ein Render-Fehler nicht die geladenen Daten verwirft). |
| **STAB-19** | `show_file.py:688-…` (load_show) | **`load_show` setzt nicht reset-first zurück und ist nicht atomar → „Frankenstein-Show" bei Fehler mitten im Laden.** Der Patch wird zuerst ersetzt (`_replace_patch_from_data`), danach folgen ~20 Blöcke. Wirft ein früher Block (oder eine ungefangene Stelle), bleibt **neuer Patch + alter Rest** (alte Cue-Stacks/Executors/Programmer/Palettes) inkonsistent stehen — kein Rollback, kein „erst komplett zurücksetzen". Zusätzlich ist **`palettes`** der einzige Manager, der **nur bei vorhandenem Key** geladen wird (kein `else`-Reset) → beim Laden einer Show **ohne** `palettes`-Key überleben die Farbpaletten der **Vorshow** (STAB-19b). | `load_show` mit `reset_show()`-first (oder Snapshot+Rollback bei Fehler) atomar machen; `palettes` unbedingt auf den geladenen Wert (bzw. leer) setzen, nicht nur bei vorhandenem Key. |

### 🟡 P3

| ID | Stelle | Befund | Fix-Richtung |
|----|--------|--------|--------------|
| **STAB-20** | `show_file.py` (mehrere) | **Robustheits-Bündel gegen alte/korrupte `.lshow`:** (a) **Non-Object-JSON** — ein gültiges JSON, das kein Objekt ist (`list`/`null`/`string`), führt zu unbehandeltem `AttributeError` (`data.get(...)`) statt sauberer Fehlermeldung. (b) **Kein Versions-Gate** — eine zu neue/unbekannte `SHOW_VERSION` wird still als aktuelles Format fehlinterpretiert (statt Warnung). (c) **Legacy-EFX/RGB-Migration** (`~829-840`) bricht beim **ersten** kaputten Eintrag ab und verliert **alle folgenden** (statt pro Eintrag zu überspringen). | (a) Am Anfang von `load_show` prüfen, dass `data` ein `dict` ist → sonst klarer `ValueError`. (b) `read_show_version` gegen `SHOW_VERSION` prüfen, bei neuerer Version warnen/gaten. (c) Migrationsschleifen pro Eintrag kapseln (wie `cue_stacks`). |

---

## Zusammenfassung

Der **Round-Trip selbst ist vollständig** und `reset_show` sauber — es geht bei normalem Speichern/Laden
kein Feld verloren. Die echten Defekte liegen in der **Fehler-Behandlung**: `save_show` kann eine gute
Datei **still durch eine korrupte/leere ersetzen** (STAB-16/17, **P1** — Datenverlust bei Crash bzw.
einer einzigen kaputten Funktion), und der Ladepfad **amplifiziert einen einzelnen kaputten Wert zum
ganzen Block** (STAB-18) bzw. hinterlässt bei Fehler einen inkonsistenten Zustand (STAB-19). Empfehlung:
**STAB-16 + STAB-17 zusammen** als erste Fix-Runde (beide in `save_show`, gemeinsame Wurzel „still lossy
über gut schreiben" — atomarer `temp+os.replace` mit `serialize-before-open` behebt beide), dann STAB-18
(Per-Wert-Robustheit), dann STAB-19/20.
