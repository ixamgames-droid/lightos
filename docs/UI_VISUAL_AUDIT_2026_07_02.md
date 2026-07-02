# UI-Visual-Audit 2026-07-02 (Optik + Bedienbarkeit)

> Autonome Loop-Runde (Davids Auftrag: „visuell anschauen, was wir ändern können, damit's besser aussieht + einfachere Bedienbarkeit").
> **Methode:** Da die Computer-Use-Freigabe nicht verfügbar war, lief der Audit **headless**: das echte `MainWindow` (inkl. globalem Dark-QSS) wurde offscreen mit geladener Demo-Show (`shows/demo_apc_mk2.lshow`) durch alle 8 Hauptsektionen + Sub-Tabs geschaltet und gerendert (15 Screenshots, 1440×900, Segoe-UI-Font-Bootstrap gegen Offscreen-Tofu), dazu ~50 Einzel-Renderings aller Views/VC-Widgets/Live-Edit-Sonderfälle. Zwei unabhängige Audit-Agents (Linsen: Optik/Konsistenz · Bedienbarkeit/Klarheit) + eigene Verifikation jedes P1-Befunds am Screenshot. **Grenze der Methode:** keine Interaktion (Hover/Drag/Dialoge), keine echten Fenstergrößen-Wechsel — ein interaktiver GUI-Nachpass per Computer Use bleibt sinnvoll.

## ✅ Was gut aussieht (kein Handlungsbedarf)
- **Simple Desk**: Kanal-Fader-Bank mit Geräte-Farbgruppierung ist klar und live-tauglich.
- **Virtuelle Konsole (Run)**: Farb-Buttons + Badges + Fader sauber; Bibliothek-Panel konsistent.
- **Live-Edit-Widget (PR #131)**: Farb-/Dimmer-Stufen-Felder rendern korrekt (RGB-Balken bzw. Graustufen), responsives Breit-Layout + einzeilige Tempo-Zeile funktionieren, „Anzeige:"-Toggles sichtbar.
- 2D-Bühnen-Layout: Fixture-Marker + Labels + Zoom-HUD klar.

## 🔴 Bestätigte Befunde (P1/P2 — von mir am Screenshot verifiziert)

| # | Befund | Beleg | Fix-Skizze |
|---|--------|-------|-----------|
| A1 | **Sektions-Tab-Beschriftungen clippen** in JEDER Ansicht („Bühnen-Lay", „Programm", „Virtual Cons", „Simple Des", „Eingabe / Aus" bei 1440 px) — Kernnavigation schwer scanbar | `mw_simple_desk.png` u. a. | Section-Buttons: Breite aus `sizeHint` der Beschriftung statt fixer Breite; bei Platzmangel elidieren + Tooltip; ggf. kürzere Titel („Bühne", „E/A") |
| A2 | **Grand-Master-Prozent liest sich als „00%"** — Slider-Griff überlappt die erste Ziffer; wichtigster Sicherheitsregler schlecht ablesbar | `mw_simple_desk.png` Kopfzeile | Label rechts vom Slider mit fester Mindestbreite (z. B. `min-width` für „100%") und Abstand, nie unterm Griff |
| A3 | **EFX-View: Buttonleiste unter der Effektliste unlesbar geclippt** („Ne/eic/sch/Sta/St") + Mini-Buttons in „Custom Path" ebenso | `mw_programmer_efx.png` | Buttons auf `minimumSizeHint` statt harter Breite; Vorbild: Matrix-View daneben (voll lesbar „Neu/Löschen/Start/Stop") |
| A4 | **Checkbox-Indikatoren im Dark-Theme fast unsichtbar** (Live-Edit-Picker: unangehakt = keinerlei sichtbare Box) | `mle_a_edit_narrow_400x520.png` | `QCheckBox::indicator` im Live-Edit-QSS (und ggf. global) mit 1px hellem Rand `#8b949e` auch unchecked |
| A5 | **Rohe interne Tokens als UI-Text über den Live-Editor hinaus**: Programmer-Matrix-Combo zeigt `normal`; VCStepper zeigt Param-Key `runner_count` als Untertitel; VCEncoder zeigt `speed` | `view_RgbMatrixView_*.png`, `vcwidget_VCStepper.png`, `vcwidget_VCEncoder.png` | Options-Label-Map aus dem Live-Editor (VCL-03, `_OPTION_LABELS`) in die Meta-Schicht (`rgb_matrix_meta`/`vc_effect_meta`) hochziehen und in Programmer-Combos + Widget-Untertiteln nutzen |
| A6 | **Programmer-Leerzustand**: „Kein Gerät ausgewählt" doppelt übereinander + ohne Handlungshinweis (trotz Geräten in der Liste links) | `mw_programmer_intensity.png`, `view_ProgrammerView_withshow.png` | Eine Meldung mit Anleitung („Gerät links anklicken…"), Doppel-Label entfernen |
| A7 | **Live-View-Kopfzeile zählt falsch**: „0 Geräte im Patch" direkt nach Konstruktion trotz gepatchter Geräte (Subscribe ohne Initial-Pull; `live_view.py:1414/2457`) | `view_LiveView_withshow.png` | `_refresh_info()` einmal am Ende von `__init__` aufrufen (Bug-Klasse wie UI-05/UI-09) |
| A8 | **Sprachmischung**: Preset-Kategorien englisch („Color", „Beam") neben deutschen Nachbarn; VC-Widget-Titel „Cue List" vs. „Cueliste" im Playback | `view_PresetBrowserView_empty.png`, `vcwidget_VCCueList.png` | Kategorie-/Titel-Labels vereinheitlichen (Anzeige-Mapping, keine Datenmigration) |

## 🟡 Kleinere Befunde (P3 — plausibel, nicht einzeln verifiziert)
- **Live-Edit breit**: Vorschau vertikal zentriert statt oben ausgerichtet → Leerraum wirkt unfertig (`mle_b_edit_wide_900x520.png`). Fix: Top-Alignment der Vorschau-Spalte. *(eigener Befund, verifiziert)*
- DMX-Monitor: rote Kanal-Rahmen ohne Legenden-Eintrag + schwacher Kontrast (`mw_dmx_monitor.png`).
- Leere Hauptansichten (Show Manager, Playback, BPM) ohne Empty-State-Hinweis — wirken „kaputt" statt leer.
- BPM „Erkennungsqualität"-Balken bei 0 % ohne sichtbare Kontur.
- Aktive Sektion nur per dünnem Unterstrich erkennbar (zusammen mit A1 doppelt ungünstig).
- VCColorList: zwei konkurrierende Leerzustands-Hinweise („— kein Ziel —" + „(keine Farbliste)").
- Statuszeile „Enttec: nicht gefunden" ohne Klickweg zu den Output-Einstellungen.
- Bibliotheks-Punkt-Farbcode (gelb/blau) ohne Tooltip-Erklärung.

## ❌ Geprüfte Nicht-Befunde (nicht wieder aufmachen)
- **„Dropdown und Effekt-Header im Live-Edit stimmen nicht überein"** (Audit-Agent-Meldung zu `mle_c/d`): Artefakt des Render-Skripts (`ed._current` direkt gesetzt, `_refresh_nav` umgangen). Alle echten Bedienpfade (−/+, Dropdown, Drop) synchronisieren Combo und Body. Kein Bug.
- **Helle Einzel-View-Renderings** (`gallery/view_*`): Artefakt — das globale Dark-QSS hängt am MainWindow (`main_window.py:228`); Standalone-Instanzen erben es nicht. Im echten Fenster ist alles dunkel (belegt durch `gallery_mw/*`).
- **„Blackout-Button abgeschnitten im VC-Edit"**: Canvas-Viewport wird im Edit-Modus durch Inspector schmaler; Widget liegt teils außerhalb → normales Scroll-Verhalten der Canvas, kein Clipping-Bug. (Beobachtung bleibt als UX-Notiz: sicherheitsrelevante Widgets nicht am rechten Canvas-Rand platzieren — Show-Design, kein Code.)

## Artefakte
- Screenshots: Session-Scratchpad `gallery/` (~50, Einzel-Views/Widgets/Live-Edit) + `gallery_mw/` (15, echtes MainWindow) + `viz05_*.png` (VIZ-05-Beweise) — Session-temporär; Befunde oben sind eigenständig verständlich.
- Repro-Skripte: `gallery_script.py`, `gallery_mw.py`, `repro_vcl04.py`, `_viz05_case_worker.py` (Scratchpad).


## ✅ Nachtrag: Interaktive GUI-Verifikation (Computer Use, 2026-07-02 nachmittags)
David war am Rechner, Freigabe erteilt — die offene interaktive Verifikation wurde in der echten App (frische Instanz, main `da184fc`) nachgeholt:
- **Farbwechsel-Auswahl (PR #131):** Swatch-Klick im „Farben"-Feld → Farbdialog → Magenta gewählt → Sequenz UND Vorschau übernehmen sofort. ✔
- **Immer-Vorschau (PR #131):** Matrix nie gestartet, Vorschau animiert trotzdem (Läuferposition wandert zwischen Aufnahmen). ✔
- **Anzeige-Toggles + Regressions-Fix (PR #131/#132-Review):** „Tempo-Kontrolle" ab- UND wieder angewählt → Tempo-Zeile kommt zurück. ✔
- **Responsiv (PR #131):** schmal = gestapelt + Tempo einzeilig ab ~430 px; breit gezogen = Vorschau links OBEN (UI-23), Params rechts. ✔
- **Bearbeiten/Bedienen:** Run-Modus zeigt nur den angehakten Farben-Regler ohne Häkchen-Liste. ✔
- **UI-Polish (PR #135):** Sektions-Tabs ohne Überlappung (Elide greift), GM „100%" lesbar, Checkbox-Rahmen sichtbar, Tempo-Label „(dieser Effekt)". ✔
- **Neuer Befund → UI-25:** Bei Davids realer Fensterbreite (1344 px logisch, unter der 1440er-Volltext-Schwelle) verteilt das Layout ungleich — „Virtual Console" voll, „Patchen" elidiert, „E/A" kollabiert zu reinem „…".