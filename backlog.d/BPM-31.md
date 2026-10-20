ID: BPM-31
Prioritaet: P3
Status: review
Status-Notiz: Lied-Look des ersten Titels startet ohne globale Funktionen sofort; Grenze aus der Musik-Anleitung gestrichen
Titel: Musik-Show: bei leerer globaler Funktionsliste startet der Lied-Look des ersten Titels nicht

**Herkunft:** Nebenbefund (a) aus DOC-16 (14.10.2026). **Befund:** `MusicShowDirector.start_show` (`src/core/audio/music_show.py`) kehrte bei leerer globaler Funktionsliste sofort zurück und startete dann auch den Lied-Look („Auto-Show für Lied…") des ersten Titels nicht — er kam erst beim nächsten Trackwechsel; in der Musik-Anleitung als bekannte Grenze vermerkt. **Ergebnis:** `start_show` prüft nur noch die eingeschaltete Kopplung; globale Liste (`_start_global_functions`) und Lied-Look (`_current_track_ids` → `_start_track_functions`) starten unabhängig voneinander, der BPM-Fallback greift auch für den Lied-Look allein. Ohne beides bleibt es ein No-op. Grenze aus `docs/anleitung_musik_sync/ANLEITUNG_MUSIK_SYNC.md` gestrichen (eine englische Fassung dieser Anleitung gibt es nicht). Test `tests/test_bpm31_liedlook_ohne_global.py` (6 Fälle, Hauptfall ohne Fix rot; Gegenproben: Kopplung aus, ohne alles, global allein, beides).
