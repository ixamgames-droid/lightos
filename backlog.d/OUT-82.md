ID: OUT-82
Prioritaet: P2
Status: todo
Titel: Pixel-Ausgabe an LED-Controller: WLED ueber WLAN und gaengige Pixel-Protokolle

**Herkunft:** Wunsch des Betreibers vom 22.11.2026: LED-Matrizen auch ueber WLAN (WLED) und ueber Standardprotokolle namhafter Hersteller ansteuern.

**Ziel:** Zuerst eine kurze Recherche mit Beleg (Herstellerdoku), welche Protokolle und Controller abgedeckt werden sollen: WLED (DDP, E1.31/sACN, Art-Net; Echtzeit-Modus), Pixel-Controller wie Advatek PixLite, ENTTEC Pixel-Octo, Falcon (Art-Net/sACN, viele Universen), Philips Color Kinetics (KiNET). Dann bauen: Ausgabe-Ziel „Pixel-Controller“ mit Geraetesuche im Netz (WLED per mDNS/JSON-API), automatische Universen-Aufteilung fuer grosse Pixelzahlen, DDP als Weg ohne 512-Kanal-Grenze. Ausgabe nur ueber den vorhandenen gesperrten Ausgabeweg (Probelauf bleibt ohne Ausgabe).

**Erledigt, wenn:** ein WLED-Geraet im Netz gefunden und eine Matrix darauf bildsynchron ausgegeben wird (Test gegen einen Schein-Empfaenger, Abnahme am echten Geraet), Art-Net/sACN-Pixelcontroller mit mehreren Universen funktionieren, Recherche-Ergebnis in docs/.
