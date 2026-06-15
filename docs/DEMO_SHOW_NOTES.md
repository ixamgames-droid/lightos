# Praxis-Demo-Show — Notizen (P13)

> **Show:** `shows/Praxis_Demo.lshow` · **Generator:** `tools/build_practice_show.py`
> (selbstverifizierend: baut, speichert, lädt neu und prüft alles per assert).
> Stand: 2026-06-11. Schwester-Show: `Komplett_Demo.lshow` (Feature-Vollabdeckung);
> die Praxis-Demo fokussiert auf die **neuen Funktionen der Runde P1–P12**.

## Fixtures & Patch (Adressen via `suggest_address`, P1)

| fid | Gerät | Modus | Universe | Adresse |
|-----|-------|-------|----------|---------|
| 1–4 | Generic ZQ01424 (PAR) | 8-Kanal RGBW | 1 | **1 / 9 / 17 / 25** |
| 5 | U King ZQ02001 „MH Links" | 11-Kanal | 1 | **33** |
| 6 | U King ZQ02001 „MH Rechts" | 11-Kanal | 1 | **44** |

Die Adressen wurden im Generator **nicht hartkodiert**, sondern von
`state.suggest_address()` vergeben — der Praxisbeweis für P1.
PARs haben `base_levels intensity=255` (Farbe sofort sichtbar).

## Gruppen & Ordner (P5)

| Ordner | Gruppe | Mitglieder |
|--------|--------|-----------|
| Buehne | PARs | fid 1–4 |
| Buehne | Moving Heads | fid 5, 6 |
| Spezial | Alle | fid 1–6 |

→ Test: **Programmer → Gruppen-Liste** muss die Ordner-Kopfzeilen „📁 Buehne" /
„📁 Spezial" zeigen (war vorher der gemeldete Bug).

## Live View (P4)

Alle 6 Fixtures sind platziert (PARs unten in Reihe, MHs oben links/rechts);
`live_view_meta` (Zoom 100 %, Grid 20, Snap an, Welt 1200×800) wandert mit der
Show und wird beim Laden wiederhergestellt.

## APC-mini-Banken (Scene-Tasten rechts = Bank 1–8)

**Auf jeder Bank aktiv:** Track-Tasten unten = Clear / Stop All / Blackout /
Tap / Musik-BPM · Fader F6 = Dimmer (Submaster), F7 = Speed global, F9 = Grand
Master.

| Bank | Name | Belegung (oberste Pad-Reihe = Note 56–63) |
|------|------|--------------------------------------------|
| 1 | GRUPPEN | PARs an · MHs Beam auf · Alle (Festival-Look); Reihe 2: Flash-Varianten; Reihe 3: PARs aus |
| 2 | FARBEN | 8 Grundfarben (PARs); Reihe 2: **Weiß (W) vs. Weiß (RGB)** + Warm-/Kaltweiß; Reihe 3: MH-Farbrad 3 Vollfarben + **2 Split-Farben** („Hellblau/Rosa", „Orange/Hellblau"); links: Color-Chaser |
| 3 | INTENSITY | Full On · Dim 50 % · All Off · Lauflicht · Ping-Pong · Strobe-Chase; F1/F2 = Speed, F5 = FX-Level |
| 4 | MH POSITION | Center · Publikum · Bühne · Links · Rechts · Stop All; F1/F2 = Pan/Tilt (Programmer) |
| 5 | EFX | Kreis (Fan 50 %) · Sweep (gespiegelt) · Acht · **Bounce** (testet den Bounce-Fix); F1 = EFX-Speed |
| 6 | LOOKS | Ambient Ruhig · Party · Festival · Highlight; Reihe 2: Matrix Rainbow/Lauflicht/Fire |
| 7 | SPECIALS | Blackout · Stop All · Clear · Tap · Musik-BPM; Reihe 2: Beat-Chaser · Strobe · All Off · MH-Reset (Flash, halten!) |
| 8 | TEST | Weiß-W vs. Weiß-RGB (am Gerät vergleichen!), Matrix, EFX, Lauflicht; F1/F2 = Rot/Weiß-Programmer-Fader (Slider-Sync-Test) |

## Enthaltene Funktionen

- **Szenen:** 8 Farben (inkl. 2× Weiß-Varianten), 4 Looks, 3 Dimmer-Stufen,
  5 MH-Positionen, 3 MH-Farbrad-Vollfarben, 2 MH-Split-Farben, MH-Reset, 2 Beat-Looks
- **Chaser:** Lauflicht, Ping-Pong, Strobe-Chase, Color-Chase, Beat-Looks (beat-getriggert)
- **EFX:** Kreis/Sweep/Acht/Bounce (alle `open_beam`, auf beiden MHs)
- **Matrix:** Rainbow, Lauflicht, Fire (auf der PAR-Reihe)

## Durchgeführte Verifikationen (automatisch im Generator)

1. Save → Reload-Roundtrip (`load_show` ok)
2. 6 Fixtures, Adressen exakt [1, 9, 17, 25, 33, 44] (= suggest_address korrekt)
3. Gruppen-Ordner-Zuordnung überlebt den Roundtrip
4. `live_view_meta` + 6 Positionen überleben den Roundtrip
5. „Weiß (W-Kanal)"-Szene: color_w=255 UND color_r=0 (kein Doppel-Weiß)
6. 2 Split-Farben-Szenen aus echten `ChannelRange`-Daten erzeugt
7. 4 EFX inkl. `direction="bounce"` persistiert, alle open_beam
8. VC: 94 Widgets, Banken 0–7 + Universal (-1) alle belegt
9. Beat-Chaser: `audio_triggered` + `beats_per_step` überleben

## Manuelle Praxis-Tests (am Gerät)

1. **Weiß-Test (Bank 2/8):** „Weiß (W)" muss sichtbar anders aussehen als
   „Weiß (RGB)" (nur W-LED vs. RGB-Mischweiß).
2. **Slider-Sync (Bank 8 / Programmer):** Farbe per Pad setzen → Programmer-
   Slider müssen mitlaufen.
3. **Ordner (Programmer → Gruppen):** „📁 Buehne" / „📁 Spezial" sichtbar.
4. **Live View:** Fixture verschieben, Show speichern/laden → Position+Zoom bleiben.
5. **Bounce (Bank 5):** Sweep muss am Rand **umkehren**, nicht zurückspringen.
6. **Auto-Save:** Nach Änderung ≤5 min warten → Statusleiste „Auto-Save: …";
   ohne Änderungen kein erneuter Write (dirty-basiert).

## Aufgefallene Grenzen / offene Punkte

- **Echte „Gruppen-Auswahl" per Pad gibt es nicht** (VC arbeitet funktionsbasiert):
  Bank 1 nutzt Gruppen-*Looks*; die Programmer-Auswahl selbst setzt man in
  Live View/Programmer. (Wunsch notiert: ButtonAction „Gruppe auswählen".)
- **Gruppen-Dimmer als eigener Fader-Modus fehlt** — abgedeckt über Submaster
  (F6) + FX-Level; ein `SliderMode.GROUP_DIMMER` wäre ein sauberes Folge-Feature.
- **EFX-Parameter-Fader** (Spread/Größe) per CC nicht belegt — nur Speed ist
  als Slider-Modus für EFX verifiziert; Rest über den EFX-Reiter.
- MH-Reset liegt bewusst als **Flash** (nur solange gedrückt) — Sicherheit.
