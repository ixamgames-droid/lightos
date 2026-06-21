# LightOS — Anleitungen (Hardstyle-Show-Kit)

> Deutsche Schritt-für-Schritt-Anleitungen mit Bildern/GIFs. Roter Faden: die **Hardstyle-Show**
> (`shows/Hardstyle_Show.lshow`) — vom Patchen bis zur musiksynchronen Live-Show.
> Rig: **8 PAR** (RGBW) + **2 Moving Heads** + **2 Spider**, ~150 BPM.

---

## Reihenfolge (vom Aufbau zur Live-Show)

| # | Anleitung | Worum geht's |
|---|---|---|
| 1 | [Patchen & Gruppen](anleitung_patch_gruppen/ANLEITUNG_PATCH_GRUPPEN.md) | Geräte auf DMX-Adressen legen, Fixture-Gruppen + Raster anlegen. |
| 2 | [Farb-Matrix](anleitung_farbmatrix/ANLEITUNG_FARBMATRIX.md) | RGB/RGBW-Farbeffekte über eine Gruppe (Algorithmen, Raster). |
| 3 | [Farbchase (Blau-Weiß)](anleitung_farbchase/ANLEITUNG_FARBCHASE.md) | Konkreter Chase mit frei wählbarer Farbfolge (Color Sequence). |
| 4 | [Dimmer-Matrix & relative Geschwindigkeit](anleitung_dimmermatrix/ANLEITUNG_DIMMERMATRIX.md) | Helligkeits-Lauflicht ×2 zur Farbe, phasen-gekoppelt. |
| 5 | [EFX — Moving-Head-Bewegung](anleitung_efx/ANLEITUNG_EFX.md) | Pan/Tilt-Bahnen (Kreis …), `open_beam`, Geräte-Verhältnis. |
| 6 | [Moving Heads steuern](anleitung_moving_heads/ANLEITUNG_MOVING_HEADS.md) | Farbrad, Gobo, Bewegung (EFX) und gezieltes Pan/Tilt über die VC. |
| 7 | [Spider steuern](anleitung_spider/ANLEITUNG_SPIDER.md) | Farb-Themes pro Bar (L/R) und Tilt-Bewegung (Scheren/Wippe). |
| 8 | [Virtuelle Konsole bauen & designen](anleitung_vc/ANLEITUNG_VC.md) | Eigene Bedienoberfläche: 5 beschriftete Bänke, Fader, Labels, Strobe. |
| 9 | [APC mini mappen](anleitung_apc_mapping/ANLEITUNG_APC.md) | VC-Widgets auf Pads/Fader legen (MIDI-Learn / Teach), LED-Feedback. |
| 10 | [Musik-Sync & Auto-Show](anleitung_musik_sync/ANLEITUNG_MUSIK_SYNC.md) | Playlist → Play startet die Show automatisch, Tempo folgt der Musik. |
| 11 | [Speed-Dial, Master/Sub & Grand-Master](anleitung_speed/ANLEITUNG_SPEED.md) | Tempo aus der VC (QLC+-Stil): Master/Sub × Faktor, Grand-Master, mehrere Effekte je Regler. |

## Schichten-Modell (so kombiniert die Show)

Die Looks sind **getrennte Ebenen** über denselben Geräten und lassen sich frei kombinieren:

- **Farbe** — Farb-Matrix/Chase (auch über die Moving Heads) → *Farbmatrix / Farbchase*
- **Beat-Farbe** — beat-synchroner Farb-Chase auf dem gemeinsamen **Tempo-Bus** (eine Farbe pro Beat, z. B. RRRW/RWRW, live umfärbbar) → *Farbchase*
- **Helligkeit** — Dimmer-Matrix, läuft **×2 phasen-gekoppelt** zur Farbe → *Dimmer-Matrix*
- **Bewegung** — EFX auf den Moving Heads (mit `open_beam`) → *EFX*
- **Moving Heads** — Farbrad & Gobo (Ring/Punkte/Zebra/Rotation) zusätzlich zur Bewegung → *Moving Heads*
- **Spider** — Farb-Themes pro Bar (L/R) und Tilt-Schwenk (Scheren/Wippe) → *Spider*
- **Tempo** — alles über **Tempo-Speeds** (Master/Sub × Faktor, Grand-Master) an die **globale BPM** koppelbar → *Speed-Dial / Musik-Sync*

## Bedienung

- **Virtuelle Konsole** (5 Bänke): Performance (Looks/Farben/LIVE-SHOW/Master), Tempo/BPM, Strobe/Musik, BEAT-BLINK / Effekt-Farben (RRRW/RWRW + Dimmer-Blink + Farb-Editor), MH-Gobos / Spider / Bewegung (Gobos, Spider-Bar-Farben, MH-Kreis/Spider-Schwenk).
- **APC mini** als Hardware-Controller (optional, per MIDI-Learn).
- **Live-Show**: ein Klick auf **LIVE-SHOW** oder **Play** startet den kompletten Look music-synchron.

## Verwandte Dokumente

- **BPM-Manager — neue Funktionen** (BPM-Quelle, Genre-Presets, Takt-Raster, **Generator**: ganzes Lied → Beatgrid, Analyse-Engines, Beatgrid-Editor, „Taktgenau"): [anleitung_bpm_manager/ANLEITUNG_BPM_MANAGER.md](anleitung_bpm_manager/ANLEITUNG_BPM_MANAGER.md)
- **Event-Demo-2026-Anleitungen** (Moving Heads · Spider · Speed/BPM · VC live bearbeiten): [ANLEITUNGEN_EVENT_DEMO.md](ANLEITUNGEN_EVENT_DEMO.md)
- Komplette Oberflächen-Anleitung (alle 8 Sektionen): [ANLEITUNG.md](ANLEITUNG.md)
- Effekte bauen & mit Tempo steuern: [EFFEKTE.md](EFFEKTE.md)
- Komplettes Lichtshow-Tutorial (Matrix · Chase · MH-EFX · VC): [tutorial_matrix/TUTORIAL_LICHTSHOW.md](tutorial_matrix/TUTORIAL_LICHTSHOW.md)
- Show-Plan/Hintergrund: [HARDSTYLE_SHOW_PLAN.md](HARDSTYLE_SHOW_PLAN.md)
- Offene Punkte/Feature-Wünsche: [OPEN_POINTS_OVERVIEW.md](OPEN_POINTS_OVERVIEW.md)
