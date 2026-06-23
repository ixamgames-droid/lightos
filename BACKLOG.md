# LightOS — Backlog (Loop-Modus)

> **Single Source of Truth für den autonomen Loop.** Hier picke ich (Claude) das
> nächste Item; hier wirfst du (David) neue Ideen rein. Weiter oben = höher priorisiert.
> Vision/Langfrist steht in [ROADMAP.md](ROADMAP.md) — dieses Backlog ist die
> *umsetzbare* Kurzliste mit Status & Akzeptanzkriterien.

## Legende
- **Status:** `todo` (offen) · `proposed` (von mir vorgeschlagen, wartet auf dein „go") ·
  `wip` (in Arbeit, Branch existiert) · `review` (PR offen) · `done`
- **Prio:** `P1` hoch · `P2` mittel · `P3` später
- **ID:** `<Bereich>-<NN>` — UI · ENG (Engine) · OUT (Ausgabe) · STAB (Stabilität) · NET (Netzwerk) · VIZ (Visualizer)

## Wie du Ideen hinzufügst
Häng einfach eine Zeile unter „Offen" an — Minimum: Titel + 1 Satz, was du willst.
ID, Prio und Akzeptanzkriterien ergänze ich beim Vorschlagen. Oder sag's mir im Chat,
dann trage ich es ein. Reihenfolge = Priorität (verschieb Zeilen nach oben/unten).

---

## 🔧 In Arbeit / Review

| ID | Prio | Status | Titel | Stand |
|----|------|--------|-------|-------|
| STAB-01 | P1 | wip | Crash-Logging „ausgereift" (wann/wie erkennbar) | **Umgesetzt, Chat-Review:** neues `src/core/crash_logging.py` + `main.py`-Verdrahtung. Start-Banner, Clean-Exit-Marker, „vorige Sitzung abgestürzt"-Erkennung (running.flag + last_alive.txt → deckt native Crashes ab), Standby-vs-Freeze-Trennung im Watchdog, `threading.excepthook` (Worker-Crashes), Fehler-Sturm-Drossel, `qInstallMessageHandler`, Log-Rotation. 18 neue Tests, volle Suite grün (1851). Branch `feature/crashlog-maturity`. |
| UI-02 | P1 | review | Undo im Patch | **Verifiziert:** Fixture-Löschen ist bereits via globalem Ctrl+Z rückgängig (`remove_fixture` pusht Undo+Redo, `patch_view._delete_selected` ruft es undoable). Fehlender Test ergänzt: `tests/test_patch_undo.py` (4 Tests). Branch `feature/patch-undo-test`. |

## 📋 Offen

| ID | Prio | Status | Titel | Akzeptanzkriterium (Definition of Done) |
|----|------|--------|-------|------------------------------------------|
| STAB-02 | P1 | todo | AV beim Beenden: DMX-Output schreibt nach Serial-Close | `OutputManager.stop()` prüft `is_alive()` nach `join(timeout=2)` nicht → DMX-Thread schreibt nach `CloseHandle()` weiter → Access Violation (crash.log 21.+22.6.). Fix: Thread garantiert beenden (Event + harter Join) **vor** `dev.close()`; `EnttecPro.send_dmx` mit `is_open`-Guard. Aus crash.log-Analyse 23.6. |
| STAB-03 | P1 | todo | AV in programmer_view-Refresh (Zombie-Subscriber / cross-thread) | `sync.emit` ruft Subscriber synchron ohne GUI-Marshalling; `clear()` auf bereits gelöschtem QListWidget → AV (crash.log 21.+23.6.). Fix: `_refresh_*_list` mit `try/except RuntimeError` absichern (wie `_refresh_sliders_from_state`); `efx_view._notify_change` über `app_state._emit` marshallen. Aus crash.log-Analyse 23.6. |
| UI-03  | P2 | todo | Fixture-Kopieren mit Offset | Mehrere Geräte mit Adress-Abstand patchen; Dialog (Anzahl + Offset) + Test |
| ENG-01 | P2 | todo | Cue-Delay In/Out auf Attribut-Ebene | Pro-Attribut `delay_in`/`delay_out` (Cue-Ebene existiert bereits); Render-Test |
| OUT-02 | P2 | todo | Enttec Open DMX USB Stabilisierung | Kein Drift/Hang über lange Sessions (>8h); Reconnect-Logik; Doku |

## ✅ Erledigt (Kurz-Log)
_(der Loop verschiebt fertige Items mit PR-Link hierher; Details stehen in [CHANGELOG.md](CHANGELOG.md))_

- **UI-01** · Preset-Browser: ein Suchfeld über Paletten **+** Fixture-Gruppen (Name/Typ/Ordner/Tag, Mehrwort-UND), Doppelklick/Enter wendet an. Filterlogik Qt-frei + getestet. [PR #13](https://github.com/ixamgames-droid/lightos/pull/13)
- **OUT-01** · sACN / E1.31: echter UDP-Loopback-Test für die Universe-Ausgabe (`tests/test_sacn_loopback.py`). [PR #14](https://github.com/ixamgames-droid/lightos/pull/14)
- **UI-04** · EFX-Tab: „▶ Start" lief stumm ohne Geräte — neue Bewegung bekommt automatisch Geräte (Auswahl → sonst alle Movingheads), klare Warnung statt No-Op. Root-Cause: `fixtures=[]` → `write()` bricht ab. [PR #11](https://github.com/ixamgames-droid/lightos/pull/11)
- **ENG-02** · Dimmer-Matrix vom Programmer-Intensity entkoppeln („aktiver Tab gewinnt"): Dimmer-Effekt besitzt seinen Kanal wert-unabhängig; Intensity-Tab+Auswahl gewinnt manuell. [PR #9](https://github.com/ixamgames-droid/lightos/pull/9)
