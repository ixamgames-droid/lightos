ID: HW-6
Status: blocked
Status-Notiz: Port-Warnung am echten Enttec bestaetigt (22.11.2026, Sitzung D mit dem Projektinhaber, Fehlercode 5, kein Fix noetig); offen nur noch Punkt 3 (Tastenbelegung mh_einmessen.py an einem echten Windows-Terminal, braucht einen Moving Head)

**Probe 22.11.2026 (Windows 11 x64, Enttec DMX USB Pro, FTDI 0403:6001):** Instanz 1 sendet; Instanz 2 meldet „COMx ist bereits von einem anderen Prozess geoeffnet — Windows vergibt serielle Ports exklusiv“ samt Verdachtsliste, die Ausgabe laeuft dort nicht an. `_win_oeffnungsversuch` liefert waehrend der Belegung 5 (ERROR_ACCESS_DENIED), sonst 0; `_WIN_BELEGT` (5, 32) deckt das ab. Am Enttec zuckte beim Test-Oeffnen nichts (Erwartung „nein“ bestaetigt), ein angeschlossener PAR blieb ruhig. Folgebefunde zur Meldung: OUT-83. Offen bleibt nur Punkt 3 (mh_einmessen.py-Tasten an einem echten Terminal).
