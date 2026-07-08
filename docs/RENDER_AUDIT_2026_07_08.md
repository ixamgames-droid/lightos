# Render-Pfad-Audit — `AppState._render_frame` (2026-07-08)

**Auftrag:** AUD-02 — verifizierte Bug-/Risiko-Liste für den **heißesten Thread der App**:
den Per-Frame-Renderer `AppState._render_frame` (`src/core/app_state.py`, ~Z. 1250–1663). Er
läuft als tick-Callback im **Output-Loop-Thread** (`output_manager.add_tick_callback`, ~Z. 1190)
und mischt jeden Frame komplett neu: Default → Funktionen → Executoren (Cues) → Programmer
(LTP) → implizite Grundhelligkeit → multiplikativer Dimmer-/Feature-Master → Art-Net/sACN-Input
→ Simple-Desk-Override → Laser-Estop → atomarer Commit ins Live-Universe. Historische AV-Quelle
(STAB-07).

**Methode:** 6-Dimensionen-Workflow (Concurrency/Lock-Disziplin · Exception-Isolation ·
Clamp/Overflow · Merge-Reihenfolge/Priorität · Commit/Freigabe · Test-Coverage), jedes Finding
**adversarial gegen den echten Code verifiziert** (je 2 Skeptiker, angewiesen zu widerlegen).
**36 Agenten, 15 Roh-Befunde → 6 CONFIRMED, 2 PLAUSIBLE, 7 zurückgewiesen.** Zeilennummern
gegen `src/core/app_state.py` @ `main` (`e11d18c`) geprüft.

## Positiv bestätigt (kein Bug)

- **Kein Thread-Death durch Exception:** Eine Exception in `_render_frame` kann den Output-Thread
  **nicht** beenden — die tick-Callback-Schleife fängt jeden Callback einzeln
  (`output_manager.py:269-273`, `try: cb(...) except Exception: pass`) und `_send_all` läuft in
  `_loop`s eigenem try/except. Die vom Scout vermuteten Wurf-Szenarien
  (`fixture_dimmers`/`feature_dimmers`=None) sind durch die `float()`-geklammerten Setter +
  Show-Reset unerreichbar; `_apply_fixture_map` hat int-Guards, `submaster` eigene try/except.
- **Wert-/Adress-Clamp lückenlos:** `Universe.set_channel` (`universe.py:44-52`) verwirft Adressen
  außerhalb 1..512 und klemmt Werte 0..255 **ohne `assert`** (robust unter `python -O`) — die
  zentrale letzte Instanz für **alle** dynamischen Schreibpfade. Die zwei clamp-umgehenden
  `set_range`-Aufrufe (Schritt 1 mit `_default_frame`, Schritt 5 Commit) speisen beweisbar
  exakt-512-lange, vorgeklemmte Daten mit `start-1+length ≤ 512`. Auch `int(get_channel(a)*factor)`
  (Z. 1528) ist durch die [0,1]-Clamps aller Faktoren überlauf-sicher (NaN/negativ/>1 ausgeschlossen).
- **Grand Master ist ein Intensitäts-Master, kein Kill-Switch (by design):** Dass der GM auf einem
  gepatchten Universum **nur** Intensity-/Color-Adressen skaliert (nicht Pan/Tilt/Gobo/Shutter/Mode
  und nicht Roh-Script-Kanäle), ist dokumentierte Absicht (`output_manager.py:293-295`, „Audit B4":
  sonst führen Moving Heads bei GM<100% falsche Positionen aus) und entspricht Standard-Pult-Semantik.
  Die Asymmetrie zum Blackout-Button (der via `bytes(512)` wirklich alles nullt) ist gewollt;
  Laser-Sicherheit hängt am dedizierten Estop-Pfad (Stage 4d), nie am GM. **Adversarial 2×
  zurückgewiesen.**
- **Laufender Effekt „besitzt" seinen Nicht-Intensitäts-Kanal (WP-6, by design):** Dass der Color-Tab
  eine laufende Matrix-/Farb-Effekt-Farbe **nicht** übersteuert (`protect = func_driven`, Z. 1424 +
  `_apply_fixture_map` Z. 1729), ist der spezifizierte Kontrakt. Die `intensity_wins`-Ausnahme ist
  bewusst eng und nur intensitäts-spezifisch begründet (Selektion setzt Intensity auto auf 0, was eine
  Dimmer-Matrix killen würde — ein Problem, das Farbkanäle nicht haben). **Adversarial 2×
  zurückgewiesen** (Feature-Request, kein Defekt — siehe ENG-Idee unten).
