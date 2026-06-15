# Musik-Player — Stand & Ideen-Roadmap

Stand 2026-06-14. Erste, bewusst **rudimentäre** Umsetzung eines Musik-Players in LightOS
plus „aktuelles/nächstes Lied" in der Virtuellen Konsole. Dieses Dokument hält den Ist-Stand
und die offenen Ideen fest (David: „erstmal nur Ideen, die man aufschreiben sollte").

## Schon umgesetzt (funktional)

- **In-App-Player** `src/core/audio/media_player.py` (`get_media_player()`): Playlist aus
  Tracks (`path/title/genre/bpm`), Play/Pause/Next/Prev/Stop/Seek/Volume, Auto-Advance am
  Track-Ende. Audio-Backend (`QMediaPlayer`/`QAudioOutput`) wird **lazy** erzeugt.
- **Tab „Musik"** `src/ui/views/music_view.py`: Playlist-Tabelle (Titel/Genre/BPM,
  Doppelklick = abspielen), Transport, Positions-/Lautstärke-Slider, „Ordner laden…",
  „BPM koppeln (Fallback)". Auch als eigenes Fenster: Menü **Ansicht → „Musik-Fenster (Now Playing)"**.
- **VC-Songanzeige** `VCSongInfo` (`src/ui/virtualconsole/vc_song_info.py`): zeigt
  „▶ Jetzt: … (BPM)" + „Als Nächstes: …", aktualisiert sich live.
- **VC-Transport-Pads**: `ButtonAction.MEDIA_PLAY_PAUSE / MEDIA_NEXT / MEDIA_PREV` → APC-Pads
  steuern die Wiedergabe.
- **Persistenz**: Playlist liegt in der `.lshow` (`state.playlist`), Player wird beim Laden gefüllt.
- **BPM-Quelle**: PRIMÄR VirtualDJ → OS2L (treibt schon den globalen `BPMManager`). Der Player
  setzt beim Trackwechsel nur eine grobe **Nominal-BPM** (Genre/Titel-Heuristik) als Fallback.

## BPM-Hintergrund (warum „grob")

Echte **Offline-BPM-Analyse** ist mit den vorhandenen Mitteln nicht zuverlässig: keine
BPM-Tags in den Dateien, kein `ffmpeg`/`librosa`/`mutagen`. Die genaue, taktgenaue BPM kommt
deshalb zur Laufzeit von VirtualDJ (OS2L) oder der vorhandenen Audio-Beat-Erkennung
(`src/core/audio/beat_detector.py`). Genre→BPM-Heuristik: `frenchcore`→185 (bzw. Zahl in `[..]`),
`hardstyle/hardtekk/rawphoric`→150, `hypertechno`→150, `bounce/hbz`→155, `techno`→135, sonst 128.

## Ideen / Roadmap (noch offen)

1. **Pro-Song-Licht-Look + Auto-Umschalten**: je Playlist-Eintrag ein gespeicherter Look/Cue,
   der beim Trackwechsel automatisch geladen wird (Setlist-Modus).
2. **Echte Offline-Analyse** (optional): `mutagen` für BPM-Tags bzw. `librosa`/`numpy`-FFT zum
   Schätzen — als optionales Extra-Paket, da heavy.
3. **Waveform + Cue-Punkte** im Musik-Tab (Anspielen ab Drop, Marker setzen).
4. **Crossfade / 2-Deck** bzw. saubere Übergabe an/von VirtualDJ (OS2L-cmd-Events → Cues).
5. **Suche/Filter** über die große Sammlung (412 Dateien), Tags/Ordner, Favoriten.
6. **Playlist-Dateien** (`.m3u`/eigenes Format) laden/speichern, mehrere Setlists pro Show.
7. **VCSongInfo erweitern**: Fortschrittsbalken/Restzeit, Cover, BPM-Quelle-Anzeige (OS2L/Tap/Nominal).
8. **MP4-Video** (der Player kann mp4 abspielen) — evtl. Video-Ausgabe/Beamer-Fenster.
9. **Auto-DJ**: automatischer Übergang Lied→Lied mit Fade + passendem Licht-Build.

## Dateien

- Core: `src/core/audio/media_player.py`
- UI: `src/ui/views/music_view.py`, Tab in `src/ui/main_window.py` (Sektion I/O), Menü „Ansicht"
- VC: `src/ui/virtualconsole/vc_song_info.py` (+ Registry `vc_canvas.py`),
  `ButtonAction.MEDIA_*` in `vc_button.py`
- Persistenz: `state.playlist` in `src/core/app_state.py`, Save/Load/Reset in `src/core/show/show_file.py`
- Demo: `tools/build_party_demo_show.py` → `shows/Party_Demo_2026.lshow` (siehe [PARTY_DEMO.md](PARTY_DEMO.md))
- Tests: `tests/test_media_player.py`, `tests/test_vc_song_info.py`, `tests/test_party_demo_show.py`
