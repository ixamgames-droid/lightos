# udmx / udmx_process — uDMX-Adapter über rohes USB

## Zweck

**OUT-68:** Ausgabe-Art „uDMX (USB)" für Adapter ohne COM-Port (Anyma uDMX und
Nachbauten, CYL-6602 „USB-DMX512"). `src/core/dmx/udmx.py` ist der Treiber (Erkennen,
Öffnen, Senden, Schließen), `src/core/dmx/udmx_process.py` entkoppelt das Senden vom
44-Hz-Ausgabe-Thread.

## Protokoll

Keine Endpunkte — alles sind Vendor-Control-Transfers an das Gerät:

| Feld | Wert |
|---|---|
| `bmRequestType` | `0x40` |
| `bRequest` | `2` (Kanalbereich) — **die einzige Nummer, die LightOS sendet** |
| `wValue` | Anzahl der Kanäle (immer 512) |
| `wIndex` | Startkanal, 0-basiert (immer 0) |
| Daten | die 512 Kanalwerte |
| Zeitlimit | `TIMEOUT_MS = 250` |

uDMX kennt einen Bootloader-Befehl (`0xf8`). Die Request-Nummer ist deshalb eine
Konstante und kein Parameter; ein Test hält fest, dass es genau eine Sende-Stelle gibt.

**Jedes Bild wird ganz gesendet, in jedem Takt.** „Nur geänderte Bereiche" wurde
geprüft und verworfen: ein volles Bild (~17 ms am Low-Speed-Adapter) passt in den
44-Hz-Takt; der Adapter hält seinen eigenen Stand und weicht nach Neustecken oder
einem verlorenen Transfer sonst unbemerkt ab; Blackout und NOT-AUS erreichen ihn so
ohne Sonderweg.

## Erkennung

Gerätetabelle `BEKANNTE_GERAETE`:

| Kennung | Gerät | Zusatzprüfung |
|---|---|---|
| `2008:1066` | CYL-6602 / Sun-light USBDMX512 | keine |
| `16c0:05dc` | Anyma uDMX | Hersteller `www.anyma.ch` **und** Produkt `uDMX` |

`16c0:05dc` ist eine geteilte Kennung (V-USB). Passt der Name nicht, ist es kein uDMX.
Lässt er sich nicht lesen (fehlende Berechtigung), gilt das Gerät als unbestätigt und
wird nicht angesprochen. Texte werden nur von Geräten gelesen, deren Kennung in der
Tabelle steht.

Adapter-Schlüssel (steht als `patch` in `universes.json`): `vid:pid#seriennummer`,
sonst `vid:pid@anschluss` (z. B. `2008:1066@1-2`), sonst `vid:pid`. `waehle()` rät nie:
mit Seriennummer nur genau dieser Adapter; mit Anschluss dieser Anschluss, ersatzweise
der **einzige** Adapter dieser Kennung; ohne beides genau einer, sonst „mehrdeutig".

