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
| STAB-03 | P1 | wip | AV in programmer_view-Refresh (Zombie-Subscriber) defensiv absichern | **Umgesetzt:** Befund — der Zombie-Fall war in `sync.emit` (RuntimeError-Selbstheilung) + `subscribe_widget`(destroyed) schon abgedeckt, und `efx_view._notify_change` läuft via `QTimer` ohnehin im GUI-Thread (kein cross-thread). Verbleibende Lücke: Qt löscht das C++-Objekt mitunter VOR dem destroyed-Signal → nativer Zugriff = AV. Fix: **Validitäts-Guard** in `subscribe_widget` (schwache Ref + `shiboken6.isValid`) überspringt + meldet tote Widgets ab. Rein additiv (lebende Views unverändert). 2 neue Tests. Branch `fix/sync-widget-validity-guard`. |
| UI-02 | P1 | review | Undo im Patch | **Verifiziert:** Fixture-Löschen ist bereits via globalem Ctrl+Z rückgängig (`remove_fixture` pusht Undo+Redo, `patch_view._delete_selected` ruft es undoable). Fehlender Test ergänzt: `tests/test_patch_undo.py` (4 Tests). Branch `feature/patch-undo-test`. |

## 📋 Offen

| ID | Prio | Status | Titel | Akzeptanzkriterium (Definition of Done) |
|----|------|--------|-------|------------------------------------------|
| ENG-01 | P2 | todo | Cue-Delay In/Out auf Attribut-Ebene | Pro-Attribut `delay_in`/`delay_out` (Cue-Ebene existiert bereits); Render-Test |
| OUT-02 | P2 | todo | Enttec Open DMX USB Stabilisierung | Kein Drift/Hang über lange Sessions (>8h); Reconnect-Logik; Doku |

### 🤖 Aus Codex-Reviews (Stand 2026-06-24 — noch offene Befunde)
_Befunde der Codex-CLI unter den PR-Kommentaren, gegen aktuellen `main` geprüft. Der STAB-/QA-/VIZ-Teil dieses Audits ist via [PR #55](https://github.com/ixamgames-droid/lightos/pull/55) bereits erledigt (siehe „Erledigt" unten) — hier bleiben die 10 noch offenen UI-/ENG-Punkte. Verschieb einzelne Zeilen nach oben in die „Offen"-Liste, um sie für den Loop zu priorisieren._

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
| ENG-07 | P2 | todo | attr_groups: `prism_rotation` als Effect klassifizieren | `core/attr_groups.py` — emittiertes `prism_rotation` (DB/QXF) fällt per Substring in Beam statt Effect → falsche Snap/Scene-Labels für echte Fixtures. Fix: `prism_rotation` zur Effect-Gruppe + Test. [Codex #30](https://github.com/ixamgames-droid/lightos/pull/30#discussion_r3462490379) |

## ✅ Erledigt (Kurz-Log)
_(der Loop verschiebt fertige Items mit PR-Link hierher; Details stehen in [CHANGELOG.md](CHANGELOG.md))_

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
