# Programmier-Notizen (wichtige Fakten für Show-/Engine-Arbeit)

> Lose Sammlung wichtiger, nicht-offensichtlicher Fakten. Bei Show-/VC-/Effekt-Arbeit hier zuerst nachsehen.

## Hardware / Rig
- **Moving Heads (ZQ02001, 11-Kanal):** MH Links @ DMX **65**, MH Rechts @ **76**. Kanäle:
  1 Pan · 2 Pan-Fine · 3 Tilt · 4 Tilt-Fine · 5 Farbrad · 6 Gobo · 7 Shutter · 8 Dimmer · 9 Speed · 10 Gobo-FX · 11 Reset.
  Physische MH müssen auf diese Adresse + 16-bit-Pan/Tilt-Modus stehen, sonst landen Kanäle falsch.
- **MH-Kreis im Center zu langsam (Davids Hinweis):** Wenn der MH zentriert steht und einen Kreis fahren soll,
  muss er die Köpfe einmal komplett herumdrehen → das dauert zu lange bei normalem Tempo. → **Kreis-Effekt für MH
  langsamere BPM/kleineren Multiplikator geben** (oder kleineren Radius/Bereich), damit die Mechanik mitkommt.
- PAR (ZQ01424, 8ch RGBW): 1 Dimmer/Intensity · 2-5 R/G/B/W · 6 Shutter · 7 Macro · 8 Speed. Intensity-Default = 0.
- Spider (SPIDER14): RGBW + 2 Tilt-Köpfe (kein Pan), Shutter, Intensity. Bewegung = nur Tilt (gegenphasig).

