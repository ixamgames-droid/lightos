# Unterstützte DMX-Interfaces

> Welche DMX-Interfaces LightOS kennt, was jedes braucht — und was du tun kannst, wenn
> deines nicht dabei ist. Die Tabelle ist dieselbe, mit der der Assistent
> **Interface einrichten…** arbeitet (Menü **Ausgabe** oder Knopf oben im Dialog
> *Ausgabe konfigurieren*). Wie du einen Ausgang anlegst, zeigt
> [Ausgabe einrichten](ANLEITUNG.md).

**LightOS installiert keine Treiber und ändert keine Systemeinstellungen.** Es erkennt,
was angeschlossen ist, sagt, was fehlt, und verlinkt die Seite des Herstellers. Unter
Linux zeigt es den nötigen Befehl zum Kopieren an — ausführen musst du ihn selbst.

## Was die Spalten bedeuten

- **Status in LightOS**
  - *unterstützt: Enttec / uDMX / ArtNet / sACN* — lässt sich als Ausgang einrichten;
    das Wort nennt die Ausgabe-Art in der Universen-Tabelle.
  - *geplant* — wird erkannt und benannt, aber noch nicht angesteuert.
  - *nicht unterstützt — Art-Net-Adapter nehmen* — eigenes oder geschütztes Protokoll.
    Ausweg: ein Ethernet→DMX-Adapter, siehe unten.
- **Geprüft**
  - *am Gerät getestet* bedeutet: mit genau diesem Gerät ausprobiert; in Klammern steht,
    was und unter welchem Betriebssystem.
  - *nach Spezifikation* — nach der veröffentlichten Beschreibung gebaut, ohne das Gerät
    in der Hand gehabt zu haben.
- **USB-Kennung** — Hersteller- und Produktnummer, an der das Betriebssystem das Gerät
  erkennt. „+ Name“ heißt: die Nummer allein reicht nicht, LightOS prüft zusätzlich den
  Gerätenamen. „(vermutet)“ heißt: die Zuordnung ist nicht aus einer nachlesbaren Quelle
  belegt.

## Kompatibilitätsliste

