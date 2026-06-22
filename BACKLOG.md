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
| UI-02 | P1 | review | Undo im Patch | **Verifiziert:** Fixture-Löschen ist bereits via globalem Ctrl+Z rückgängig (`remove_fixture` pusht Undo+Redo, `patch_view._delete_selected` ruft es undoable). Fehlender Test ergänzt: `tests/test_patch_undo.py` (4 Tests). Branch `feature/patch-undo-test`. |

## 📋 Offen

| ID | Prio | Status | Titel | Akzeptanzkriterium (Definition of Done) |
|----|------|--------|-------|------------------------------------------|
| UI-01  | P1 | todo | Preset-Browser | Suchfeld über Paletten + Gruppen; Treffer per Doppelklick anwenden; Test deckt Filterlogik ab |
| UI-03  | P2 | todo | Fixture-Kopieren mit Offset | Mehrere Geräte mit Adress-Abstand patchen; Dialog (Anzahl + Offset) + Test |
| ENG-01 | P2 | todo | Cue-Delay In/Out auf Attribut-Ebene | Pro-Attribut `delay_in`/`delay_out` (Cue-Ebene existiert bereits); Render-Test |
| OUT-01 | P1 | todo | sACN / E1.31 Ausgabe | Universe per sACN senden; Ziel-IP + Universe konfigurierbar; Loopback-Test |
| OUT-02 | P2 | todo | Enttec Open DMX USB Stabilisierung | Kein Drift/Hang über lange Sessions (>8h); Reconnect-Logik; Doku |

## ✅ Erledigt (Kurz-Log)
_(der Loop verschiebt fertige Items mit PR-Link hierher; Details stehen in [CHANGELOG.md](CHANGELOG.md))_

- **ENG-02** · Dimmer-Matrix vom Programmer-Intensity entkoppeln („aktiver Tab gewinnt"): Dimmer-Effekt besitzt seinen Kanal wert-unabhängig; Intensity-Tab+Auswahl gewinnt manuell. [PR #9](https://github.com/ixamgames-droid/lightos/pull/9)
