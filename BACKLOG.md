# LightOS — Backlog (Loop-Modus)

> **Single Source of Truth für den autonomen Loop.** Hier picke ich (Claude) das
> nächste Item; hier wirfst du (David) neue Ideen rein. Weiter oben = höher priorisiert.
> Vision/Langfrist steht in [ROADMAP.md](ROADMAP.md) — dieses Backlog ist die
> *umsetzbare* Kurzliste mit Status & Akzeptanzkriterien.

## Legende
- **Status:** `todo` (offen) · `proposed` (von mir vorgeschlagen, wartet auf dein „go") ·
  `wip` (in Arbeit, Branch existiert) · `review` (PR offen) · `done`
- **Prio:** `P1` hoch · `P2` mittel · `P3` später
- **ID:** `<Bereich>-<NN>` — UI · ENG (Engine) · OUT (Ausgabe) · STAB (Stabilität) · NET (Netzwerk) · VIZ (Visualizer) · QA (Tests/CI)

## Wie du Ideen hinzufügst
Häng einfach eine Zeile unter „Offen" an — Minimum: Titel + 1 Satz, was du willst.
ID, Prio und Akzeptanzkriterien ergänze ich beim Vorschlagen. Oder sag's mir im Chat,
dann trage ich es ein. Reihenfolge = Priorität (verschieb Zeilen nach oben/unten).

---

## 🔧 In Arbeit / Review

| ID | Prio | Status | Titel | Stand |
|----|------|--------|-------|-------|
| UI-02 | P1 | review | Undo im Patch | **Verifiziert:** Fixture-Löschen ist bereits via globalem Ctrl+Z rückgängig (`remove_fixture` pusht Undo+Redo, `patch_view._delete_selected` ruft es undoable). Fehlender Test ergänzt: `tests/test_patch_undo.py` (4 Tests). Branch `feature/patch-undo-test`. |

## 📋 Offen

_Aktuell keine frei eingereihten Items — die nächsten Kandidaten stehen unten unter „Aus Demo-Bau" / „Aus Codex-Reviews". Einzelne Zeilen nach hier oben ziehen, um sie für den Loop zu priorisieren (oder eine neue Idee anhängen)._

### 🔎 Aus Demo-/Anleitungs-Bau (Findings, Session 2026-06-29)
_Beim Bauen der `Hochzeit_Komplett_2026`-Show + Minianleitungen entdeckt. Volle Details (Problem/Fix/DoD) in [`docs/LOOP_FINDINGS_DEMO_BUILD.md`](docs/LOOP_FINDINGS_DEMO_BUILD.md) — wird laufend ergänzt._

| ID | Prio | Status | Titel | Akzeptanzkriterium (Definition of Done) |
|----|------|--------|-------|------------------------------------------|
| DEMO-02 | P2 | done | Generatoren ohne `__main__`-Guard → Windows-Spawn korrumpiert Patch | ✅ Single-Point-Bootstrap `tools/_gen_env.py` (setzt `LIGHTOS_SERIAL_INPROC=1` etc. vor `app_state` → kein `spawn`-Re-Import) + `import _gen_env` in allen 30 bauenden Generatoren. [PR #90](https://github.com/ixamgames-droid/lightos/pull/90) |
| DEMO-03 | P2 | done | `reset_show()` räumt verwaiste `current_show.db`-Patch-Zeilen nicht hart | ✅ `reset_show()` ruft jetzt hart `state.clear_patch()`. [PR #90](https://github.com/ixamgames-droid/lightos/pull/90) |
| DEMO-04 | P2 | done | Bus-gekoppelte Dimmer-Effekte gehen dunkel, wenn der Bus nicht läuft | ✅ Stall-Erkennung in `_advance_step` (dt>0 + Position unverändert → Free-Run statt Einfrieren). [PR #88](https://github.com/ixamgames-droid/lightos/pull/88) |

### 🤖 Aus Codex-Reviews (Stand 2026-06-24 — noch offene Befunde)
_Befunde der Codex-CLI unter den PR-Kommentaren, gegen aktuellen `main` geprüft. Der STAB-/QA-/VIZ-Teil dieses Audits ist via [PR #55](https://github.com/ixamgames-droid/lightos/pull/55) bereits erledigt (siehe „Erledigt" unten) — hier bleiben die 9 noch offenen UI-/ENG-Punkte (alle am 2026-06-30 erneut gegen den aktuellen Code verifiziert: noch real). Verschieb einzelne Zeilen nach oben in die „Offen"-Liste, um sie für den Loop zu priorisieren._

| ID | Prio | Status | Titel | Akzeptanzkriterium (Definition of Done) |
|----|------|--------|-------|------------------------------------------|
| UI-05 | P2 | todo | Programmer-Fokus beim Start initialisieren | `ui/views/programmer_view.py` — `programmer_focus` bleibt `None` (Intensity-Tab feuert kein `currentChanged`) → „Intensity gewinnt" erst nach Tab-Wechsel. Fix: einmal `_on_main_tab_changed(currentIndex())` nach connect; Test. [Codex #9](https://github.com/ixamgames-droid/lightos/pull/9#discussion_r3455648382) |
| UI-06 | P2 | todo | Color-Tab: Default-Köpfe nicht persistieren | `ui/views/programmer_view.py` (`_seed_separate_head`) — Tab-Bau schreibt `ch.default_value` als aktive `color_*#N` → Default/Null landet ungewollt in Szenen/Snaps/Paletten. Fix: nur Anzeige-Fallback, nicht persistieren; Test. [Codex #35](https://github.com/ixamgames-droid/lightos/pull/35#discussion_r3462619556) |
| UI-07 | P2 | todo | QuickBars: Representative-Range nur auf kompatible Fixtures | `ui/views/programmer_view.py` — gemischte Auswahl nutzt einen Fixture-Range als Template für alle → „open"/Strobe schreibt fremden Range-Mittelwert in inkompatiblen Kanal. Fix: QuickBars auf range-kompatible Fixtures filtern; Test. [Codex #28](https://github.com/ixamgames-droid/lightos/pull/28#discussion_r3462419284) |
| UI-08 | P2 | todo | Orientierungs-Tri-State auf Pan/Tilt filtern | `ui/views/programmer_view.py` (`_build_orientation_bar`/`_set_orientation`) — statische Fixtures verfälschen Tri-State + Flags werden auf nicht-fähige Fixtures persistiert. Fix: nur Pan/Tilt-fähige berücksichtigen; Test. [Codex #28](https://github.com/ixamgames-droid/lightos/pull/28#discussion_r3462419288) |
| UI-09 | P2 | todo | Externe Auswahl in ProgrammerView spiegeln | `ui/views/programmer_view.py` — abonniert `SELECTION_CHANGED` nicht → Preset-Browser-Gruppenauswahl im Attribut-Tab unsichtbar/funktionslos. Fix: subscriben + `_selected_fids`/Liste nachziehen; Test. [Codex #13](https://github.com/ixamgames-droid/lightos/pull/13#discussion_r3459492513) |
| ENG-03 | P2 | todo | Palette: Phantom-Köpfe vermeiden | `core/engine/palette.py` (`apply_to_programmer`) — Mehrkopf-Keys auf Einkopf-Fixture schreiben Bogus-`attr#N`, landen in Snaps/Paletten. Fix: Head-Keys gegen echte Kanal-Vorkommen der Ziel-Leuchte filtern; Test. [Codex #20](https://github.com/ixamgames-droid/lightos/pull/20#discussion_r3461923078) |
| ENG-04 | P2 | todo | Palette-Overwrite: stale Werte bereinigen | `ui/views/palette_view.py` + `Palette.record_from_programmer` — selektives Überschreiben merged nur, alte Fixture-Werte bleiben und werden später angewendet. Fix: bei Auswahl-Overwrite nicht-Ziel-fids leeren/ersetzen; Test. [Codex #22](https://github.com/ixamgames-droid/lightos/pull/22#discussion_r3462027119) |
| ENG-05 | P2 | todo | Preset-Browser: Gruppen-Identität (ID/fids statt Name) | `core/engine/preset_search.py` + `app_state` — gleichnamige Gruppen → `select_group_by_name` (`scalar_one_or_none`) scheitert („Gruppe ohne Geräte"). Fix: Gruppen-ID/fids im Eintrag statt nur Name; Lookup per ID; Test. [Codex #13](https://github.com/ixamgames-droid/lightos/pull/13#discussion_r3459492508) |
| ENG-06 | P2 | todo | EFX: Spider-Modus nach Auto-Zuweisung aktualisieren | `ui/views/efx_view.py` (`_auto_assign_if_empty`) — Auto-Zuweisung nur von Spider-Fixtures ruft `_update_spider_mode()` nicht → Spider-Controls bleiben versteckt. Fix: nach Auto-Zuweisung `_update_spider_mode()` aufrufen; Test. [Codex #11](https://github.com/ixamgames-droid/lightos/pull/11#discussion_r3458551131) |

## ✅ Erledigt (Kurz-Log)
_(der Loop verschiebt fertige Items mit PR-Link hierher; Details stehen in [CHANGELOG.md](CHANGELOG.md))_

- **ENG-07** · `prism_rotation` korrekt als **Effect** statt Beam klassifiziert: Der real emittierte Attributname `prism_rotation` (QXF-Import `qxf_import.py`, eingebauter Generic-MH `fixture_db.py`) fiel per Substring-Match `prism` in die **Beam**-Gruppe → falsche Snap/Szenen-Labels für echte Fixtures. Der 2026-06-24-Fix deckte nur die **synthetische, nie emittierte** Kurzform `prism_rot` ab. Jetzt sind beide exakt in der Effect-Menge (Exact-Match in Pass 1 schlägt den Beam-Substring) + deutsches Label „Prisma-Rotation". +2 Tests (classify + Label inkl. Mehrkopf-Suffix `#1`→„Kopf 2"). Volle Suite grün (262 Dateien, 0 Failures/Crashes). Aus den offenen Codex-Befunden (alle 9 verbleibenden am 2026-06-30 als noch-real verifiziert). [PR #89](https://github.com/ixamgames-droid/lightos/pull/89)

- **DEMO-02 / DEMO-03 / DEMO-05** · Demo-Bau-Findings als Batch: **DEMO-02** Generator-Spawn-Korruption — neues Single-Point-Bootstrap `tools/_gen_env.py` setzt vor `app_state`/`output_manager` die spawn-sicheren Env-Schalter (`LIGHTOS_SERIAL_INPROC=1` etc.), `import _gen_env` in allen 30 bauenden `tools/build_*.py` → kein `multiprocessing`-`spawn`-Re-Import des guardlosen Skripts mehr (voller Patch). **DEMO-03** `reset_show()` ruft zusätzlich hart `state.clear_patch()` (verwaiste `current_show.db`-Patch-Zeilen nach Absturz). **DEMO-05** `ColorSequence` iterierbar/indexierbar (`__iter__`/`__getitem__`). +11 Tests, volle Suite grün (264/265, 1 batch-fremder Flake). Parallel via 3 Subagents. [PR #90](https://github.com/ixamgames-droid/lightos/pull/90)

- **DEMO-04** · Bus-gekoppelte Matrix friert nicht mehr **dunkel** ein: Ein an einen Tempo-Bus gekoppelter Matrix-Effekt fror auf der statischen Bus-Position ein, wenn der Bus `bpm>0` hatte, aber nicht vorrückte (Render ohne `advance_frame`-Schleife: Vorschauen/`render_probe`/Validierung/Generatoren/Headless; pausierte Uhr) → bei Dimmer-Style = Intensität 0 = dunkel. `RgbMatrixInstance._advance_step` erkennt den stehenden Bus jetzt am Positions-Delta über einen echten Zeitschritt (`dt>0` + Position unverändert) und fällt auf **Free-Run** (`matrix_speed`) zurück; `dt==0`-Re-Evaluationen (z. B. nach „Jetzt synchronisieren") rechnen weiter Bus-Sync; Bus-Wiederanlauf snappt zurück; globaler Freeze hält an. Live byte-identisch. +6 Tests. [PR #88](https://github.com/ixamgames-droid/lightos/pull/88)

- **UI-13** · VC-Button-Politur (3-in-1): (a) **quadratische Default-Größe** — neu angelegte Buttons sind `72×72` (Pad-Look, grid-aligned) statt länglich `120×60`; nur Neuanlage, Alt-Shows unverändert. (b) **Farb-/Effekt-Vorschau-Badge oben rechts** (analog Gobo): einfarbig = Kreis, Farbwechsel = **animiert durchwechselnd** (Timer nur aktiv wenn sichtbar+mehrfarbig); Dimmer-/Shutter-Style (`has_colors=False`) → kein Badge. (c) **RGBW-Weiß-Erkennung** — zentraler Qt-freier Helfer `color_utils.rgbw_to_display`/`display_rgb_from_attrs` faltet den W-Kanal additiv in die Anzeige-RGB; Snap-Swatch + Badge zeigen reines Weiß als weiß statt schwarz, und `VCColor` faltet W auch beim Senden an Effekt-Farb-Slots (Wurzel von „weißer Effekt = schwarzer Knopf"). +17 Tests, volle Suite grün (261 Dateien). [PR #87](https://github.com/ixamgames-droid/lightos/pull/87)

- **ENG-01** · Cue-Delay **In/Out auf Attribut-Ebene**: Cues hatten bereits eine Pro-Attribut-Verzögerung beim Hineinfaden (`attr_delays`); neu ist das symmetrische `attr_delays_out` fürs Ausfaden. `CueStack._fade_to` wählt jetzt **richtungsabhängig** Fade-Zeit, Cue-Delay-Basis **und** die Pro-Attribut-Delays (GO → `fade_in`/`delay_in`/`attr_delays`, BACK → `fade_out`/`delay_out`/`attr_delays_out`). Nebenbei behoben: der BACK-Fade nahm bisher fälschlich `delay_in` statt `delay_out` als Verzögerungs-Basis. Alt-Shows ohne den neuen Schlüssel verhalten sich unverändert (defensive Deserialisierung). +6 Tests. [PR #78](https://github.com/ixamgames-droid/lightos/pull/78)

- **STAB-08** · Serial-Ausgabe **prozess-isoliert**: die Enttec-Ausgabe läuft jetzt in einem eigenen Prozess (`EnttecProcessProxy` + `serial_process`-Worker). Eine native, in Python **unfangbare** Access Violation im USB-/FTDI-Kerneltreiber killt damit nur den Worker; der Parent respawnt ihn gedrosselt, GUI/Engine laufen weiter. Parent schreibt latest-wins in einen shared `Array` → der 44-Hz-Thread hängt nie mehr an einem Serial-Write. Default an, `LIGHTOS_SERIAL_INPROC=1` erzwingt den In-Prozess-Pfad, Fallback bei Spawn-Fehler. +10 Tests. [PR #75](https://github.com/ixamgames-droid/lightos/pull/75)

- **OUT-02** · Enttec-Serial-Stabilisierung (Fehler-Watchdog): nach `FAIL_LIMIT` (20) aufeinanderfolgenden Schreib-Fehlern wird der Port geschlossen + als tot markiert → kein 44-Hz-Hammern auf ein abgezogenes/wackliges USB-Gerät (drastisch weniger native Access-Violation-Gelegenheiten); ein erfolgreicher Frame resettet den Zähler. Gedrosselter Reconnect (alle 3 s) reaktiviert die Ausgabe automatisch, sobald das USB zurück ist; `is_disabled()` für UI-Status. Reines Python kann eine native Kerneltreiber-AV nicht fangen — der Fix senkt die Exposition. +6 Tests. [PR #73](https://github.com/ixamgames-droid/lightos/pull/73)

- **STAB-07** · Häufigste native Access Violation (crash.log Jun 2026, GUI-Thread im Programmer-Refresh) **ursächlich** behoben: `programmer_view._refresh_fixture_list` kapselt `clear()`+Neuaufbau in `blockSignals` → keine re-entrante `itemSelectionChanged`→`_rebuild_attr_editor`-Kaskade mehr; **und** `_on_state_change` behandelt `patch_changed` nicht mehr → kein Doppel-Rebuild über Legacy- **und** Sync-Pfad. Befund nebenbei: die BUG-01-Bremse `_suppress_emits` ist inert (nie auf `True`). +4 Regressionstests. [PR #70](https://github.com/ixamgames-droid/lightos/pull/70)
- **NET-01 / QA-04** · Quick Wins aus der crash.log-Analyse: Web-Remote startet wieder (`allow_unsafe_werkzeug=True` an `sio.run` — der `WebServer`-Thread starb sonst still beim Start, Remote nie erreichbar) + RGB-Matrix-Style-Sichtbarkeit gegen `AttributeError`-Regression abgesichert (Prod war längst gefixt: `_shut_form_label`; neuer Headless-Test über **alle** `MatrixStyle`×`RgbAlgorithm`). [PR #71](https://github.com/ixamgames-droid/lightos/pull/71)
- **STAB-03** · AV im `programmer_view`-Refresh (Zombie-Subscriber) defensiv abgesichert: `subscribe_widget` mit `weakref` + `shiboken6.isValid`-Guard überspringt/meldet tote Widgets ab. (Die verbleibende **re-entrante** Refresh-Ursache wurde separat als STAB-07 gelöst.) +2 Tests. [PR #37](https://github.com/ixamgames-droid/lightos/pull/37)

- **UI-12 / ENG-08** · Programmer-Matrix: „Farbe pro Runde wechseln" (`color_cycle`) hoch in die Farben-Gruppe (auf RGB/RGBW gegated) **und** neue **Dimmer-Sequenz** für den Dimmer-Chase — explizite Dimmerwerte (z. B. 255/50/100) pro Runde, Pendant zur Farbauswahl: `DimmerSequence` + Checkbox „Dimmer pro Runde wechseln" + Graustufen-Editor, `dimmer_order`/`dimmer_interval`, Cycle-Werte ohne Min/Max-Remap (abwärtskompatibel). +29 Tests, Manifest regeneriert. [PR #60](https://github.com/ixamgames-droid/lightos/pull/60)

- **STAB-04 / STAB-05 / STAB-06** · DMX-Output- & Crash-Erkennungs-Stabilität gehärtet: getimeouteten Output-Thread weitertracken (kein zweiter, konkurrierender DMX-Thread → AV), fatale Exception wird nicht mehr als „sauberer Exit" markiert (Absturz beim nächsten Start erkennbar), Running-Flag pro PID + Windows-sicherer Liveness-Check (OpenProcess statt os.kill). +15 Tests. [PR #55](https://github.com/ixamgames-droid/lightos/pull/55)
- **QA-01 / QA-02 / QA-03** · Test-Gate/CI gehärtet: `pytest-timeout` in den CI-Install-Pfad, sACN-Loopback `fail` statt `skip` nach erfolgreichem Bind, `_delete_selected`-UI-Pfad direkt getestet. [PR #55](https://github.com/ixamgames-droid/lightos/pull/55)
- **VIZ-01 / VIZ-02 / VIZ-03 / VIZ-04** · Visualizer-Lows: 2D-Live-View-Positionen beim Unpatch aufräumen, Spider-Tilt-Default 180° statt 270°, Dock beim Ausrichten/Verteilen lösen, Laser-Fächer-Sichtbarkeit bei View-/Settings-Wechsel reapplien. +5 Tests. [PR #55](https://github.com/ixamgames-droid/lightos/pull/55)
- **UI-03** · Fixture-Kopieren mit Offset: Toolbar-Button „Mit Offset kopieren…" (Dialog Anzahl + Offset), testbare `plan_offset_copies`-Logik (Universe-Überlauf übersprungen), jede Kopie einzeln undoable. +6 Tests. [PR #55](https://github.com/ixamgames-droid/lightos/pull/55)
- **UI-10 / UI-11** · EFX-RANDOM-Vorschau folgt jetzt dem echten `_random_xy`-Walk (wandernde Spur statt geschlossener Schleife; Fixture-Punkte + Spider-Bars numerisch == `EfxInstance._values`) + Fan-Fallback `phase_mode`-bewusst. Letzte Punkte des Programmer-Audits 2026-06-23. _Rein visuelle Feinabnahme im laufenden Programm noch offen._ [PR #51](https://github.com/ixamgames-droid/lightos/pull/51)
- **STAB-02** · Access Violation beim Beenden behoben: `OutputManager.stop()` schließt DMX-Geräte nur nach bestätigtem Thread-Ende (sonst CloseHandle neben WriteFile → AV); `EnttecPro` mit `is_open`-Guard + Purge vor close. +8 Tests. [PR #36](https://github.com/ixamgames-droid/lightos/pull/36)
- **STAB-01** · Crash-Logging „ausgereift": man erkennt jetzt **wann/wie** abgestürzt — Start-/Clean-Exit-Marker, „vorige Sitzung abgestürzt"-Erkennung (deckt native Crashes ab), Standby≠Freeze, `threading.excepthook`, Sturm-Drossel, Qt-Message-Handler, Rotation. Neu `src/core/crash_logging.py` + 18 Tests. [PR #33](https://github.com/ixamgames-droid/lightos/pull/33)
- **UI-01** · Preset-Browser: ein Suchfeld über Paletten **+** Fixture-Gruppen (Name/Typ/Ordner/Tag, Mehrwort-UND), Doppelklick/Enter wendet an. Filterlogik Qt-frei + getestet. [PR #13](https://github.com/ixamgames-droid/lightos/pull/13)
- **OUT-01** · sACN / E1.31: echter UDP-Loopback-Test für die Universe-Ausgabe (`tests/test_sacn_loopback.py`). [PR #14](https://github.com/ixamgames-droid/lightos/pull/14)
- **UI-04** · EFX-Tab: „▶ Start" lief stumm ohne Geräte — neue Bewegung bekommt automatisch Geräte (Auswahl → sonst alle Movingheads), klare Warnung statt No-Op. Root-Cause: `fixtures=[]` → `write()` bricht ab. [PR #11](https://github.com/ixamgames-droid/lightos/pull/11)
- **ENG-02** · Dimmer-Matrix vom Programmer-Intensity entkoppeln („aktiver Tab gewinnt"): Dimmer-Effekt besitzt seinen Kanal wert-unabhängig; Intensity-Tab+Auswahl gewinnt manuell. [PR #9](https://github.com/ixamgames-droid/lightos/pull/9)