<!-- INTERFACE-TABELLE:ANFANG (erzeugt aus src/core/dmx/interfaces.py) -->
| Gerät | USB-Kennung | Status in LightOS | Geprüft | Linux | Windows-Treiber |
|---|---|---|---|---|---|
| Enttec DMX USB Pro Mk2 (1. Universum) | `0403:6001` + Name (vermutet) | unterstützt: Enttec | nach Spezifikation | Kein Treiber nötig (im Kernel). Das Benutzerkonto muss in der Gruppe dialout sein; danach einmal ab- und wieder anmelden. | FTDI VCP (kommt meist über Windows Update) — [Herstellerseite](https://ftdichip.com/drivers/vcp-drivers/) |
| Enttec DMX USB Pro | `0403:6001` + Name | unterstützt: Enttec | nach Spezifikation | Kein Treiber nötig (im Kernel). Das Benutzerkonto muss in der Gruppe dialout sein; danach einmal ab- und wieder anmelden. | FTDI VCP (kommt meist über Windows Update) — [Herstellerseite](https://ftdichip.com/drivers/vcp-drivers/) |
| DMXking ultraDMX | `0403:6001` + Name | unterstützt: Enttec | nach Spezifikation | Kein Treiber nötig (im Kernel). Das Benutzerkonto muss in der Gruppe dialout sein; danach einmal ab- und wieder anmelden. | FTDI VCP (kommt meist über Windows Update) — [Herstellerseite](https://ftdichip.com/drivers/vcp-drivers/) |
| DMXIS | `0403:6001` + Name | unterstützt: Enttec | nach Spezifikation | Kein Treiber nötig (im Kernel). Das Benutzerkonto muss in der Gruppe dialout sein; danach einmal ab- und wieder anmelden. | FTDI VCP (kommt meist über Windows Update) — [Herstellerseite](https://ftdichip.com/drivers/vcp-drivers/) |
| Vince USB-DMX512 | `0403:6001` + Name | nicht unterstützt — Art-Net-Adapter nehmen | nicht unterstützt | Wird von LightOS nicht angesprochen. | — |
| FTDI-Adapter (FT232) — Enttec Pro, Open DMX oder Eurolite Pro Mk2? | `0403:6001` | unterstützt: Enttec | am Gerät getestet (Linux, ein Pro-kompatibler FT232-Adapter über die Art „Enttec“; „Open DMX“-Kabel sind geplant) | Kein Treiber nötig (im Kernel). Das Benutzerkonto muss in der Gruppe dialout sein; danach einmal ab- und wieder anmelden. | FTDI VCP (kommt meist über Windows Update) — [Herstellerseite](https://ftdichip.com/drivers/vcp-drivers/) |
| FTDI FT2232 (zwei Kanäle) | `0403:6010` (vermutet) | geplant | geplant | Kein Treiber nötig (im Kernel). Das Benutzerkonto muss in der Gruppe dialout sein; danach einmal ab- und wieder anmelden. | FTDI VCP (kommt meist über Windows Update) — [Herstellerseite](https://ftdichip.com/drivers/vcp-drivers/) |
| FTDI FT232H | `0403:6014` (vermutet) | geplant | geplant | Kein Treiber nötig (im Kernel). Das Benutzerkonto muss in der Gruppe dialout sein; danach einmal ab- und wieder anmelden. | FTDI VCP (kommt meist über Windows Update) — [Herstellerseite](https://ftdichip.com/drivers/vcp-drivers/) |
| FTDI FT230X / FT231X | `0403:6015` (vermutet) | geplant | geplant | Kein Treiber nötig (im Kernel). Das Benutzerkonto muss in der Gruppe dialout sein; danach einmal ab- und wieder anmelden. | FTDI VCP (kommt meist über Windows Update) — [Herstellerseite](https://ftdichip.com/drivers/vcp-drivers/) |
| DMX4ALL USB-Interface | `0403:c850` | nicht unterstützt — Art-Net-Adapter nehmen | nicht unterstützt | Wird von LightOS nicht angesprochen. | — |
| Eurolite USB-DMX512 PRO (altes Modell) | `04d8:fa63` + Name | geplant | geplant | Kein Treiber nötig (im Kernel). Das Benutzerkonto muss in der Gruppe dialout sein; danach einmal ab- und wieder anmelden. | in Windows enthalten (usbser) — [Herstellerseite](https://www.steinigke.de/) |
| WCH CH340 (z. B. Arduino Nano-Nachbau) | `1a86:7523` | geplant | geplant | Kein Treiber nötig (im Kernel). Das Benutzerkonto muss in der Gruppe dialout sein; danach einmal ab- und wieder anmelden. Erscheint ein CH340 nicht als /dev/ttyUSB*, hält ihn oft der Braille-Dienst brltty fest. | CH341SER (WCH) — [Herstellerseite](https://www.wch-ic.com/downloads/CH341SER_EXE.html) |
| WCH CH341 | `1a86:5523` (vermutet) | geplant | geplant | Kein Treiber nötig (im Kernel). Das Benutzerkonto muss in der Gruppe dialout sein; danach einmal ab- und wieder anmelden. Erscheint ein CH340 nicht als /dev/ttyUSB*, hält ihn oft der Braille-Dienst brltty fest. | CH341SER (WCH) — [Herstellerseite](https://www.wch-ic.com/downloads/CH341SER_EXE.html) |
| WCH CH9102 | `1a86:55d4` (vermutet) | geplant | geplant | Kein Treiber nötig (im Kernel). Das Benutzerkonto muss in der Gruppe dialout sein; danach einmal ab- und wieder anmelden. Erscheint ein CH340 nicht als /dev/ttyUSB*, hält ihn oft der Braille-Dienst brltty fest. | CH341SER (WCH) — [Herstellerseite](https://www.wch-ic.com/downloads/CH341SER_EXE.html) |
| Silicon Labs CP210x (z. B. ESP32-Board) | `10c4:ea60` | geplant | geplant | Kein Treiber nötig (im Kernel). Das Benutzerkonto muss in der Gruppe dialout sein; danach einmal ab- und wieder anmelden. Erscheint ein CH340 nicht als /dev/ttyUSB*, hält ihn oft der Braille-Dienst brltty fest. | CP210x Universal Windows Driver (Silicon Labs) — [Herstellerseite](https://www.silabs.com/developer-tools/usb-to-uart-bridge-vcp-drivers) |
| Arduino (Originalboard) | `2341:*` (vermutet) | geplant | geplant | Kein Treiber nötig (im Kernel). Das Benutzerkonto muss in der Gruppe dialout sein; danach einmal ab- und wieder anmelden. Erscheint ein CH340 nicht als /dev/ttyUSB*, hält ihn oft der Braille-Dienst brltty fest. | in Windows enthalten; sonst mit der Arduino-IDE — [Herstellerseite](https://www.arduino.cc/en/software) |
| Arduino (arduino.org-Board) | `2a03:*` (vermutet) | geplant | geplant | Kein Treiber nötig (im Kernel). Das Benutzerkonto muss in der Gruppe dialout sein; danach einmal ab- und wieder anmelden. Erscheint ein CH340 nicht als /dev/ttyUSB*, hält ihn oft der Braille-Dienst brltty fest. | in Windows enthalten; sonst mit der Arduino-IDE — [Herstellerseite](https://www.arduino.cc/en/software) |
| Espressif ESP32 (eigener USB-Anschluss) | `303a:*` (vermutet) | geplant | geplant | Kein Treiber nötig (im Kernel). Das Benutzerkonto muss in der Gruppe dialout sein; danach einmal ab- und wieder anmelden. Erscheint ein CH340 nicht als /dev/ttyUSB*, hält ihn oft der Braille-Dienst brltty fest. | in Windows enthalten (usbser, ab Windows 10) |
| CYL-6602 „USB-DMX512“ (Sun-light USBDMX512) | `2008:1066` | unterstützt: uDMX | am Gerät getestet (Linux, Kommunikation; Ausgang mit Gerät noch offen) | Kein Treiber nötig. Einmalig die udev-Regel packaging/linux/60-lightos-udmx.rules einspielen und den Adapter neu einstecken. | WinUSB — muss dem Gerät einmalig von Hand zugewiesen werden (noch nicht am Gerät erprobt) — [Herstellerseite](https://learn.microsoft.com/windows-hardware/drivers/usbcon/winusb-installation) |
| Anyma uDMX und Nachbauten | `16c0:05dc` + Name | unterstützt: uDMX | nach Spezifikation | Kein Treiber nötig. Einmalig die udev-Regel packaging/linux/60-lightos-udmx.rules einspielen und den Adapter neu einstecken. | WinUSB — muss dem Gerät einmalig von Hand zugewiesen werden (noch nicht am Gerät erprobt) — [Herstellerseite](https://learn.microsoft.com/windows-hardware/drivers/usbcon/winusb-installation) |
| AVLdiy D512 | `03eb:8888` + Name | geplant | geplant | Kein Treiber nötig; Zugriffsrecht per udev-Regel (folgt). | WinUSB — von Hand zuzuweisen — [Herstellerseite](https://learn.microsoft.com/windows-hardware/drivers/usbcon/winusb-installation) |
| Velleman K8062 / VM116 | `10cf:8062` | nicht unterstützt — Art-Net-Adapter nehmen | nicht unterstützt | Wird von LightOS nicht angesprochen. | — |
| DMX4ALL NanoDMX | `03eb:2018` | nicht unterstützt — Art-Net-Adapter nehmen | nicht unterstützt | Wird von LightOS nicht angesprochen. | — |
| Peperoni / Lighting Solutions | `0ce1:*` | nicht unterstützt — Art-Net-Adapter nehmen | nicht unterstützt | Wird von LightOS nicht angesprochen. | — |
| DMXCreator 512 Basic | `0a30:0002` | nicht unterstützt — Art-Net-Adapter nehmen | nicht unterstützt | Wird von LightOS nicht angesprochen. | — |
| ShowJockey SJ-DMX-U1 | `0483:57fe` | nicht unterstützt — Art-Net-Adapter nehmen | nicht unterstützt | Wird von LightOS nicht angesprochen. | — |
| FX5 USB DMX | `16c0:088b` | nicht unterstützt — Art-Net-Adapter nehmen | nicht unterstützt | Wird von LightOS nicht angesprochen. | in Windows enthalten (HID) |
| Digital Enlightenment USB DMX | `04b4:0f1f` | nicht unterstützt — Art-Net-Adapter nehmen | nicht unterstützt | Wird von LightOS nicht angesprochen. | in Windows enthalten (HID) |
| DMXControl Nodle U1 | `16d0:0830` | nicht unterstützt — Art-Net-Adapter nehmen | nicht unterstützt | Wird von LightOS nicht angesprochen. | in Windows enthalten (HID) |
| DMXControl Nodle R4S | `16d0:0833` | nicht unterstützt — Art-Net-Adapter nehmen | nicht unterstützt | Wird von LightOS nicht angesprochen. | in Windows enthalten (HID) |
| Sunlite USBDMX2 (ohne Firmware) | `0962:2000` | nicht unterstützt — Art-Net-Adapter nehmen | nicht unterstützt | Wird von LightOS nicht angesprochen. | nur mit der Software des Herstellers |
| Sunlite USBDMX2 | `0962:2001` | nicht unterstützt — Art-Net-Adapter nehmen | nicht unterstützt | Wird von LightOS nicht angesprochen. | nur mit der Software des Herstellers |
| Nicolaudie / Sunlite (SIUDI, SUT) | am Namen (vermutet) | nicht unterstützt — Art-Net-Adapter nehmen | nicht unterstützt | Wird von LightOS nicht angesprochen. | nur mit der Software des Herstellers |
| ADJ myDMX | am Namen (vermutet) | nicht unterstützt — Art-Net-Adapter nehmen | nicht unterstützt | Wird von LightOS nicht angesprochen. | nur mit der Software des Herstellers |
| Chauvet Xpress | am Namen (vermutet) | nicht unterstützt — Art-Net-Adapter nehmen | nicht unterstützt | Wird von LightOS nicht angesprochen. | nur mit der Software des Herstellers |
| Art-Net-Adapter aller Hersteller, ESP32-Selbstbau, Pi mit OLA | Netzwerk | unterstützt: ArtNet | nach Spezifikation | Kein Treiber. PC und Adapter brauchen Adressen im selben Netz. | keiner; Firewall-Freigabe für LightOS |
| sACN-Adapter (E1.31) | Netzwerk | unterstützt: sACN | nach Spezifikation | Kein Treiber. PC und Adapter brauchen Adressen im selben Netz. | keiner; Firewall-Freigabe für LightOS |
<!-- INTERFACE-TABELLE:ENDE -->

Die Kennungen stammen aus den öffentlich einsehbaren Gerätelisten der freien Programme
OLA und QLC+ sowie aus eigener Messung (`2008:1066`).

### Der Sonderfall `0403:6001` (FTDI-Adapter — Typ unklar)

`0403:6001` ist die Nummer des verbauten FTDI-Chips, nicht die eines bestimmten
DMX-Interfaces. Dieselbe Nummer tragen der Enttec DMX USB Pro, einfache
„Open DMX“-Kabel, der Eurolite USB-DMX512 PRO Mk2 und beliebige USB-Seriell-Adapter.
Nennt sich das Gerät selbst „DMX USB PRO“, ist die Sache klar. Meldet es sich nur als
„FT232R USB UART“, zeigt der Assistent **Typ unklar**:

- Ist es ein Enttec-Pro-kompatibler Adapter, läuft er über die Ausgabe-Art **Enttec**.
  Einrichten, dann im Reiter **Testsignal** ausprobieren.
- Ist es ein reines „Open DMX“-Kabel, kommt am Gerät nichts Brauchbares an — diese
  Bauart wird noch nicht unterstützt (geplant).

Ein bereits eingerichteter Ausgang bleibt, wie er ist: LightOS ändert an gespeicherten
Ausgaben nichts, nur weil der Typ nicht ablesbar ist.

## Treiber und Zugriffsrechte

### Linux

Linux bringt die Treiber für FTDI, CH340 und CP210x im Kernel mit. Nötig sind nur
Zugriffsrechte:

- **Serielle Adapter** (FTDI, CH340, CP210x, Arduino): das Benutzerkonto muss in der
  Gruppe `dialout` sein.

  ```bash
  sudo usermod -aG dialout "$USER"
  ```

  Danach einmal ab- und wieder anmelden. Taucht ein CH340-Adapter gar nicht als
  `/dev/ttyUSB*` auf, hält ihn meist der Braille-Dienst `brltty` fest.
- **uDMX-Adapter** (ohne COM-Port): einmalig die udev-Regel einspielen.

  ```bash
  sudo cp packaging/linux/60-lightos-udmx.rules /etc/udev/rules.d/
  sudo udevadm control --reload-rules && sudo udevadm trigger
  sudo usermod -aG plugdev "$USER"
  ```

  Danach den Adapter neu einstecken. Details: [INSTALL.md](../../INSTALL.md#udmx-adapter-usb).

### Windows

- **FTDI** — Windows holt den Treiber meist selbst über Windows Update. Auf einem
  Rechner ohne Internet vorher besorgen: <https://ftdichip.com/drivers/vcp-drivers/>
- **CH340 / CH341** (viele Arduino-Nachbauten) — Treiber `CH341SER` des Herstellers
  WCH: <https://www.wch-ic.com/downloads/CH341SER_EXE.html>
- **CP210x** (viele ESP32-Boards) — Treiber von Silicon Labs:
  <https://www.silabs.com/developer-tools/usb-to-uart-bridge-vcp-drivers>
- **uDMX-Adapter** — für sie gibt es keinen eigenen Treiber. Dem Gerät muss einmalig
  der in Windows enthaltene WinUSB-Treiber zugewiesen werden; Microsoft beschreibt den
  Weg hier: <https://learn.microsoft.com/windows-hardware/drivers/usbcon/winusb-installation>.
  Dieser Weg ist mit LightOS noch nicht am Gerät erprobt.

Zeigt der Assistent **Treiber fehlt**, sieht Windows das Gerät am USB, hat ihm aber
keinen COM-Port gegeben — dann fehlt genau der Treiber aus dieser Liste.

## Ethernet→DMX per LAN-Kabel direkt am PC

Ein Art-Net- oder sACN-Adapter braucht keinen Treiber und funktioniert mit jedem
Betriebssystem. Er muss nicht an einem Router hängen: ein LAN-Kabel direkt vom PC zum
Adapter genügt. Dann vergibt aber niemand automatisch Adressen — du stellst sie von
Hand ein. **Die Adresse des PCs stellst du im Betriebssystem ein, nicht in LightOS.**

1. **Adresse des Adapters herausfinden.** Sie steht auf dem Gerät, in seiner Anleitung
   oder in seinem Einstellprogramm. Beispiel: `192.168.1.50`. Viele Art-Net-Geräte
   haben ab Werk eine Adresse `2.x.x.x` oder `10.x.x.x` mit der Maske `255.0.0.0`.
2. **LAN-Kabel einstecken**, Adapter einschalten. An der Netzwerkbuchse sollte die
   Verbindungslampe leuchten.
3. **Dem PC eine feste Adresse im selben Netz geben** — im Betriebssystem, an genau
   der Netzwerkkarte, an der das Kabel steckt:
   - Die ersten Zahlen wie beim Adapter, die letzte anders. Zum Adapter `192.168.1.50`
     passt zum Beispiel `192.168.1.10`, Maske `255.255.255.0`. Zum Adapter `2.0.0.5`
     passt `2.0.0.10`, Maske `255.0.0.0`.
   - Gateway und DNS bleiben leer.
   - Windows: *Einstellungen → Netzwerk und Internet → Ethernet → IP-Zuweisung →
     Bearbeiten → Manuell*. Linux Mint: *Netzwerkverbindungen → Kabelverbindung →
     IPv4 → Methode „Manuell“*.
4. **In LightOS nachsehen:** Assistent **Interface einrichten…**, Reiter
   **Netzwerk (Art-Net / sACN)**. Dort steht unter *Adressen dieses Rechners*, welche
   Adresse der PC jetzt hat. LightOS zeigt sie nur an und ändert nichts.
5. **Ausgang anlegen:** **Art-Net-Ausgabe einrichten** führt in den Reiter **Art-Net**.
   Dort die richtige **Netzwerkkarte** wählen, als Ziel die Adresse des Adapters
   eintragen (oder Broadcast lassen), Universum wählen, **Übernehmen**. Die Schritte im
   Einzelnen: [Ausgabe einrichten, Abschnitt Art-Net](ANLEITUNG.md#3-art-net).
6. **Prüfen:** Reagiert nichts, zuerst `ping 192.168.1.50` (mit der Adresse deines
   Adapters). Kommt keine Antwort, stimmt die Adresse des PCs oder das Kabel nicht —
   siehe [Netzwerk-Falle](ANLEITUNG.md#netzwerk-falle-bei-art-net-und-sacn).

Der PC kann dabei gleichzeitig per WLAN im Internet bleiben: das Lichtnetz läuft über
die Kabel-Netzwerkkarte, das WLAN über die andere. Art-Net-Geräte automatisch suchen
kann LightOS noch nicht.

## Testsignal

Im Assistenten, Reiter **Testsignal**, steht je eingerichtetem Ausgang ein Knopf
**Testsignal senden**. Er fährt Kanal 1 fünf Sekunden langsam auf und ab und setzt ihn
danach auf 0 — ein Dimmer oder Scheinwerfer auf Adresse 1 wird dabei heller und dunkler.

- Vor dem Senden fragt LightOS nach, ob an diesem Ausgang keine Laser hängen.
- **In Universen mit gepatchtem Laser ist das Testsignal gesperrt**, ebenso bei
  ausgelöstem Laser-NOT-AUS.
- Blackout, Grand Master und NOT-AUS gelten weiter: das Testsignal läuft über denselben
  Weg wie jede andere Ausgabe.

## Hinweis beim Einstecken

Steckst du im Betrieb ein bekanntes Interface ein, erscheint nach ein paar Sekunden
unten in der Statusleiste **Neues DMX-Interface erkannt: … — Einrichten…**. Ein Klick
öffnet den Assistenten, das **✕** schließt den Hinweis. Eingerichtet wird nichts von
selbst. Abschalten: Menü **Ausgabe → Hinweis bei neuem DMX-Interface**.
