# Party Demo 2026 — BPM-getaktete Party-Show + Musik

`shows/Party_Demo_2026.lshow` · Generator `tools/build_party_demo_show.py`

Show passend zu Davids Party-Musik (Ordner `Desktop/Musik/BP Party` — HBz-Bounce /
Hardstyle / Hypertechno / Frenchcore, ~150 BPM). **Setup:** Akai APC mini + 8× RGBW-PAR
(ZQ01424, 8ch @1,9,…,57) + 2× Moving Head (ZQ02001, 11ch @65,@76).

## Banks (APC-SCENE-Tasten = Bank 1–5 = Playback-Seite)

| Bank | Name | Inhalt |
|---|---|---|
| 1 | **LIVE/Party** | R1–2 16 Farben (Programmer) · R3–4 16 Beat-Effekte (PAR, exklusiv) · R5 8 MH-Formen (layern) · R6 8 Looks · R7 Gruppen-Auswahl + Flashes · R8 Track + Musik-Transport. Fader: FX-Speed/FX-Master/FX-Param/PAR-Dim/MH-Dim. |
| 2 | **Matrix-Looks** | Alle 16 RGB-Matrix-Algorithmen auf den 8 PARs (exklusiv). |
| 3 | **Moving Heads** | XY-Pad (16-bit zielen) + 8 EFX-Formen (Kreis/Acht/Dreieck/Zufall/Linie/Raute/Quadrat/Lissajous) + Relativ/Spiegeln/Neustart. |
| 4 | **Playback** | 4 BPM-getaktete Cuelisten auf Executoren (s. u.) + GO-/Flash-Pads + Speed-Dial + Dimmer-Fader. |
| 5 | **Musik** | **VCSongInfo** (aktuelles/nächstes Lied) + große Media-Transport-Reihe (◄◄ ►/❚❚ ►►) + Musik-BPM + Looks. |

Universell (alle Banks): Track-Reihe Clear/Stop/Blackout/Tap; Master/Dimmer/Speed-Fader.

## Playbacks (taktbezogen, repräsentativ 150 BPM → Beat 0,4 s)

- **Warmup** (Loop) — ruhige Farbstimmungen, langsames Auto-Atmen über je 1 Phrase.
- **Drop/Peak** (einmal GO, Auto-Follow) — Build → Peak (Weiß) → 2 Farb-Bursts → Halten.
- **Hands-Up** (Bounce) — schneller Farb-Chase auf dem Beat.
- **MH-Sweep** (Bounce) — Moving-Head-Fahrt über die Phrase mit Amber-Wash.

Spielbar in **VC-Bank 4** (GO-Pads/Cuelisten) **und** im **Playback-Tab Seite 4** (gekoppelt).

## Musik abspielen

Zwei Wege, BPM an die Lichter zu bekommen:

1. **In-App-Player** (Tab **„Musik"**): Die Playlist ist in der Show gespeichert (10 Lieder,
   Warmup → Peak → Frenchcore → Ausklang). Doppelklick = abspielen; ◄◄ ►/❚❚ ►► auch auf den
   APC-Pads (Bank 1 R8 und Bank 5). „BPM koppeln" setzt eine **grobe Nominal-BPM** als Fallback.
2. **VirtualDJ → OS2L (empfohlen, taktgenau):** Menü **„Ausgabe → OS2L-Server starten"**
   (TCP :1234), in VirtualDJ den OS2L-Output auf `localhost:1234` stellen. Dann liefert VirtualDJ
   die **echte BPM/Beats**; sie überschreibt die Nominal-BPM laufend, alle Beat-Effekte und der
   „Musik-BPM"-Pad takten exakt mit.

Die Playlist verweist auf die **Original-Dateien** unter `Desktop/Musik/BP Party` (die Show
bleibt klein, ist aber an diesen PC gebunden). „Ordner laden…" im Musik-Tab lädt eine andere
Sammlung (BPM/Genre werden grob aus dem Dateinamen geschätzt).

## Neu generieren

```
venv/Scripts/python.exe tools/build_party_demo_show.py
```

Der Generator ist selbst-verifizierend (Patch=10, Playlist=10, 4 Playbacks gebunden,
VCSongInfo + 6 Media-Pads, keine Widget-Überlappung). Tests:
`pytest tests/test_party_demo_show.py tests/test_media_player.py tests/test_vc_song_info.py`.

Siehe auch [MUSIK_PLAYER_IDEEN.md](MUSIK_PLAYER_IDEEN.md) für die Roadmap des Musik-Players.
