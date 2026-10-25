ID: BPM-32
Prioritaet: P3
Status: review
Status-Notiz: entschieden (25.10.): Sperre gilt bei „Aus“/„OS2L“; Auto-Show zeigt Hinweis „Takt aus Titel übernehmen“ (Musik-Tab + VC-Musik-Anzeige); Bild 03_play_vc neu, 05_takt_hinweis neu
Nach: BPM-31
Titel: Auto-Show setzt die Nominal-BPM des Titels auch bei BPM-Quelle „Aus“/„OS2L“ (BPM-17-Sperre gilt dort nicht)

**Herkunft:** Gegenprüfung von BPM-31 (20.10.2026).
**Befund:** `MusicShowDirector._ensure_bpm` (`src/core/audio/music_show.py`) setzt beim Play die Nominal-BPM des Titels als Quelle „file“, sobald die BPM auf 0 steht — ohne `song_may_lead()` (BPM-17) zu fragen. `MediaPlayer._apply_track_bpm` ist dagegen gesperrt. Die Lücke bestand schon bei globaler Auto-Show-Liste und beim Trackwechsel; seit BPM-31 greift sie auch beim ersten Play mit nur einem Lied-Look. Sichtbar im Anleitungsbild `musik_sync/03_play_vc` (124 BPM bei Quelle „Aus“).
**Zu entscheiden:** Darf die Auto-Show einen Takt setzen, wenn der Nutzer die Quelle auf „Aus“/„OS2L“ gestellt hat (sonst stehen Beat-Effekte still), oder gilt die BPM-17-Sperre auch hier?
**Fertig, wenn:** entschieden, umgesetzt, Test für beide Quellen.
**Entscheidung (25.10.2026, Projektinhaber):** Nein zur stillen Übernahme — die Quellenwahl gilt auch für die Auto-Show. Bei Quelle „Aus“/„OS2L“ und BPM 0 setzt `_ensure_bpm` (Play, globale Liste, Lied-Look, Trackwechsel) nichts, sondern meldet einen sichtbaren Hinweis mit Ein-Klick „Takt aus Titel übernehmen“ (Quelle → Lied-Analyse, Titel-BPM als „file“). Begründung: Nutzerwahl respektieren, bei OS2L keine Konkurrenz zur DJ-Software.
**Ergebnis:** `nominal_fallback_blocked()` in `src/ui/bpm_source_controller.py` (gesperrt nur „off“/„os2l“, fail-open; bewusst enger als `song_may_lead`, damit PC-Audio/Eingang vor dem Einrasten ihren Fallback behalten). `MusicShowDirector` (`src/core/audio/music_show.py`): Signal `taktHinweisChanged(bpm)`, `takt_hinweis()`, `uebernehme_titel_takt()`; BPM-/Quellen-Rückrufe aus fremden Threads gehen über ein internes Signal in den GUI-Thread; Hinweis weg bei Takt, Quellenwechsel (dann greift der Fallback der neuen Quelle) oder Stop. Anzeige: gelbe Leiste im Musik-Tab (`MusicView._takt_hinweis`) und Zeile in `VCSongInfo`. Musik-Anleitung ergänzt, Bilder `03_play_vc` (neu) und `05_takt_hinweis` (neu). Test `tests/test_bpm32_takt_hinweis.py`.
