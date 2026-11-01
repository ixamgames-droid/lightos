ID: MTC-04
Prioritaet: P3
Status: review
Status-Notiz: Cue-Feld „Timecode" (HH:MM:SS:FF, Spalte in der Cueliste); Ausloesung bei Erreichen/Ueberschreiten im Render-Takt (PlaybackEngine.compute_merged, ENG-33), Ruecksprung macht wieder scharf, Mehrfach-Sprung nur letzte Cue; MTC jetzt ueber die gemeinsame Empfangsschleife — damit auch unter WinMM (Windows-ARM) ohne rtmidi; tests/test_midi7_mtc04_clock_timecode.py