- **Test-Coverage des Render-Pfads ist tatsächlich breit** (korrigiert die Backlog-Annahme „nur
  `test_render_frame.py`"): Der Pfad ist über **≥ 8 dedizierte Suiten** abgedeckt — `test_input_layer.py`
  (HTP/LTP-Input inkl. Free-Channel-Release), `test_iso_simple_desk.py` (Override an/aus, Zombie,
  Clamp), `test_feature_dimmer.py` (Stacking-Produkt, Feature-Klassifikation), `test_matrix_dimmer_master.py`
  (ENG-02 `intensity_wins`), `test_laser_dmx_estop.py` (Estop-Dunkelschaltung), `test_programmer_priority.py`
  (WP-6 protect), `test_strict_dimmer_render.py`, `test_dimmer_master.py`. **Fünf** als „ungetestet"
  gemeldete Stufen wurden adversarial zurückgewiesen, weil die Tests bereits existieren.

---

## Befunde (nach Severity)

### 🟠 P2

| ID | Stelle | Befund | Fix-Richtung |
|----|--------|--------|--------------|
| **STAB-13** | `app_state.py:1542` (+ Writer `1777/1779/1784`) | **`feature_dimmers` wird im Renderer in-place iteriert, aber lock-frei von UI-Threads mutiert.** Stage 4b² baut `active = [s for s in fd_slots.values() …]` direkt über `self.feature_dimmers` — ohne Snapshot/Lock. Ändert ein UI-Thread währenddessen die **dict-Größe** (`set_feature_dimmer` legt einen Slot an / `pop`t ihn beim Schwellen-Crossing über 0.999; `clear_feature_dimmers` beim Show-Load), wirft CPython `RuntimeError: dictionary changed size during iteration`. Der Block ist **nicht** in try/except → Exception steigt auf, wird erst im Output-Loop geschluckt → der Commit (Schritt 5) läuft für diesen Frame **nie** → alle Universen behalten den Vorframe. Bei Show-Load / anhaltendem Slider-Drag ein realer, wiederholbarer Dropped-Frame-Stutter. `feature_dimmers` ist die **einzige** Render-Ebene ohne Lock-Snapshot (programmer/simple_desk/input werden alle unter Lock gezogen). | `_fd_lock` einführen (analog `_prog_lock`/`_sd_lock`/`_input_lock`); `set_feature_dimmer`/`clear_feature_dimmers` unter Lock schreiben; im Renderer vor Z. 1542 unter Lock snapshotten (`fd_slots = list(self.feature_dimmers.values())`). |
| **STAB-14** | `app_state.py:675` (Reset) ↔ `1653-1662` (Konsum) | **Repatch verwirft die Engine-Extra-Freigabeliste → Roh-Kanal bleibt dauerhaft hängen (Zombie).** Eine `ScriptFunction` schreibt per `setdmx` einen **nicht gepatchten** Roh-Kanal (z. B. U1/Adr 100 = 255); der Commit merkt sich `_engine_extra_prev[1]={100}` (Z. 1662), um ihn später wieder auf 0 freizugeben. Ein Patch-Change ruft `_rebuild_render_plan`, das `_engine_extra_prev` **hart auf `{}` zurücksetzt** (Z. 675) — **ohne** die Live-Werte zu nullen (kein `universe.clear()` im Repatch-Pfad). Stoppt das Skript danach, ist `prev=None`, die Bedingung `if cur or prev` (Z. 1656) falsch → **keine Freigabe** → `live[100]` bleibt für immer 255 (nur durch Blackout temporär maskiert), bis eine andere Quelle die Adresse beschreibt oder die App neu startet. Auf einem Strobe-/Shutter-/Beam-Kanal ein sicht- und sicherheitsrelevanter Dauer-An. | In `_rebuild_render_plan` `_engine_extra_prev` **nicht** blind verwerfen: entweder das Tracking über Repatches erhalten (dann released der nächste Frame korrekt), oder beim Repatch die bisher gemerkten Roh-Adressen der betroffenen Universen einmal aktiv auf 0 committen, bevor geleert wird. Zugriff auf `_engine_extra_prev` unter denselben Renderer-Snapshot/Lock stellen (cross-thread gelesen Z. 1655 / geschrieben Z. 675/1662). |

### 🟡 P3

| ID | Stelle | Befund | Fix-Richtung |
|----|--------|--------|--------------|
| **STAB-15** | `app_state.py:669-672` (Rebind) ↔ `1259/1267/1648/1653` (Lese) | **Der Patch-Render-Plan wird beim Re-Patch/Show-Load ungelockt und nicht-atomar getauscht.** `_rebuild_render_plan` rebindet `_fix_index`/`_default_frame`/`_commit_spans`/`_patched_set`/`_engine_extra_prev` als **fünf separate Statements ohne Lock** (UI-Thread), während `_render_frame` dieselben Felder lock-frei quer über den Frame liest (`_default_frame` früh in Schritt 1, `_commit_spans`/`_patched_set` spät in Schritt 5). Fällt ein GIL-Switch genau zwischen die Rebinds während der Renderer zwischen Schritt 1 und 5 steht, mischt ein Frame alte + neue Strukturen → ein **Spurious-/dunkler Wert** an einer eben umgepatchten Adresse (z. B. alter Base-Level als Roh-Kanal committet). Selbstheilend im Folgeframe, **kein** Crash/Datenverlust, nur bei **manuellem** Umpatchen (nicht im laufenden Playback); Zeitfenster winzig. Deckt auch `torn-render-plan-one-frame-glitch` (dieselbe Wurzel) ab. | Die zusammengehörigen Plan-Strukturen zu **einem** unveränderlichen Snapshot-Objekt (`RenderPlan`-namedtuple) bündeln und in `_rebuild_render_plan` mit **einem** atomaren Rebind tauschen; `_render_frame` zieht am Frame-Anfang genau einmal `plan = self._plan`. Alternativ ein `_plan_lock` um Rebind + Frame-Kopf. |

### 🧪 Coverage (klein, echt — der Rest war schon abgedeckt)

| ID | Stelle | Lücke | Test-Vorschlag |
|----|--------|-------|----------------|
| **QA-25** | `app_state.py` Render-Fail-Safe + Engine-Extra | (a) **Fail-Safe:** kein Test belegt, dass eine Exception in einer **ungeschützten** Stage (4/4a²/4b/4b²/Commit) den zuletzt committeten Frame stehen lässt statt halb zu committen (Trigger nur via API-Umgehung, daher niedrig). (b) **Multi-Universe-Engine-Extra-Release** + der **Patch-Wechsel-Zombie** aus STAB-14 sind ungetestet (alle bestehenden Render-Tests nutzen nur Universe 1). (c) **EE-02 prog_factor-Multiply** auf einem **Color-only-Fixture** (RGB ohne Dimmer, Effekt treibt Farbe, Programmer-Intensity multipliziert → ~`color*factor`) — der einzige EE-02-Pfad ohne Test. | (a) Universe-Stub, dessen `set_channel` in einer späten Stage wirft → asserten, dass ein zuvor committeter Wert erhalten bleibt. (b) 2 Universen mit Roh-Script in beiden, in einem stoppen → nur dort Release; + Repatch-Zombie-Regression (nach STAB-14-Fix). (c) Color-only-Fixture, Effekt→color_r=200, programmer intensity=128 → assert ~100 (Multiply, nicht 128, nicht 200). |

---

## ENG-Idee (aus zurückgewiesenem Merge-Befund, kein Bug)

- **Manuelles Farb-Override analog zu `intensity_wins`:** Aktuell lässt sich ein bewusst selektiertes
  Fixture im Color-Tab nicht umfärben, solange ein Farb-Effekt darauf läuft (WP-6 schützt den Kanal —
  by design). Für Intensität ist der „Nutzer will manuell übersteuern"-Fall über `intensity_wins`
  gelöst, für Farbe (und andere Features) nicht. **Optionale** Konsistenz-Erweiterung: ein
  feature-spezifisches `<focus>_wins` (aktiver Tab entspricht einer `func_driven`-Feature-Gruppe UND
  Fixture selektiert → betroffene Adressen aus `protect` discarden). Bewusst als P-niedrig / Produkt-
  Entscheidung markiert, **kein** Korrektheitsdefekt.

---

## Zusammenfassung

Der Render-Pfad ist grundsätzlich **robust** gebaut: Thread-am-Leben (Callback-Isolation),
Wert-/Adress-Clamp zentral und lückenlos, Commit atomar (scratch getrennt von live), Merge-Ordnung
bewusst und dokumentiert, Coverage breit. Die einzigen zwei echten Defekte betreffen **nebenläufigen
Zustand rund um `feature_dimmers` und `_engine_extra_prev`** (STAB-13/14, P2) plus den ungelockten
Plan-Swap (STAB-15, P3) — allesamt an der Grenze zwischen dem lock-freien Render-Thread und den
UI-Threads, die Patch/Slots mutieren. Empfehlung: STAB-13 und STAB-14 als nächste Fix-Runden
(klein, testbar), STAB-15 danach; QA-25 als begleitende Coverage-Ergänzung.
