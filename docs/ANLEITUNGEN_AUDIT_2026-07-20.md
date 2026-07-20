# Anleitungen-Audit — 2026-07-20 (Code-Verifikation aller 12 Kern-Anleitungen)

Autonome Verifikations-Runde aus der Loop-Watcher-Session: **alle 12 nummerierten
Kern-Anleitungen** aus [`ANLEITUNGEN.md`](ANLEITUNGEN.md) wurden Schritt für Schritt
gegen den **aktuellen Quellcode** geprüft. Baut auf den früheren Audits
([2026-07-12](ANLEITUNGEN_AUDIT_2026-07-12.md) / [06-20](ANLEITUNGEN_AUDIT_2026-06-20.md) /
[06-19](ANLEITUNGEN_AUDIT_2026-06-19.md)) auf.

## Methode

Die deutschen UI-Bezeichnungen stehen als **String-Literale** im Quellcode
(`QPushButton("…")`, `QGroupBox("…")`, `addRow("…")`, Enum-Werte …). Jede konkrete
Anleitungs-Aussage (Button-/Tab-/Dialog-/Sektions-Name, DMX-Wert, Shortcut, Attribut)
wurde gegen die zugehörige Stelle in `src/` verifiziert. Das ist ein belastbarer,
gefahrfreier Proxy für die UI (die Oberfläche wird aus genau diesen Literalen gebaut) —
ohne die laufende Instanz oder echte Hardware anzufassen.

Show-Datei-spezifische Teile (VC-Bank-Layouts der Demo-Shows, z. B. `Event_Demo_2026.lshow`)
liegen **nicht** im Code, sondern in der `.lshow` — diese sind für eine spätere Live-UI-Runde
vorgemerkt (unten markiert).

## Ergebnis

| # | Anleitung | Ergebnis |
|---|---|---|
| 1 | Patchen & Gruppen | ✅ aktuell — alle Labels exakt (patch_view, fixture_browser, fixture_group_view). |
| 2 | Farb-Matrix | ⚠️→✅ Regler „After Fade" → **„Schweif (%)"** korrigiert. |
| 3 | Farbchase | ✅ aktuell — inkl. Color-Sequence-Editor-Legende + Status-Label. |
| 4 | Dimmer-Matrix | ⚠️→✅ „After Fade" → **„Schweif (%)"**; Tempo-&-Blende-Felder bestätigt. |
| 5 | EFX | ⚠️→✅ §4 behauptete „kein Tempo-Bus-Feld" — der EFX-Editor hat es inzwischen; neu geschrieben. |
| 6 | Moving Heads | ✅ Farbrad-/Gobo-DMX-Werte + ZQ02001-Profil exakt. *(VC-Bank-4-Layout → Live-UI vorgemerkt.)* |
| 7 | Spider | ✅ SPIDER14-Profil (2× RGBW-Bars, 2 Tilts, kein Pan, Shutter 8=offen) exakt. *(VC-Bank-5 → Live-UI.)* |
| 8 | Virtuelle Konsole | ⚠️→✅ §1 Widget-Palette **16 statt 15**, tote „Baukasten-Knöpfe" entfernt. |
| 9 | APC mini | ✅ APC-Layout (Note 0–63/64–71/82–89, CC 48–56) + Dialoge exakt. |
| 10 | Musik-Sync | ✅ Auto-Show/OS2L/PC-Audio + Shortcuts Strg+7/8 exakt. |
| 11 | Speed-Dial | ⚠️→✅ §4 „Gekoppelte Effekte" → **„Steuert"-Liste** korrigiert. |
| 12 | Laser | ✅ L2600-Profil, Laser-Tab, „Laser-Muster abrufen", NOT-AUS, Zeichen-Studio (§7) exakt. |

**8/12 waren voll aktuell; 4 hatten veraltete Stellen** (5 Fund-Cluster), alle korrigiert.

## Korrekturen (Commits auf diesem Branch)

- **`After Fade` → `Schweif (%)`** (7 Stellen in 4 Dateien): der Matrix-Chase-Regler
  wurde im UI zurück auf „Schweif (%)" benannt (`rgb_matrix_meta.py:94`), damit er nicht mit
  dem zeitlichen Ausblenden verwechselt wird. Betroffen: `anleitung_dimmermatrix`,
  `anleitung_farbmatrix` (2×), `anleitung_vc_widgets/19_matrix_editor` (3×), `anleitung_colorfade_vc`.
  → Commit `25cbcbf`.
- **EFX-Editor hat jetzt ein Tempo-Bus-Feld** — `ANLEITUNG_EFX.md` §4 sagte mehrfach das
  Gegenteil; die Gruppe „Tempo & Richtung" enthält heute Tempo-Bus/Tempo ×/Tempo-Versatz/
  „Taktgleich starten" (`efx_view.py:976-1009`). → Commit `2400409`.
- **VC-Widget-Palette 16 statt 15** + tote „Baukasten-Knöpfe" — `ANLEITUNG_VC.md` §1: die
  Edit-Modus-Werkzeugleiste hat 16 Knöpfe (`virtual_console_view.py:144-161`; „Cueliste" statt
  „Cue List", kein „Chase Builder", zusätzlich „Tempo-Controller"/„Live-Edit"); die 3 grünen
  Baukasten-Knöpfe gibt es nicht mehr → durch „Controller-Vorlage einfügen" ersetzt. → Commit `48add03`.
- **Speed-Dial „Gekoppelte Effekte" → „Steuert"-Liste** — `ANLEITUNG_SPEED.md` §4: der separate
  Block heißt nicht mehr so; Effekt-/Parameterwahl steckt jetzt in der „Steuert"-Liste
  (`vc_speedial.py:809/884`). → Commit `5054ee3`.

## Offen für eine Live-UI-Runde (nicht code-prüfbar)

- VC-Bank-Layouts der Demo-Shows (#6 Bank 4, #7 Bank 5) — leben in der `.lshow`.
- Exakte Chrome/Position der „Controller-Vorlage einfügen"-Funktion (#8 §1).

## Historisches bewusst unangetastet

`UMBAU_2026-06_*` und `ANLEITUNGEN_AUDIT_2026-06-*` dokumentieren die damalige „After Fade"-Ära
und bleiben als Zeitdokumente unverändert.
