ID: BPM-32
Prioritaet: P3
Status: decision
Status-Notiz: Folgefrage aus BPM-31 — Projektinhaber entscheidet
Nach: BPM-31
Titel: Auto-Show setzt die Nominal-BPM des Titels auch bei BPM-Quelle „Aus“/„OS2L“ (BPM-17-Sperre gilt dort nicht)

**Herkunft:** Gegenprüfung von BPM-31 (20.10.2026).
**Befund:** `MusicShowDirector._ensure_bpm` (`src/core/audio/music_show.py`) setzt beim Play die Nominal-BPM des Titels als Quelle „file“, sobald die BPM auf 0 steht — ohne `song_may_lead()` (BPM-17) zu fragen. `MediaPlayer._apply_track_bpm` ist dagegen gesperrt. Die Lücke bestand schon bei globaler Auto-Show-Liste und beim Trackwechsel; seit BPM-31 greift sie auch beim ersten Play mit nur einem Lied-Look. Sichtbar im Anleitungsbild `musik_sync/03_play_vc` (124 BPM bei Quelle „Aus“).
**Zu entscheiden:** Darf die Auto-Show einen Takt setzen, wenn der Nutzer die Quelle auf „Aus“/„OS2L“ gestellt hat (sonst stehen Beat-Effekte still), oder gilt die BPM-17-Sperre auch hier?
**Fertig, wenn:** entschieden, umgesetzt, Test für beide Quellen.