Sind **mehrere** uDMX-Ausgänge eingerichtet, gilt `streng`: nur noch der exakte Treffer
(Seriennummer oder genau dieser Anschluss). Der Ersatz „der einzige vorhandene" entfällt
dann, weil das der Adapter eines anderen Universums sein kann, dessen eigener gerade
abgezogen ist – zwei Universen sendeten sonst abwechselnd auf denselben Ausgang. Ein
Schlüssel ohne Seriennummer und Anschluss sendet in diesem Fall gar nicht („mehrere
Adapter – bitte einen auswählen"). Der OutputManager führt das nach
(`_udmx_streng_nachfuehren` → `setze_streng` der Sender), auch für einen bereits
ersatzweise gehaltenen Adapter.

## Konfiguration / Schalter

| Schalter | Wirkung |
|---|---|
| `pyusb` + libusb-1.0 | Optionale Abhängigkeit, erst im Sender geladen (`_usb_laden`). Fehlt sie: Grund `G_PYUSB_FEHLT` / `G_LIBUSB_FEHLT`, die App läuft weiter. `libusb-package` wird genutzt, wenn installiert. |
| `LIGHTOS_KEIN_USB` (Env) | Rohes USB ganz abschalten: nichts wird geladen oder aufgezählt. `tests/conftest.py` setzt es. |
| `LIGHTOS_SERIAL_INPROC` (Env) | Gesetzt → Sende-**Thread** (`UdmxThreadProxy`) statt Sende-Prozess. Auswahl in `output_manager._make_udmx_device`. |
| `Udmx.FAIL_LIMIT = 5` | Fehlversuche in Folge bis „Ausfall" (Zeitlimit/Übertragungsfehler). Abgezogen, keine Rechte, kein Treiber gelten sofort. |
| `Udmx.RECONNECT_EVERY_S = 2.0` | Drossel für das Wiederfinden des Adapters. |

## Threading- / Prozessmodell

- **Standard: eigener Prozess** (`UdmxProcessProxy`, Unterklasse von
  [`EnttecProcessProxy`](serial_process.md)). libusb ist nativer Code; ein Absturz oder
  ein im Treiber hängender Transfer trifft nur den Sende-Prozess. Neustart,
  Elternwache und Windows-Job werden geerbt; die Sende-Schleife ist dieselbe
  (`_serial_worker_loop`).
- **Rückfall: eigener Thread** (`UdmxThreadProxy`) — wenn sich kein Prozess starten
  lässt oder `LIGHTOS_SERIAL_INPROC` gesetzt ist.
- In beiden Fällen legt `send_dmx()` nur das neueste Bild ab („das neueste gewinnt")
  und macht keinen USB-Aufruf. Der Ausgabe-Thread blockiert nie am Adapter.
- Die Adapter-Suche des Dialogs läuft in einem Hilfs-Thread, nie im UI-Thread.

## Fehler- / Zustandsmeldung

- `status()` (`ST_CONNECTING` / `ST_OK` / `ST_DISABLED`) wie beim Enttec-Proxy; dazu
  `grund()` (`udmx.G_*`), `grund_text()` (Satz + nächster Schritt) und `grund_kurz()`.
- `OutputManager.ausgabe_status()` führt den Weg als `"uDMX"`; sendet der Adapter
  nicht, steht `grund_kurz()` in `problem` — das Ausgabe-Banner (OUT-67) und die
  Statusleiste zeigen damit den Grund.
- Meldungen auf stderr einmal je Ausfallgrund und einmal bei Wiederkehr.

## Sicherheitsweg

- Der Treiber verändert das Bild nicht. Blackout, Grand Master, Ziel-Blackout,
  Laser-Aus-Werte und Laser-NOT-AUS wirken in `OutputManager._send_all`, bevor der
  Adapter das Bild bekommt — gleiche Stelle und Reihenfolge wie beim Enttec.
- NOT-AUS je Ausgabeweg (OUT-64): alle uDMX-Ausgänge teilen sich den Weg-Schlüssel
  `("udmx", None)`, weil Adapter ohne Seriennummer nicht sicher unterscheidbar sind.
- `close()` sendet kein „alles auf 0". Der Adapter hält vermutlich sein letztes Bild,
  wenn Kabel oder Rechner ausfallen (nicht gemessen).

## Stand der Prüfung

Am Gerät CYL-6602 getestet: Kommunikation ja; Ausgang mit angeschlossenem Gerät noch
nicht bestätigt; OUT2 ungeprüft. Anyma uDMX und der STALL-Sonderfall (ein STALL gilt
dort wie bei OLA als Erfolg) sind nur mit Attrappe getestet. Windows/WinUSB ungeprüft.

## Gekoppelte Module

`output_manager.py` (`_udmx_outputs`, `add_udmx`, `_weg_udmx`, `_send_all`) ·
`app_state.apply_output_config` (`output == "uDMX"`) ·
`src/ui/widgets/output_config.py` (Reiter „uDMX (USB)", `AUSGABE_TYPEN`) ·
`diagnose_log.udmx_infos`, `selbsttest.OPTIONALE_MODULE` ·
`packaging/linux/60-lightos-udmx.rules` · `INSTALL.md` („uDMX-Adapter (USB)").

## Tests

`tests/test_out68_udmx_treiber.py`, `tests/test_out68_udmx_ausgabe.py` — nur mit der
Attrappe `tests/_out68_usb_attrappe.py`, nie mit einem echten Gerät.
