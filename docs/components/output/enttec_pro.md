# enttec_pro — EnttecPro

## Zweck

Ausgabe an einen **Enttec DMX USB Pro** über pyserial. `EnttecPro` öffnet einen
COM-Port, verpackt 512 DMX-Bytes ins Enttec-Framing (Label 6) und schreibt sie. Enthält
den Fehler-Watchdog und die Reconnect-Logik, die einen wackligen/abgezogenen USB-Stecker
überlebt, ohne LightOS abzuschießen.

## Konfiguration / Schalter

| Schalter | Wirkung |
|---|---|
| `ENTTEC_BAUD = 57600` | Serielle Baudrate. |
| `ENTTEC_VID = 0x0403`, `ENTTEC_PID = 0x6001` | VID/PID für die Auto-Erkennung (`find_enttec_port`). |
| `FAIL_LIMIT = 20` | So viele aufeinanderfolgende Schreib-Fehler werten den Port als tot (OUT-02). |
| `RECONNECT_EVERY_S = 3.0` | Drossel für Reconnect-Versuche, solange der Port als tot gilt. |
| `write_timeout = 0.5` | KRITISCH: ohne Timeout blockiert `write()` endlos und friert die 44-Hz-Engine ein; 0.5 s sind großzügig für ein 513-Byte-Paket bei 57600 Baud (~90 ms). |

Hilfsfunktionen: `find_enttec_port()` (Auto-Erkennung per VID/PID),
`list_serial_ports()` (alle COM-Ports).

## Threading- / Prozessmodell

Kein eigener Thread. Wird entweder direkt aus dem 44-Hz-Output-Thread des
`OutputManager` (bei `LIGHTOS_SERIAL_INPROC`) ODER innerhalb des Worker-Prozesses von
[`serial_process`](serial_process.md) betrieben. Keine internen Locks — die
Serialisierung übernimmt der Aufrufer (`OutputManager._io_lock` bzw. der Single-Thread-
Worker-Loop).

## Fehler- / Watchdog-Verhalten

- **OUT-02 Fehler-Watchdog:** `send_dmx` zählt aufeinanderfolgende Schreib-Fehler
  (`_note_fail`). Ab `FAIL_LIMIT` wird der Port als tot markiert und geschlossen
  (`_disable`) — kein weiteres 44-Hz-Hämmern auf ein abgezogenes USB-Gerät (jeder
  `WriteFile` darauf riskiert eine native, nicht fangbare Access Violation).
- Ein erfolgreicher Frame setzt den Zähler zurück → nur ein ANHALTENDER Abriss löst das
  Auto-Disable aus, kein einzelner Hickup.
- `is_open`-Guard: kein Schreiben auf ein bereits geschlossenes Handle.
- `_try_reconnect` öffnet den Port gedrosselt neu; gelingt es, reaktiviert sich die
  Ausgabe von selbst (ohne App-Neustart). `is_disabled()` für UI-Status.
- **Nur der eigene Dongle (OUT-66):** `_reconnect_ziel` wählt das Ziel des Reconnects.
  Bekannt ist die USB-Seriennummer (beim ersten Öffnen aus `comports()` gemerkt) → der
  Enttec mit dieser Nummer, auch an neuer COM-Nummer (SERIAL-02). Ohne Seriennummer →
  der eigene Portname, sonst ein anderer Port nur, wenn genau EIN Enttec sichtbar ist.
  Ports und Seriennummern anderer `EnttecPro`-Instanzen im selben Prozess scheiden aus;
  ist nichts eindeutig, wird der Versuch ausgelassen. Unter POSIX wird mit
  `exclusive=True` geöffnet (zwischen den Worker-Prozessen); hält jemand den
  KONFIGURIERTEN Port exklusiv, wird nur gewarnt und geteilt geöffnet (wie OUT-54).
  `konfig_port` bleibt beim Portwechsel stehen — er ist der Schlüssel der
  NOT-AUS-Sperre je Ausgabeweg (`OutputManager._weg_enttec`, OUT-64).
  Im Prozess-Proxy meldet der Worker den geoeffneten Port (`port_aktuell`) und die
  gelernte Seriennummer zurueck; ein neu gestarteter Worker bekommt sie mit
  (`EnttecPro(port, seriennr=…)`). Ohne Exklusiv-Sperre geoeffnet (fremder Halter)
  wird keine Seriennummer gelernt.
- **Ersatzgerät am eigenen Port (OUT-66, Review 2):** Steckt am KONFIGURIERTEN Port ein
  anderer Dongle als der gelernte, wird er übernommen und seine Seriennummer neu
  gelernt — beim ersten Öffnen wie beim Reconnect —, sofern keine ANDERE konfigurierte
  Enttec-Ausgabe diese Nummer kennt. Die Menge dieser fremden Nummern gibt der
  `OutputManager` jeder Ausgabe mit (beim Anlegen, laufend im Ausgabe-Thread, nach dem
  Entfernen; `setze_fremde_seriennr`, beim Proxy über ein gemeinsames Feld). Ein Dongle
  mit einer fremden Nummer wird nie genommen. Die Übernahme erscheint als `hinweis` in
  `OutputManager.ausgabe_status()` (Systeminfo, Tooltip der Ausgabe-Anzeige) und im Log.
