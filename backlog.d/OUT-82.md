ID: OUT-82
Prioritaet: P2
Status: teils
Status-Notiz: DDP-Ausgabe, WLED-Suche und Matrix-Verteilung gebaut; Abnahme am echten WLED offen
Titel: Pixel-Ausgabe an LED-Controller: WLED ueber WLAN und gaengige Pixel-Protokolle

**Herkunft:** Wunsch des Betreibers vom 22.11.2026: LED-Matrizen auch ueber WLAN (WLED) und ueber Standardprotokolle namhafter Hersteller ansteuern.

**Ziel:** Zuerst eine kurze Recherche mit Beleg (Herstellerdoku), welche Protokolle und Controller abgedeckt werden sollen: WLED (DDP, E1.31/sACN, Art-Net; Echtzeit-Modus), Pixel-Controller wie Advatek PixLite, ENTTEC Pixel-Octo, Falcon (Art-Net/sACN, viele Universen), Philips Color Kinetics (KiNET). Dann bauen: Ausgabe-Ziel „Pixel-Controller“ mit Geraetesuche im Netz (WLED per mDNS/JSON-API), automatische Universen-Aufteilung fuer grosse Pixelzahlen, DDP als Weg ohne 512-Kanal-Grenze. Ausgabe nur ueber den vorhandenen gesperrten Ausgabeweg (Probelauf bleibt ohne Ausgabe).

**Erledigt, wenn:** ein WLED-Geraet im Netz gefunden und eine Matrix darauf bildsynchron ausgegeben wird (Test gegen einen Schein-Empfaenger, Abnahme am echten Geraet), Art-Net/sACN-Pixelcontroller mit mehreren Universen funktionieren, Recherche-Ergebnis in docs/.

**Geliefert (22.11.2026):** Recherche in docs/PIXEL_CONTROLLER.md (WLED-Doku verlinkt; die DDP-Spezifikationsseite und die Herstellerseiten von Advatek/ENTTEC waren nicht abrufbar, das steht dort). Neue Ausgabe-Art „DDP (WLED)“ im Reiter Universen: alle Universen derselben Ziel-IP gehen als ein DDP-Strom hinaus (Offset je Universum in der Spalte „Ext. Universum“, Pakete bis 1440 Byte, Push nur im letzten), mit Blackout, Grand Master und Laser-NOT-AUS je Ausgabeweg wie Art-Net/sACN, gesperrt im Probelauf (STAB-39). WLED-Suche ohne neue Abhaengigkeit: mDNS-Anfrage nach _wled._tcp, sonst manuelle IP, je Treffer /json/info (Name, LED-Zahl) mit kurzer Zeitgrenze (src/core/dmx/wled.py). Matrix-Verteilung: wled.ddp_verteilung rechnet fuer eine Matrix aus dem LED-Matrix-Assistenten Universum und Offset je Teil; Anleitung „Ausgabe einrichten“ Abschnitt 4b. Art-Net/sACN-Pixelcontroller laufen ueber die vorhandenen Ausgaben (je Universum eine Zeile). Test tests/test_out82_ddp_wled.py.

**Offen:** Abnahme an einem echten WLED-Geraet (Bildsynchronitaet, WLAN-Last); Knopf „WLED suchen“ im Dialog und Assistenten-Seite fuer die Matrix-Verteilung (Funktionen stehen, Oberflaeche fehlt); Schlussbild fuer DDP im Fall eines haengenden Ausgabe-Threads; KiNET nicht umgesetzt.
