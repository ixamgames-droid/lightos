# VIZ-12 — Ziel-Design: EIN VisualizerService + Dauerfenster

Phase 2 aus `docs/VIZ3D_OVERHAUL_PLAN.md`. Baut strikt auf VIZ-10 (Selbstheilung, Slot-Guard, RenderCrashGuard) und VIZ-11 (SceneGraph-Adapter, Undo-Command-Layer, Stage-Echo-Token, dict-only-Invariante) auf — nichts davon wird zurückgedreht.

## 0. Verifizierte Ground-Truth (READ-ONLY geprüft)

- **Zwei-Bridge-Zwei-Timer-Realität bestätigt.** `visualizer_window.py:1687` (`_setup_channel`) und `visualizer_view.py:112` bauen je eine eigene `VisualizerBridge` + `QWebChannel` + `QWebEngineView`; `_setup_update_timer` (1765) und `visualizer_view.py:44` erzeugen je einen `QTimer(33ms)`. `_push_dmx_updates` (1771 vs. 182) ist byte-gleiches Copy-Paste, **N Signale/Tick, kein Dirty-Check**.
- **Fenster wird bei jedem Öffnen zerstört.** `main_window.py:1326 _open_visualizer` ruft `close()` + `deleteLater()` + `VisualizerWindow(self)` neu — außer der VIZ-10-Dialog bricht `close()` ab (`False`), dann nur `raise_()`.
- **`_release_state` (2822) = endgültiges Teardown** mit `_dmx_released=True`; `showEvent` (2848) startet den Timer explizit NICHT neu, wenn dieses Flag gesetzt ist (dokumentierter Code-Vertrag). `closeEvent` (2892) ruft immer `_release_state`.
- **hideEvent (2856) stoppt nur den Timer** (Subscriber bleibt) — das gewünschte „CPU sparen ohne Rebuild"-Muster existiert bereits, ist aber nicht an echtes Re-Open angeschlossen.
- **Qt-Fakt (bestätigt `stage_scene.html:3435`):** `new QWebChannel(qt.webChannelTransport, …)` — `qt.webChannelTransport` wird pro `QWebEnginePage` von `setWebChannel()` injiziert; ein `QWebChannel` ist an **genau eine Page** gebunden. `registerObject` ist rein additiv (kein Ownership-Transfer); ein QObject kann in zwei Channels registriert werden, aber `Signal.emit()` liefert dann an **beide** Pages ohne Ziel-Routing.
- **JS `dmxUpdated`-Handler (3440):** `bridge.dmxUpdated.connect(j => { const d=JSON.parse(j); updateFixture(d.fid, …) })` — **ein Objekt pro Signal**. `updateFixture(fid,r,g,b,intensity,pan,tilt,heads)` (1845).
- **Live-View-Call-Sites:** `live_view.py:1353 _set_view_3d` (direkter Umschalt-Pfad) UND `live_view.py:2028 _set_active` (Tab-Sichtbarkeits-Timer) rufen beide `on_shown()/on_hidden()`.
- **Dict-only-Invariante (VIZ-11, eisern):** `_pop_fixture_scene_state` (130) und die gesamte Bridge-Datenlogik arbeiten nur über `state.visualizer_positions/_docks/_rotations`-Dicts; Tests fahren `SimpleNamespace`-Fakes ohne `state._scene`. **Der Service darf diese Invariante nicht brechen** — er kapselt Serialisierung/Takt, nicht das Datenmodell.

---

## (a) VisualizerService-API + Ownership

### Ownership & Lebensort
- **Ein Singleton**, gehalten am `AppState` (nicht am MainWindow — Fenster/Live-View sind beide nur Konsumenten und dürfen den Service überleben). Zugriff über `get_visualizer_service()` analog `get_state()`; lazy beim ersten Konsumenten erzeugt. Der Service besitzt **den einen Takt (`QTimer 33 ms`)**, das **Dirty-Tracking (Snapshot-Cache)** und die **Serialisierung**. Er besitzt bewusst **KEINE** `QWebEngineView`/`QWebChannel` — die leben pro Render-Target (WebGL-Kontext ist unvermeidlich pro Page).
- Der Service abonniert den `AppState` **genau einmal** (der VIZ-11-`_on_state`-Prune läuft künftig service-seitig, nicht mehr pro Bridge doppelt). Damit verschwindet die Doppel-Subscription, die `_release_state`/`WindowReleaseStateTest` heute absichern.

