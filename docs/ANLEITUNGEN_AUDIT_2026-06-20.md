# Anleitungen-Audit & Fixes — 2026-06-20

> **Auslöser:** Frische Re-Verifikation **aller Anleitungen** gegen den aktuellen Quellcode
> (Folge-Audit nach [ANLEITUNGEN_AUDIT_2026-06-19.md](ANLEITUNGEN_AUDIT_2026-06-19.md)).
> **Methode:** Multi-Agent — 6 Ground-Truth-Agenten (UI/Sektionen, VC-Smart-Build, RGB-Matrix,
> Programmer/Helper, EFX/Tempo, Audio/BPM + Show-Bänke) + **34 Einzel-Agenten** (1 pro Anleitung),
> die jede UI-Aussage mit `file:line` gegen den Code abgeglichen haben. Diesmal **inkl.** der neuen
> `anleitung_komplettshow_2026/`-Serie (am 06-19 noch nicht geprüft) sowie `MULTIPLIKATOR_DIAL_ANLEITUNG`
> und `KEYBOARD_MAPPING`.

## Ergebnis

- ✅ Die **6 MAJOR-Befunde des 06-19-Audits** sind nachweislich **eingearbeitet** (8 Sektionen/Strg+1…8,
  Helper-Tab statt FunctionManagerView, 18 statt 17 Matrix-Algorithmen, VC-Smart-Build-Flow,
  „Dimmer treiben"-Schalter weg → Style, 5 statt 3 Bänke).
- Neuer Stand der Erstprüfung: **~17 OK · 4 MAJOR · 3 nur fehlender Screenshot · ~10 MINOR**.
- **Alle gefundenen Text-/Code-Fehler wurden am 2026-06-20 behoben** (siehe unten). Offen bleiben nur
  noch echte Screenshots und die fehlenden (neuen) Anleitungen → To-do-Liste.

---

## 1. Heute behoben (eingespielt)

### 🟥 MAJOR (Nutzer blieb hängen / wurde in die Irre geführt)

- **`MULTIPLIKATOR_DIAL_ANLEITUNG.md`** — Schritt 6 war unausführbar: im Ziel „Effekt ×½/×2 (Multiplier)"
  ist die Zeile „Faktor-Set (Sub):" **ausgeblendet** (`vc_speedial.py:883`: nur sichtbar bei Ziel
  „Speed-Knoten" **oder** gesetztem Häkchen „Multiplikator-Modus (0.5/1/2/4×)"). → Schritt ergänzt: erst
  das Häkchen setzen, dann erscheint das Feld.
- **`anleitung_komplettshow_2026/06_efx_bewegung`** — falsche Aussage „2D-Live-View zeigt keine
  Pan/Tilt-Bewegung". Tatsächlich dreht sich die Beam-Linie mit dem Pan-Wert (`live_view.py:117-122`);
  nur Tilt wird im Beam nicht visualisiert. → korrigiert.
- **`anleitung_komplettshow_2026/02_positionen_3d`** — Schritte 2–3 (Geräte aus „Auto-Bogen" ziehen,
  Layout aufbauen) passten nicht: die Show bringt alle 12 Geräte fertig platziert mit
  (`live_view.py:498-524`, Auto-Bogen nur für neu gepatchte Geräte ohne Position). → umgeschrieben.
- **`anleitung_speed_bpm`** — §4 nannte ein „Tempo-Bus"-Feld im Effekt-Editor, das es nicht gibt. → ersetzt
  durch die echten Wege (Smart-Drop-Aspekt „Tempo-Bus zuweisen…" bzw. Rechtsklick → „⚡ Live-Parameter…").

### 🟨 MINOR (Label-/Wortlaut-Drift)

`anleitung_farbmatrix` (kein „Weißanteil"-Regler; Rainbow=0 Farben) · `tutorial_matrix` (EFX-Namen nicht
alle englisch: Trapez/Random/Custom Path) · `anleitung_moving_heads` (Reihen-Zählung „MH wählen" = Reihe 4)
· `anleitung_vc_workflow` („MIDI Lernen" bricht bei Fader/XY-Pad ab statt ignorieren) · `anleitung_programmer`
(Farb-Kacheln ignorieren die Selektion) · `anleitung_ablaeufe` (Überschrift §3: nur 2 von 3 Cuelisten
beat-synchron) · `anleitung_dimmermatrix` (§2 folgt der Auswahl automatisch) · komplettshow `00_grundlagen`
(Titelleisten-Pfad), `03_gruppen` („＋"-Glyph), `04_coloreffekt` („Schnellwahl:" + Fan-Tool 1 Attribut),
`05_matrix_dimmer` („▶ Start/■ Stop" + Default-Matrix), `07_virtuelle_konsole` (Dialog nur beim Ziehen).

### 🖼️ Bilder / 🔧 Code

- **`anleitung_dimmermatrix/img/02_vc_tempo_bus.png`** — fehlte → das passende SpeedDial-Properties-Bild
  aus der (verwaisten) Mappe `anleitung_farb_fx_vc/img/` wiederverwendet. Link gefixt.
- **Code-Backfix** `src/ui/virtualconsole/vc_effect_meta.py:153` — Kontextmenü-Label `Farben aendern…`
  → `Farben ändern…` (löst die Drift in `anleitung_vc_elemente`; UTF-8 ok, kompiliert).

---

## 2. Offen → To-do (in der Session-Task-Liste hinterlegt)

### Fehlende Screenshots (Text korrekt, aktuell Platzhalter im Dokument)
- `docs/tutorial_matrix/web/programmer_helper.png` (in `ANLEITUNG.md` §5) — Programmer-Helper-Tab.
- `docs/anleitung_musik_sync/img/03_autoshow_fuer_lied.png` — Dialog „Auto-Show für Lied…".
- → echte Aufnahme via laufender App + `docs/_walkthrough/lo.ps1`; danach den HTML-Kommentar im Dokument
  wieder aktivieren.

### Fehlende Anleitungen (erreichbare Features ohne Doku)
- **Hoch:** Simple Desk (Sektion) · Playback/Cuelists/Executors + Show-Manager · Snapshots/Snaps.
- **Mittel:** DMX-Ausgabe einrichten (ArtNet/sACN/USB) · eigene Fixtures bauen & QXF/GDTF-Import ·
  Paletten · Submaster/Kanal-Gruppen · Kurven-Editor · erweiterte Funktionstypen
  (Sequence/Collection/Carousel/Layered/Script — erst Erreichbarkeit prüfen, da FunctionManagerView
  nicht mehr eingehängt ist).
- **Niedrig:** Web-/Remote-Konsole · OSC · Timecode · Befehlszeile (F12).

### Struktur / Aufräumen
- Verwaiste Mappe `docs/anleitung_farb_fx_vc/` (nur `img/`, keine `.md`) auflösen + `FARB_FX_VC_SHOW.md`
  auditieren (nie geprüft).
- `docs/`-Wurzel: ~24 Plan-/Audit-/Log-Dateien von den Endnutzer-Anleitungen trennen (z. B. `docs/_planung/`).
- `anleitung_komplettshow_2026/08_apc_mapping/` ist eine leere Platzhalter-Mappe (Index sagt korrekt
  „noch offen") → APC-Mapping-Anleitung ergänzen.

---

*Quelle: Multi-Agent-Audit + Fix-Workflows 2026-06-20 (40 + 19 Agenten). Vorgänger:
[ANLEITUNGEN_AUDIT_2026-06-19.md](ANLEITUNGEN_AUDIT_2026-06-19.md).*