- **Kein Ersatz, solange eine andere Ausgabe ihren Dongle nicht kennt (OUT-66, Runde 3):**
  Hat eine ANDERE konfigurierte Enttec-Ausgabe noch keine Seriennummer gelernt (Dongle
  fehlte seit dem Start oder seit „Übernehmen“), könnte der Ersatz genau ihr Dongle sein
  — zwei Universen tauschten still. Dann bleibt die Ausgabe dunkel; `hinweis` meldet
  „Nicht übernommen: anderer Enttec an … weil Ausgabe U2 (…) ihren Dongle noch nicht
  kennt“. Ausnahme: die andere Ausgabe ist gerade an ihrem EIGENEN konfigurierten Port
  verbunden (ihr Dongle ist nachweislich dort). Der `OutputManager` reicht diese
  Ausgaben als Einträge `?U<n> (<port>)` in derselben Fremdmenge mit (beim Proxy im
  selben gemeinsamen Feld). Mit nur EINER konfigurierten Enttec-Ausgabe wird ein Ersatz
  weiter übernommen.
- **„Früher eigen“ (Runde 3):** Wer einen Ersatz übernimmt, behält die alte Nummer
  (`frueher_seriennr`, beim Proxy ein weiteres gemeinsames Feld, ein neu gestarteter
  Worker bekommt sie mit). Der Manager sammelt sie je Universum (auch einen beobachteten
  Nummernwechsel) und gibt sie den ANDEREN Ausgaben als fremd mit — bis zum App-Neustart
  oder bis das Universum neu zugewiesen wird.
- **Toter Ausgang (Review 2):** `port_aktuell` nennt eine gefolgte Nummer nur, solange
  der Ausgang dort verbunden ist; `close_enttec_on_port` verdrängt einen toten Ausgang
  dort also nicht. Die NOT-AUS-Sperre liest zusätzlich `port_zuletzt` (bleibt nach dem
  Ausfall stehen — lieber eine Nummer zu viel gesperrt).
- **Grenze — Neustart (→ OUT-80):** die Seriennummer lebt nur zur Laufzeit. Vertauscht
  Linux beim Booten `ttyUSB0`/`ttyUSB1`, öffnet jedes Universum den Dongle des anderen
  und lernt ihn als eigenen (bestand schon vor OUT-66, Konfiguration über den
  Portnamen). Abhilfe geplant in OUT-80: Seriennummer in der Universums-Konfiguration,
  unter Linux `/dev/serial/by-id`.
- **Grenze — „Übernehmen“ nach Vertauschen zur Laufzeit (→ OUT-80):** „Übernehmen“ in der
  Ausgabe-Konfiguration legt jede Ausgabe neu an, ohne die gelernte Seriennummer und ohne
  die „früher eigenen“ Nummern. Wurden die Dongles vorher zur Laufzeit vertauscht
  eingesteckt, lernt danach jedes Universum den Dongle an seinem konfigurierten Port —
  also den des anderen. Ohne OUT-66 war das genauso; OUT-80 behebt beides, indem die
  Nummer in der Konfiguration steht und beim Anlegen mitgegeben wird.
- `close()` bricht/leert vorher den Output-Puffer, damit `CloseHandle()` nicht mit einem
  ausstehenden `WriteFile` kollidiert. Idempotent, fehlertolerant.

## Gekoppelte Module

- [`output_manager`](output_manager.md) — `_make_enttec_device` wählt In-Prozess
  `EnttecPro` (bei `LIGHTOS_SERIAL_INPROC`) oder den Prozess-Proxy.
- [`serial_process`](serial_process.md) — der Worker-Prozess betreibt intern einen
  `EnttecPro`.

## Tests

- `tests/test_enttec_pro.py`
- `tests/test_enttec_fail_watchdog.py`
- `tests/test_serial_status_reconnect.py` (SERIAL-02)
- `tests/test_out66_enttec_reconnect_eigener_port.py` (OUT-66)
- `tests/test_out66_ersatz_dongle_review2.py` (OUT-66, Ersatzgerät, Worker-Argumente, toter Ausgang)
- `tests/test_out66_ersatz_runde3.py` (OUT-66, kein Tausch mit ungelernter Ausgabe, Einzel-Dongle, „früher eigen“)

## Quelle

`src/core/dmx/enttec_pro.py:40` (Klasse), `:68` `send_dmx`, `:102` `_note_fail`,
`:108` `_disable`, `:122` `_try_reconnect`, `:150` `close`.
