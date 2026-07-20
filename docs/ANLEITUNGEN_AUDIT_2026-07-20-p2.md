# Anleitungen-Audit — 2026-07-20 · Phase 2 (ältere Standalone-Docs)

Fortsetzung des [Kern-Audits](ANLEITUNGEN_AUDIT_2026-07-20.md) (12/12 Kern-Anleitungen,
PR #380). Phase 2 prüft die **älteren Standalone-Docs** außerhalb des
[`ANLEITUNGEN.md`](ANLEITUNGEN.md)-Index gegen den aktuellen Quellcode.

## Methode

Wie Phase 1: konkrete UI-/API-Aussagen (Enum-Werte, Label-Literale, Modul-/Klassennamen,
Attribut-Keys) gegen `src/` verifiziert. Reine Show-Layout-Beschreibungen (Demo-`.lshow`) und
historische Bug-/Test-Logs sind **nicht code-prüfbar** und wurden nicht angefasst (Triage unten).

## Ergebnis

| Doc | Ergebnis |
|---|---|
| MATRIX_LIVE.md | ⚠️→✅ „Algorithmen-Katalog (17)" → **18**; Schachbrett/CHECKER-Zeile ergänzt (rgb_matrix.py:53). |
| MOVING_HEADS.md | ✅ aktuell — ZQ02001-Kanal-/Farbrad-/Gobo-/Strobe-/Reset-Tabellen matchen fixture_db.py exakt; UI-Module (gobo_icons, ShutterQuickBar/GoboQuickBar/ColorWheelAutoBar) bestätigt. |
| APC_SCHRITT_FUER_SCHRITT.md | ⚠️→✅ §12: tote VC-Baukasten-Knöpfe als historisch markiert + Redirect. |
| APC_TEST_SHOW.md | ⚠️→✅ §6b: dito. |
| anleitung_vc_elemente/ANLEITUNG_VC_ELEMENTE.md | ⚠️→✅ Sektion „Baukasten-Knöpfe" (inkl. „Neu: Chase auf Gruppe") als historisch markiert. |
| KEYBOARD_MAPPING.md | ✅ aktuell — KeyboardHotkeyFilter-Singleton, „⌨ Taste zuweisen…", ⌨-Indikator bestätigt. |
| LIVE_EDIT.md | ✅ aktuell — Edit-Slot-Kern (effect_live.set/get_edit_target, edit_slot-Feld) bestätigt. |
| PROFI_MODUS.md | ✅ aktuell — Show-Layout (self-verifizierend); referenzierte EFX/Effect-Live-APIs bestätigt. |

## Zwei Fund-Cluster (alle korrigiert)

1. **MATRIX_LIVE.md — Algorithmus-Zahl:** „17" → **18** (die `RgbAlgorithm`-Enum hat 18 Werte;
   **Schachbrett** fehlte). → Commit `ca60de1`.
2. **Tote VC-Baukasten-Knöpfe (⌗ Controller / 🎨 Color-Chase / 🟦 Chase-Bereich):** in mehreren
   Docs noch als aktuell beschrieben. **3-fach verifiziert entfernt:** (a) VC-Toolbar
   (`virtual_console_view.py` = 16er-Widget-Palette → ↶/↷, keine Baukasten), (b) Canvas-Kontextmenü
   „Hinzufügen" (`vc_canvas.py:1657` = nur Einzel-Widgets), (c) src-weit kein Builder/Emoji/
   „Chase-auf-Gruppe"-Dialog. Controller-Vorlage heute über den Controller-Browser (Sektion *MIDI*).
   Betroffene Docs als historisch markiert + Redirect: `apc_schritt` (`8d5eddf`), `apc_test_show` +
   `anleitung_vc_elemente` (`bd5bf8b`). *(Die Kern-Anleitung `anleitung_vc` war bereits in PR #380
   korrigiert.)*

## Triage — bewusst nicht angefasst (nicht code-prüfbar)

- **Historische Logs:** `APC_PROBIER.md` (Hardware-Test-Bug-Log, „Stand 2026-06-11").
- **Show-Layout-Beschreibungen** (Inhalt lebt in der jeweiligen `.lshow`, self-verifizierende
  Generatoren): `APC_SEITEN_UEBERSICHT.md`, `KOMPLETT_DEMO.md`, `NEUE_DEMO.md`, `PARTY_DEMO.md`,
  `MASTER_DEMO.md`.
