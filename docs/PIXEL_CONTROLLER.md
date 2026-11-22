# Pixel-Controller: Protokolle und Quellen (OUT-82)

**Kurz:** WLED wird über **DDP** angesteuert (ein Strom ohne 512-Kanal-Grenze,
bildsynchron per Push-Flag). Große Pixel-Controller (Advatek PixLite, ENTTEC
Octo, Falcon) sprechen **Art-Net** und **sACN (E1.31)** mit vielen Universen —
das kann LightOS schon, je Universum eine Zeile im Reiter Universen.

Stand der Recherche: 22.11.2026. Beispiel-Adressen nur aus `192.0.2.0/24`.

## WLED

| Thema | Angabe | Quelle |
|---|---|---|
| DDP | UDP-Port 4048; Zeitstempel im Kopf werden ignoriert | [kno.wled.ge/interfaces/ddp](https://kno.wled.ge/interfaces/ddp/) |
| DDP-Modus | DDP läuft immer als „Multi RGB“, unabhängig vom DMX-Modus | [kno.wled.ge/interfaces/e1.31-dmx](https://kno.wled.ge/interfaces/e1.31-dmx/) |
| E1.31 / Art-Net | E1.31 eingebaut; Art-Net nach Umschalten in *Sync settings* + Neustart; 170 RGB-LEDs (510 Kanäle) je Universum, bis 9 Universen, für flüssige 40 fps höchstens 3 | dieselbe Seite |
| Geräteinfo | `GET /json/info`: `name` (Anzeigename), `leds.count` (LED-Zahl), `ver` | [kno.wled.ge/interfaces/json-api](https://kno.wled.ge/interfaces/json-api/) |
| Gerätesuche | WLED meldet sich per mDNS als Dienst `_wled._tcp` | WLED-Quellcode / json-api-Seite |
| Echtzeit | Web-Oberfläche ist im Echtzeit-Modus gesperrt; Helligkeit und Gamma aus WLED gelten weiter | [kno.wled.ge/interfaces/udp-realtime](https://kno.wled.ge/interfaces/udp-realtime/) |

## DDP (Distributed Display Protocol)

Spezifikation: [www.3waylabs.com/ddp](http://www.3waylabs.com/ddp/) (die Seite
war bei der Recherche nicht erreichbar; der Kopf unten entspricht der
Spezifikation und der WLED-Umsetzung).

| Byte | Inhalt |
|---|---|
| 0 | Flags `VV x T S R Q P`: Version 1 = `0x40`, Push = `0x01` |
| 1 | Sequenznummer (untere 4 Bit, 1–15; 0 = unbenutzt) |
| 2 | Datentyp `C R TTT SSS`: `0x0B` = RGB, 8 Bit |
| 3 | Ziel-ID, 1 = Standard-Ausgabe |
| 4–7 | Offset in Byte (big-endian) |
| 8–9 | Datenlänge in Byte (big-endian) |

Nutzlast höchstens 1440 Byte je Paket (480 RGB-Pixel). Das **Push-Flag** steht
nur im letzten Paket eines Bildes; der Empfänger zeigt das Bild dann auf einmal.

## Pixel-Controller mit vielen Universen

Die Zeilen fassen die Herstellerangaben zusammen; die Produkt-Detailseiten
waren bei der Recherche nicht abrufbar (Seiten umgezogen). Vor einem Kauf das
Datenblatt des konkreten Modells prüfen.

| Gerät | Protokolle | Hinweis | Quelle |
|---|---|---|---|
| Advatek PixLite | Art-Net, sACN (E1.31) | viele Universen je Ausgang, Einrichtung über Advatek Assistant | [advateklighting.com](https://www.advateklighting.com/) |
| ENTTEC Octo / Pixel-Octo | Art-Net, sACN, ENTTEC ESP | 8 Ausgänge, mehrere Universen je Ausgang | [enttec.com](https://www.enttec.com/) |
| Falcon F16/F48 | sACN (E1.31), Art-Net, DDP | verbreitet bei Weihnachtsbeleuchtung (xLights) | [pixelcontroller.com](https://pixelcontroller.com/) |
| Philips Color Kinetics | KiNET | eigenes Protokoll — in LightOS nicht umgesetzt | — |

## Was LightOS daraus macht

- **Neue Ausgabe-Art „DDP (WLED)“** (`src/core/dmx/ddp.py`): Universen mit
  derselben Ziel-IP bilden einen Strom; Offset je Universum in der Spalte
  „Ext. Universum“.
- **Gerätesuche** (`src/core/dmx/wled.py`): mDNS-Anfrage nach `_wled._tcp`
  ohne neue Abhängigkeit, sonst manuelle IP; je Treffer `/json/info` mit kurzer
  Zeitgrenze.
- **Matrix-Verteilung:** `wled.ddp_verteilung` rechnet für eine Matrix aus dem
  LED-Matrix-Assistenten Universum und Offset je Teil.
- Art-Net/sACN-Pixelcontroller: unverändert über die vorhandenen Ausgaben.
- Ausgabe nur in der echten App (STAB-39); im Probelauf geht nichts ins Netz.