### API (Skizze)
```
class VisualizerService(QObject):
    def instance() -> VisualizerService          # Singleton am AppState

    # Target-Registrierung (Fenster + Spiegel docken an)
    def attach_target(target: VisualizerTarget) -> None
    def detach_target(target: VisualizerTarget) -> None
    def set_target_active(target, active: bool) -> None   # Sichtbarkeit/Push-Relevanz

    # Takt-Steuerung (aggregiert über alle Targets)
    def _tick() -> None            # EIN Snapshot -> Dirty-Diff -> EINE Batch-Message
    def _ensure_timer() -> None    # läuft nur wenn >=1 aktives Target existiert
    def force_full_resync(target=None)   # nach Reload/show_loaded: Dirty-Cache leeren

    # Zustands-Pushes (heutige Bridge-Push-Signaturen bleiben erhalten!)
    def push_stage_definition(defn); push_settings(s); push_edit_mode(m); push_view_mode(m)
    def reset_interaction_state()  # zentral: stop_trace + Reload-Guard reset (§ Punkt 4)
```
`VisualizerTarget` ist ein dünnes Frontend (s. (c)): hält seine eigene `QWebEnginePage` + `QWebChannel` + `RenderCrashGuard` und exponiert genau die `Signal`-Slots, die JS erwartet. Der Service ruft `target.emit_batch(json)` / `target.emit_stage(json)` etc. — **er entscheidet, welche Targets ein Push bekommen** (aktiv/sichtbar), Qt gibt ihm das nicht geschenkt.

