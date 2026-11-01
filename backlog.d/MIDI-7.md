ID: MIDI-7
Prioritaet: P3
Status: review
Status-Notiz: MIDI-Clock (0xF8) als BPM-Quelle „MIDI-Clock (Pult/DAW)": rtmidi filtert Timing nicht mehr (timing=False), Clock/MTC laufen ueber subscribe_echtzeit der gemeinsamen Empfangsschleife (rtmidi + WinMM); src/core/midi/midi_clock.py misst 24 PPQN ueber 2 Viertel, meldet je Viertel per request_bpm(…, "midi_clock"), Start/Continue messen neu, Stop haelt den Takt, nur ein Clock-Port zaehlt, Zeitstempel beim Empfang; tests/test_midi7_mtc04_clock_timecode.py
