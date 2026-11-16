ID: PRIV-8
Prioritaet: P1
Status: review
Titel: Klarname und Benutzerpfad in einer getrackten Demo-Show

**Herkunft:** Neuheiten-Audit von Sitzung A am 15.11.2026, von einem zweiten Pruefer bestaetigt.

**Befund:** `shows/Demo_Show_Full.lshow` (show.json im ZIP) trug in den 16 Playlist-Eintraegen einen absoluten Windows-Benutzerpfad mit dem Klarnamen des Betreibers. Ursache war der Generator `tools/build_demo_show_full.py`: er las einen festen Musikordner und schrieb dessen absolute Pfade in die Show. Der Waechter `tests/test_keine_privaten_dateien.py` liess Demo-Shows nach dem Dateinamen durch und sah nie in die Archive hinein. Die anderen vier getrackten Shows und sonstige getrackte ZIP-Dateien waren sauber.

**Behebung:** Der Generator liest echte Musik nur noch auf ausdruecklichen Wunsch (`LIGHTOS_DEMO_MUSIC_DIR`) und schreibt immer nur den neutralen relativen Pfad `Musik/<datei>`; seine Selbstpruefung bricht bei einem anderen Pfad ab. Die Show ist damit im Sandkasten (Wegwerf-Daten) neu erzeugt (Platzhalter-Playlist mit vier Titeln). Der Waechter oeffnet jetzt jedes getrackte `.lshow` und jede Datei mit ZIP-Kennung und prueft alle Text-Eintraege mit `pruefe_oeffentlich()` (Pfad-Teil ueberall, Namensteil mit der lokalen Liste), mit Gegenprobe an kuenstlichen Archiven. Test `tests/test_priv8_demo_generator_neutrale_pfade.py` faehrt den Generator mit einem Musikordner im Wegwerf-Verzeichnis.

**Offen:** Die Git-Historie wird nicht umgeschrieben (Projektregel, wie PRIV-01/03): Name und Pfad bleiben in den frueheren Staenden der Show oeffentlich einsehbar. Ob das bereinigt werden soll, entscheidet der Projektinhaber gesondert.