### Wie erreichen die Konsumenten den Service
- **`VisualizerWindow`**: holt beim `__init__` `get_visualizer_service()`, erzeugt sein `VisualizerTarget`, `service.attach_target(self._target)`. Kein eigener `QTimer` mehr, kein eigenes `_push_dmx_updates`, kein eigenes State-Subscribe. `showEvent → set_target_active(True)`, `hideEvent → set_target_active(False)`.
- **`Visualizer3DView` (Spiegel)**: identisch — eigenes `VisualizerTarget`, `attach`/`detach` in `on_shown`/`on_hidden`. Kein eigener Timer/Bridge/Subscribe mehr. Der `destroyed`-Backstop (`visualizer_view.py:124`) entfällt (der Service stirbt NICHT mit dem Widget); stattdessen `detach_target` in `on_hidden` + ein `destroyed`→`detach`-Backstop.
- **`main_window`**: `_open_visualizer` zeigt/raised nur noch (s. (b)); `closeEvent` behält den VIZ-10-Veto-Pfad, ruft aber zusätzlich beim **echten App-Ende** `service.shutdown()` (der einzige verbleibende „vollständige Teardown"-Pfad — löst das State-Subscribe endgültig).

---

## (b) Ziel-Zustandsdiagramm Fenster-Lifecycle

```
                 App-Start
                    │  (Fenster NICHT vorab gebaut — lazy)
                    ▼
             ┌─────────────┐   _open_visualizer (erstes Mal)
             │ NIE GEÖFFNET │ ───────────────────────────────►┐
             └─────────────┘                                  │
                                                              ▼
   ┌────────────────────────── show()/raise_() ────────► ┌────────┐
   │                                                      │ OFFEN  │  ← Target aktiv,
   │                                                      │(sicht- │    Service pusht Batch
   │  _open_visualizer (Fenster existiert)                │ bar)   │
   │  ── hide() ◄── closeEvent (VIZ-10-Veto ok) ──────────┤        │
   ▼                                                      └───┬────┘
┌────────┐   showEvent → set_target_active(True)              │ Renderer-Crash
│HIDDEN  │ ◄──────────────────────────────────────────────┐  │ (renderProcessTerminated)
│(Target │   hideEvent → set_target_active(False)          │  ▼
│inaktiv,│ ── Target bleibt attached, Page lebt ──────────┐│ ┌──────────────┐
│Page    │                                                ││ │ CRASHED      │ RenderCrashGuard
│lebt)   │                                                ││ │ (auto-reload │ (≤3×/60s, PRO Page)
└───┬────┘                                                ││ │  ≤3×/60s)    │
    │ closeEvent (VIZ-10-Veto ok) → hide()                ││ └──────┬───────┘
    │  (KEIN _release_state, KEIN deleteLater)            ││        │ loadFinished ok
    ▼                                                     ││        ▼ force_full_resync(target)
 (bleibt HIDDEN, wiederöffenbar ohne Rebuild)             │└──► zurück zu OFFEN
                                                          │  Aufgeben (>3×): Statusmeldung,
   App-Ende: service.shutdown() → einziger echter        │  bleibt OFFEN-aber-tot (kein Loop)
   Teardown (State-Unsubscribe), Prozess-Exit killt Timer─┘
```

**Kernänderungen ggü. heute:**
1. `closeEvent`: Veto-Abfrage (`_confirm_close_with_unsaved_stage`) **bleibt unverändert**. Bei „weiter" ruft es **`hide()` statt `_release_state()`**. `event.ignore()`+`hide()` (das Fenster soll ja am Leben bleiben) — konkret: `event.ignore(); self.hide()` ODER `super().closeEvent` nach vorherigem `hide`-Umbau; das `_dmx_released`-Flag entfällt komplett.
2. `_open_visualizer`: wenn Fenster existiert → `show(); raise_(); activateWindow()`. Kein `close()`/`deleteLater()`/Neubau mehr. Neubau nur noch, wenn `self._visualizer_window is None` (nie geöffnet).
3. **„Szene neu laden"** wird ein expliziter Menüpunkt im Fenster: ruft `target.reload_page()` (der einzige Ort, der noch `load_stage_html` mit Cache-Buster fährt) + danach `service.force_full_resync(target)`. Der Cache-Buster-Zwang bei jedem `show()` entfällt.
4. **VIZ-10-Selbstheilung bleibt pro Target/Page** (s. (c)) — Crash im Fenster reloadet nur die Fenster-Page, nicht die Spiegel-Page.

**Windows-Gotcha (adressiert):** `showEvent`/`hideEvent` feuern auch bei Minimieren/Restore. Da der Push jetzt nur „aktiv/inaktiv" schaltet (kein Rebuild, kein Subscribe-Toggle) ist ein ungewolltes Pausieren beim Minimieren harmlos (Fenster ist eh nicht sichtbar) und beim Restore läuft der Push sofort wieder an. Kein `_dmx_released`-Fallstrick mehr.

---

## (c) Bridge-Architektur-Entscheidung: **2 dünne Frontends über 1 Service-Kern**

**Entscheidung: ZWEI Bridge-Frontends (je eine `VisualizerBridge`-Instanz pro Page) über EINEM Service-Kern — NICHT eine Bridge in zwei Channels.**

**Begründung aus den Qt-Fakten:**
- Ein `QWebChannel` ist an **genau eine Page** gebunden (`qt.webChannelTransport` ist pro Page injiziert, `stage_scene.html:3435`). Für zwei Pages braucht es zwangsläufig **zwei Channels** — das ist nicht wählbar.
- Man *könnte* dieselbe Bridge-Instanz in beide Channels `registerObject`-en (additiv, erlaubt). Dann liefert aber `Signal.emit()` **immer an beide Pages** — kein Ziel-Routing möglich. Das kollidiert mit drei harten Anforderungen:
  1. **Batch nur an aktive Targets** (Constraint 5 / Akzeptanz „statische Szene ≈ 0 Push-Last, verstecktes Fenster keine Serialisierung"): eine geteilte Bridge kann einen Push nicht an der versteckten Page vorbeischicken.
  2. **Pro-Target-Reload-Token** (`_stage_reload_token`, `_last_stage_echo_token`, `_reloading_stage`): zwei Chromium-Prozesse reloaden unterschiedlich schnell. Ein geteilter Zähler in EINER Bridge würde Echos aus Page A fälschlich für Page B als aktuell/stale werten (genau die Race-Klasse, die VIZ-11 pro Page gelöst hat) — die Token-Zustandsmaschine **muss pro Page bleiben**.
  3. **Pro-Page-Settings/Edit-Mode**: Fenster im „Bauen"-Modus, Spiegel im „Ansehen"-Modus gleichzeitig über dieselbe Szene — `editModeChanged`/`settingsChanged` müssen ziel-getrennt sein.

**Konsequenz — klare Schichtung:**
- **`VisualizerService` (Kern, page-agnostisch):** State-Subscribe (einmal), Snapshot-Erzeugung, Dirty-Diff, EINE Serialisierung pro Tick, die Undo-Command-Aufrufe (VIZ-11), Stage-Definition-Resolve. Der Kern serialisiert **einmal** und übergibt das fertige JSON an alle relevanten Targets → **keine doppelte Serialisierung** (Constraint 3 erfüllt).
- **`VisualizerBridge` (dünnes Frontend, eine Instanz pro Page):** behält ihre **heutigen Signal/Slot-Signaturen 1:1** (`dmxUpdated`, `stageLoaded`, `editModeChanged`, `requestFixtures`, `pyFixtureMoved`, …) — **darum bleiben fast alle VIZ-11-Tests grün** (sie testen Bridge-Datenlogik, nicht Timer/Channel-Anzahl). Neu: die Bridge zieht ihre Snapshot-/Emit-Aufrufe nicht mehr aus einem eigenen Timer, sondern bekommt sie vom Service. Der pro-Page-Zustand (`_reloading_stage`, `_stage_reload_token`, `_last_stage_echo_token`, `_reload_guard_timer`, `_render_crash_guard`) **bleibt in der Bridge/im Target** — genau da, wo er hingehört.
- **`RenderCrashGuard` bleibt pro Page** (eine Instanz je Target) — Chromium-Crashes sind renderprozess-/page-lokal.

Damit ist die Bridge weiterhin JS-facing und dict-only (VIZ-11-Invariante unberührt), der Service ist der neue, testbare, page-freie Kern.

---

## (d) Batch-Protokoll Python → JS

**Heute:** N × `dmxUpdated.emit(json.dumps({fid,r,g,b,intensity,pan,tilt,heads?}))` pro Tick, JS: `updateFixture(d.fid, …)`.

**Ziel: EIN Array-Signal pro Tick, nur wenn Dirty.**

### Message-Format (rückwärtskompatibler Payload pro Element)
```jsonc
// neues Signal: dmxBatch(json)   — json = Array der GEÄNDERTEN Fixtures
[
  { "fid": 12, "r": 255, "g": 128, "b": 0, "intensity": 255, "pan": 130, "tilt": 90 },
  { "fid": 13, "r": 0,   "g": 0,   "b": 255, "intensity": 255, "pan": 128, "tilt": 128,
    "heads": [ {"r":..,"g":..,"b":..,"cr":..,"cg":..,"cb":..,"cw":..,"tilt":..}, {...} ] }
]
```
Das Pro-Element-Objekt ist **byte-identisch** zum heutigen `push_dmx_update`-Payload (inkl. Spider-`heads`). Nur die Verpackung (Array statt Einzelsignal) ist neu → JS-Änderung minimal.

### Dirty-Tracking (Service-Kern, pro Fixture)
- Service hält `self._last_payload: dict[fid, dict]`. Pro Tick baut er den Payload je Fixture (heutige `push_dmx_update`-Logik ins Service verschoben), vergleicht mit `_last_payload[fid]`. **Nur geänderte** kommen ins Array. Kein geändertes Fixture → **kein Signal** (statische Szene = 0 Push-Last, Constraint 5 + Akzeptanz).
- **Vergleich = value-equality des serialisierten Dicts** (nicht Objekt-Identität). Der `heads`-Sub-Payload wird mitverglichen.
- `force_full_resync()` leert `_last_payload` → nächster Tick pusht alle (nach Reload/Stage-Wechsel/Target-neu-attached), damit eine frisch geladene Page nicht auf die nächste DMX-Änderung warten muss.
- **Pro-Target-Dirty:** Ein neu sichtbar gewordenes Target braucht den vollen Stand, ein dauerhaft sichtbares nur die Diffs. Lösung: `_last_payload` ist **service-global** (eine Szene), aber `attach_target`/`set_target_active(True)` setzt für DIESES Target ein „needs_full"-Flag → beim nächsten Tick bekommt nur dieses Target das volle Array, die anderen das Diff. So bleibt es bei EINER Serialisierung pro geändertem Fixture; nur die Array-Zusammenstellung pro Target unterscheidet sich (billiger dict-Lookup, keine Re-Serialisierung des Fixtures).

### JS-Handler-Änderung (minimal, additiv/rückwärtskompatibel)
```js
// stage_scene.html ~3440: dmxBatch NEBEN dmxUpdated (Alt-Signal bleibt für Tests)
if (bridge.dmxBatch) bridge.dmxBatch.connect(j => {
  const arr = JSON.parse(j);
  for (const d of arr) {
    updateFixture(d.fid, d.r, d.g, d.b, d.intensity, d.pan||128, d.tilt||128, d.heads||null);
  }
});
```
`updateFixture` selbst **unverändert**. `dmxUpdated` (Einzelsignal) bleibt als Bridge-Signal bestehen (kein Bruch für Tests, die es direkt emittieren) — der Live-Pfad nutzt nur noch `dmxBatch`.

---

## (e) Migrations-/Kompat-Plan für Tests

**Grün-bleibend ohne Änderung** (testen reine Datenlogik / Dirty-Flags / Reload-Token über `SimpleNamespace`, unabhängig von Timer-Anzahl, solange Bridge-Signaturen erhalten bleiben): `test_visualizer_state_leaks.py`, `test_viz10_ui_repairs.py`, Großteil `test_viz11_bridge_fixes.py`. **Die dict-only/SimpleNamespace-Invariante bleibt hart** — der Service kapselt Takt/Serialisierung, greift NIE auf `state._scene` zu, arbeitet über dieselben Dicts.

**Muss umgeschrieben werden (2 Tests — bewusst falsch geworden):**
1. `test_visualizer_leak.py::WindowReleaseStateTest::test_release_state_unsubscribes_both` — Prämisse „close = beide Subscriber weg" gilt nicht mehr (Fenster hat gar keinen eigenen `_on_state` + keine eigene Bridge-Subscription mehr; das Subscribe lebt im Service). **Ersetzen** durch `ServiceShutdownUnsubscribesTest`: `service.shutdown()` meldet den EINEN Service-Subscriber ab; `hide()`/`detach_target` melden NICHTS ab (Background-Live-Updates bleiben). Zusätzlich neuer Test: `attach`/`detach` mehrfach → genau ein Subscriber, kein Leak.
2. `test_viz10_stability.py::MainWindowRespectsVetoTest::test_open_visualizer_replaces_window_on_confirmed_close` — asserted `deleteLater()` bei confirmed close; VIZ-12 schafft das ab. **Ersetzen** durch `test_open_visualizer_shows_existing_window`: bei existierendem Fenster wird `show()/raise_()/activateWindow()` gerufen, `deleteLater` NICHT.

**Anzupassen (Ziel-Methode umbenannt, Struktur bleibt):** `test_viz10_stability.py::CloseEventIntegrationTest` mockt `_release_state` und prüft „bei confirmed close aufgerufen, bei cancel nicht". Der Veto-Pfad bleibt strukturell identisch, aber `closeEvent` ruft künftig `hide()` statt `_release_state`. → Mock-Ziel auf die neue Handhabung umstellen (z.B. `self.hide` mocken und prüfen „bei confirm aufgerufen / bei cancel `event.ignore()`"). `test_open_visualizer_keeps_window_on_cancel` und `test_main_close_event_ignored_when_visualizer_vetoes` **bleiben gültig** (Veto-Semantik unverändert).

**Neue Tests (Kern-Neuwert):** `test_viz12_service.py` — (a) Dirty-Diff: unveränderter Snapshot → kein `dmxBatch`; (b) EIN geändertes Fixture → Array mit genau einem Element, identischer Pro-Element-Payload wie altes `push_dmx_update`; (c) `force_full_resync` → nächster Tick voll; (d) zwei Targets, eins inaktiv → nur das aktive bekommt Batch; (e) Timer läuft nur bei ≥1 aktivem Target; (f) Spider-`heads` im Batch erhalten. Alle über `SimpleNamespace`-State + Emit-Stub (wie `test_visualizer_state_leaks.py`), **ohne echtes QWebEngine**.

---

## (f) implementation_steps

Siehe strukturierte `implementation_steps` — jeder Schritt für sich grün (Test-Gate), analog VIZ-11-Schnitt.

## (g) / (h)

Siehe `risks` und `open_questions`.


---

## Orchestrator-Entscheidungen (2026-07-03, bindend)

1. **Zwei-Target-Modus-Konflikt:** Fuer VIZ-12 unkritisch (Spiegel-View bleibt view/edit-only, kein Szenegraph-mutierender Modus dort). VOR VIZ-13 (Gizmo ueberall) explizit re-pruefen — als Punkt in die VIZ-13-Runde uebernehmen.
2. **Service-Timer bei 0 aktiven Targets:** HART stoppen. Der Patch-Prune laeuft event-getrieben ueber den State-Subscribe, nicht ueber den Timer.
3. **dmxUpdated-Einzelsignal:** bleibt in VIZ-12 als Kompat-/Test-API bestehen (Live-Pfad nutzt nur noch dmxBatch); Entfernung als expliziter Cleanup-Punkt der VIZ-13-Runde.
4. **"Szene neu laden"-Menuepunkt:** laedt BEIDE Pages (Fenster + aktives Spiegel-Target) frisch + service.force_full_resync — der Menuepunkt verspricht die Szene, nicht ein Fenster.
5. **Singleton-Ownership:** am AppState (get_visualizer_service(state)) — frischer State in Tests = frischer Service; kein Modul-Global.