## Farb-FX-VC-Show (shows/Farb_FX_VC_Show.lshow)
- **Strikte Trennung Farbe ↔ Dimmer:** Farb-Seite (Bank 1) treibt den Dimmer NICHT. `state.implicit_brightness=False`
  + keine `base_levels`-Intensity → reine Farbe bleibt DUNKEL, Helligkeit kommt aus Bank 2 („Dimmer Voll"/Dimmer-Effekt)
  + Master-Fadern (Bank 4). Bewiesen: PAR Solid blau → intensity 0; + Dimmer Voll → intensity 255.
- **Master-Tempo + Pro-Effekt-Multiplikator:** alle Effekte `tempo_bus_id="Global"` (= Default-Bus, spiegelt globale BPM)
  + eigener `tempo_multiplier`. Speed-Dial im Modus `TEMPO_BUS_MULT` zeigt das Faktor-Gitter ¼ ½ 1 2 3 4.
- **Sync:** ◆ SYNC re-ankert alle Effekte auf „jetzt" (gleicher Schlag); Auto-Sync (default an) hält neue Effekte
  am gemeinsamen Beat-Raster. `TempoBus.sync()` löst Bus-Zugehörigkeit über `mgr.get(id) is self` (deckt Alias „Global").

## Engine-Stolpersteine (wichtig!)
- **Laufende App lädt Python-Code NICHT neu.** Nach Engine-/Widget-Code-Änderungen App **neu starten** (kill `python main.py`
  + relaunch). Show-Reload (Strg+O) lädt nur Daten. Sehr viele „geht nicht"-Fälle = alter Code lief noch.
- **Effekt im Render-Pfad starten:** `fm.start(fid)` (registriert in `running_ids`, damit `function_manager.tick` ihn rendert) —
  NICHT nur `fn.start()` (setzt nur das interne Flag → wird nicht getickt).
- **VC bedienen nur mit „Bearbeiten" AUS** — im Edit-Modus editieren Klicks die Tasten statt sie auszulösen.
- **VC-Laden robust:** `VCCanvas.from_dict` überspringt defekte/unbekannte Widgets einzeln; `VCButton.apply_dict` fällt bei
  unbekannter Aktion auf `Toggle` zurück (sonst kippt eine neue Enum-Aktion die ganze VC einer älteren Version).
- **open_beam** an einem EFX öffnet Shutter + setzt Intensity 255 (MH/Spider sichtbar bei Bewegung).

## VC-Editor-Bedienung (2026-06-18)
- **Undo/Redo:** Strg+Z = rueckgaengig, Strg+Y / Strg+Umschalt+Z = wiederholen; zusaetzlich zwei
  Pfeile (↶/↷) oben in der Editor-Toolbar. Verlauf = Snapshots des ganzen Canvas (max. 50).
  Undo-Punkte: **Hinzufuegen, Loeschen, Verschieben, Groesse aendern, Eigenschafts-Dialog** (nur bei
  echter Aenderung). Ein Live-Control-Kit (`add_live_controls`) = EIN atomarer Schritt. Show-Laden
  (Strg+O) setzt den Verlauf zurueck. Code: `VCCanvas._push_undo/push_undo_snapshot/undo/redo/_restore`
  + `VCWidget._edit_properties` (Vorher-Snapshot um den Dialog) + `mousePress/Release` (Move/Resize)
  + `_vc_undo/_vc_redo` in der View. **Pre-Edit-Snapshot-Muster:** Vorher-Stand erfassen, Aktion
  ausfuehren, nur bei `to_dict() != before` per `push_undo_snapshot(before)` ablegen (kein No-op-Strg+Z).
- **„Steuert"-Liste unter Widgets:** Button-/Fader-/XY-Pad-Dialoge haben eine aufklappbare Liste
  der gesteuerten Funktionen/Effekte NACH NAMEN (statt nur Slot-Nummern) — je Zeile Auswahl-Combo,
  beim Fader zusaetzlich Parameter-Combo, „✕" loescht, „+" fuegt hinzu. Wiederverwendbare Komponente
  `target_list_editor.TargetListEditor(with_params=...)`. Befuellt = maßgeblich (ueberschreibt das
  rohe Slot-/ID-Feld); bei Executor-Slot-Aktionen bleibt das Zahlenfeld. Der Speed-/BPM-Dial hat die
  je-Effekt-Parameterliste schon (Vorbild). VCColor nicht — dort ist das Ziel eine Farbe/Gruppe.
- **Multiplikator-Button:** Speed-Dial im Ziel-Modus „Effekt ×½/×2 (Multiplier)" (TEMPO_BUS_MULT)
  zeigt das Faktor-Gitter ¼ ½ 1 2 3 4 statt Rad (das Gitter wird in diesem Modus immer gezeigt,
  unabhaengig von der Anzeige-Option). Default-Faktoren = ¼ ½ 1 2 4 (ohne 3×) → fuer ¼…4× das
  Feld „Faktor-Set" auf `¼, ½, 1, 2, 3, 4` setzen. Erscheint er trotzdem als normaler Dial → **App neu starten** (alter Code).
- **Live-Anzeige-Aktualisierung (Auto-Refresh):** `VCSpeedDial` hat jetzt einen eigenen ~10-Hz-Timer
  (`_poll_live`/`_live_bpm_probe`), der die BPM-/Multiplikator-Anzeige (Master × Faktor bzw. Bus-BPM)
  in Echtzeit nachzieht, wenn die Master-BPM sich extern (Audio/Tap) aendert — vorher aktualisierte sie
  erst beim Antippen. Repaint nur bei echter Wertaenderung. `VCBpmDisplay` macht das bereits (Push-Sub
  fuer den globalen Leader + 100-ms-Poll im Bus-Modus). Der View-`_active_fx_timer` (400 ms) zeichnet
  nur Button/Slider bei Laufzustands-Wechsel — NICHT die Tempo-Anzeigen; deshalb der eigene Timer.

## Test/Verifikation
- Headless: `LIGHTOS_NO_OUTPUT_THREAD=1 LIGHTOS_SHOW_DB=<temp> QT_QPA_PLATFORM=offscreen venv/Scripts/python.exe -m pytest …`
- Voll-Suite nur bei geschlossener Live-App (COM3-Hang) — bzw. Live-App hält COM3, headless meldet dann COM3-Fehler (harmlos).
- Render-Pfad headless testen: Universe manuell setzen (`state.universes={1:Universe(1)}; state._rebuild_render_plan()`),
  `fm.start(fid)`, `state._render_frame(dt)`, dann `universes[1].get_channel(addr)`.
- computer-use sieht das venv-Fenster; Klicks im skalierten VC-Canvas treffen aber unzuverlässig → Behavior headless beweisen,
  Live nur für „rendert/lädt/kein Crash". Fallback-Steuerung: `docs/_walkthrough/lo.ps1` (Win32 + GDI, ignoriert das Overlay).
</content>
