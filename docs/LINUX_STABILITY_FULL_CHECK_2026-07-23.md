# LightOS Linux-Stabilitaetspruefung — 2026-07-23

## Ziel und System

Vollstaendige Stabilitaets- und Funktionspruefung der lokalen Installation auf
Linux Mint 22.3 (X11, Python 3.12.3, zwei 1920x1080-Touchdisplays).

Diese Datei wird waehrend der Pruefung fortlaufend ergaenzt. Sie dokumentiert
Befunde, Aenderungen, Verifikation und verbleibende Hardwaregrenzen.

## Ausgangslage

- LightOS-Start war zunaechst durch das fehlende Systempaket
  `libxcb-cursor0` blockiert; Paket wurde installiert.
- Zwei native Abstuerze am 23.07.2026 nachgewiesen:
  - 17:19:05: `SIGABRT`, Qt/PySide6 im Stack.
  - 17:26:10: `SIGSEGV`, PySide6 im Stack; `python-rtmidi` und laufende
    Audio-Capture-/MIDI-Threads waren geladen.
- `~/LightOS/crash.log` zeigte wiederholte ungeschuetzte
  `rtmidi.MidiIn()`-/`MidiOut()`-Fehler (`ALSA sequencer client object`) im
  Zwei-Sekunden-Rhythmus.
- Das Crash-Log belegte vier nahezu gleichzeitige Starts (PIDs 12836, 12860,
  12881 und 12885). Diese Prozesse konkurrierten um ALSA-Sequencer-Clients,
  Qt-Portale, WebEngine und Ausgabe-Sockets.
- Das offizielle Test-Gate brach bereits bei der Test-Sammlung ab, weil
  `soundcard` bei nicht erreichbarem PulseAudio `AssertionError` statt
  `ImportError` warf.
- Ressourcen waren unauffaellig: ca. 6,3 GiB RAM und 82 GiB Speicher frei;
  `pip check` meldete keine defekten Python-Abhaengigkeiten.

## Durchgefuehrte Aenderungen

1. Audio-Capture degradiert bei jedem Fehler waehrend des optionalen
   `soundcard`-Imports sauber, nicht nur bei `ImportError`.
2. RtMidi-Portscans sind pro Manager serialisiert.
3. RtMidi-Scanfehler liefern leere Portlisten statt die GUI zu beenden.
4. Ein 10-Sekunden-Circuit-Breaker verhindert einen Sturm nativer
   ALSA-Client-Erzeugungen; danach ist automatische Erholung moeglich.
5. Die MIDI-Ansicht besitzt zusaetzliche Guards fuer alternative Backends.
6. Regressionstests fuer PulseAudio-Import, RtMidi-Circuit-Breaker und
   MIDI-UI-Start ohne Backend wurden hinzugefuegt.
7. Portable Show-Patches: numerische Fixture-Profil-IDs werden beim Laden gegen
   gespeicherten Hersteller/Modellnamen validiert und bei abweichender lokaler
   Datenbank-ID remappt.
8. Der MainWindow-Close-Pfad zeigt unter `offscreen` keinen unbeantwortbaren
   modalen Speichern-Dialog mehr.
9. Eine betriebssystemweite Einzelinstanz-Sperre beendet Mehrfachstarts bereits
   vor Qt/ALSA/WebEngine. Damit kann ein mehrfacher Touch/Doppelklick keine
   konkurrierenden LightOS-Prozesse mehr erzeugen.
10. Der MTC-Portscan nutzt den geschuetzten MIDI-Manager-Scan statt bei jedem
    Refresh einen weiteren nativen ALSA-Client anzulegen.
11. Die Sektions-Tabs zeigen den Volltext, sobald das berechnete Textbudget
    exakt reicht; Qt-Glyph-Bearings kuerzen „Programmer“ bei 1440 px nicht mehr.
12. Das Janitor-Entwicklerwerkzeug normalisiert Windows-Pfade auch dann korrekt
    case-insensitiv, wenn die Analyse unter Linux laeuft.
13. Die ausgelieferte `data/universes.json` enthielt ein Test-Enttec
    (`COM_FAKE`) sowie aktive Art-Net-Broadcast- und sACN-Ausgaenge. Die
    Installationsvorgabe ist jetzt fuer alle Universen `Disabled`; reale
    Ausgaenge werden bewusst unter E/A aktiviert.
14. Die 2D-Buehnenansicht zeichnet mit 10 statt 20 FPS. Das reduziert die
    QPainter-Last, ohne den getrennten DMX-/Playback-Takt zu veraendern.
15. Die Section-Button-Paddingbreite wurde touch-sicher reduziert (der
    56-px-Klick-Floor bleibt), sodass bei 1440 px alle Titel wieder voll lesbar
    sind.
16. Der Janitor-Unterpfadvergleich verwendet passend zum erkannten Pfadstil
    `/` oder `\\`.
17. Beim realen Fensterschliessen lief der daemonisierte `AudioCapture` noch im
    nativen PulseAudio-Mainloop. Nach dem bereits geloggten „sauberer Exit“
    folgte reproduzierbar ein `SIGSEGV`. Der Close-Pfad stoppt/joint Capture
    jetzt vor Qt/Python-Abbau und stoppt vorher den MIDI-Autoconnect-Timer.
18. `AA_ShareOpenGLContexts` wird vor `QApplication` gesetzt. Nach dem
    Eventloop werden alle `atexit`-Finalizer explizit ausgefuehrt und erst dann
    der unter QtWebEngine fehlerhafte globale Interpreter-Abbau uebersprungen.
19. Die eigentliche 3D-Crashursache wurde bis auf den globalen Python-
    `QApplication`-Eventfilter der VC-Tastatur-Hotkeys isoliert. Dieser Filter
    wurde durch einen fokusgebundenen Widget-Filter ersetzt; Chromium-interne
    `QWebEngineView`-/`RenderWidgetHost`-Widgets werden bewusst ausgeschlossen.
    Tastatur-Patching, Press/Release und Flash-Semantik bleiben erhalten.
20. Die Windows-Roaming-Daten wurden vom USB-Stick unveraendert nach
    `~/lightos-windows-data-backup-2026-07-23` kopiert und per Dateivergleich
    verifiziert. `bierpong.lshow` sowie VC-Assets, Stages und Snaps wurden in
    den lokalen LightOS-Datenordner installiert; die Linux-Fixture-Datenbank
    wurde dabei nicht ueberschrieben.
21. Der Onboard-Adapter Intel I219-V (`e1000e`, `eno1`) wurde als dauerhaftes
    NetworkManager-Profil `Internes Ethernet` eingerichtet. Wegen eines
    fehlerhaften Router-DHCP-Leases (angebotene Adresse bereits im LAN belegt)
    verwendet er konfliktgeprueft `192.168.178.250/24`, Gateway
    `192.168.178.1`, DNS `192.168.178.1` und `1.1.1.1`, EEE aus.
22. Fuer den ENTTEC DMX USB Pro wurde `maxi` dauerhaft der Gruppe `dialout`
    hinzugefuegt. Fuer die laufende Sitzung wurde zusaetzlich eine ACL auf
    `/dev/ttyUSB0` gesetzt.
23. Die lokale Fixture-Datenbank enthielt fuer mehrere in `bierpong.lshow`
    benoetigte Profile keine Modes und erzeugte dadurch falsche Fallback-Modi.
    Sie wurde als `fixtures.db.before-windows-import-2026-07-23` gesichert und
    durch die Datenbank der funktionierenden Windows-Installation ersetzt.
24. Alle 30 Fixtures von `bierpong.lshow` liegen auf Universe 1. Deshalb wurde
    Universe 1 auf den persistenten ENTTEC-Pfad
    `/dev/serial/by-id/usb-ENTTEC_DMX_USB_PRO_EN492875-if00-port0` gestellt.
    Alte Test-/Broadcast-Ausgaenge (`COM_FAKE`, Art-Net, sACN) sind deaktiviert.
25. Das interne Funkmodul wurde von Linux zunaechst ueberhaupt nicht enumeriert
    (`nmcli`: `WIFI-HW missing`; kein PCI-/USB-WLAN- oder Bluetooth-Geraet).
    Treiber (`iwlwifi`) und `linux-firmware` waren vorhanden. Die aus Linux
    auslesbaren Lenovo-UEFI-Werte zeigten `Wireless LAN: Disabled` und
    `Bluetooth: Disabled`; beide wurden ueber ThinkLMI/fwupd auf `Enabled`
    gestellt. Ein Neustart ist fuer die erneute Hardware-Enumeration notwendig.
26. Die VC-Arbeitsflaeche blieb wegen `QScrollArea.setWidgetResizable(False)`
    auf ihrer Mindestbreite von 1200 px stehen. Auf dem 1920-px-Touchscreen
    entstand dadurch rechts neben dem Raster eine grosse unbenutzbare schwarze
    Flaeche. Hauptansicht und Popout wachsen jetzt bis zur Viewportgroesse;
    unterhalb von 1200x800 bleiben sie weiterhin scrollbar. Show-Inhalt,
    Widgetpositionen und das 8-px-Snapraster bleiben unveraendert.

## Testprotokoll

| Pruefung | Ergebnis | Details |
|---|---|---|
| `pip check` | BESTANDEN | Keine defekten Python-Abhaengigkeiten |
| Full pytest, Ausgangslage | FEHLER | Collection-Abbruch durch `soundcard`/PulseAudio |
| Breiter isolierter Dateilauf | BESTANDEN | 471 Testdateien: 456 sofort gruen; 15 Befunddateien einzeln analysiert |
| Gebuendelter Fix-Regressionslauf | BESTANDEN | 57/57 in 119,09 s |
| UI-Audit | BESTANDEN | Janitor 18/18, Tab-Allokation 10/10, UI-Polish 12/12, MIDI-View 2/2 |
| Reale GUI-Start-/Exitpruefung | BESTANDEN | X11-Fenster 1400x900 erscheint; nach reproduziertem Exit-Fix endet derselbe Fensterschliessen-Ablauf mit Code 0 |
| Mehrfachstart | BESTANDEN | Zweiter `start.sh` beendet sich sauber mit „LightOS läuft bereits“ |
| MIDI ohne ALSA-Sequencer | BESTANDEN (Fallback) | GUI bleibt aktiv; Scan liefert leer und wird 10 s gedrosselt |
| Audio/BPM ohne Pulse/Device | BESTANDEN (Fallback) | Optionaler Import/Start degradiert ohne Collection-/App-Abbruch |
| Show-/Fixture-Portabilitaet | BESTANDEN | Demo-Profil Stage Light ZQ01424 von stale ID 17 auf lokale ID 23 remappt |
| 3D-WebEngine-Funktionen | BESTANDEN | Crash auf globalen VC-Hotkey-Eventfilter eingegrenzt und behoben; isolierte Reproduktion 12 s sowie komplette `bierpong.lshow` im Hauptfenster mit 3D 30 s stabil |
| `bierpong.lshow` statische Validierung | BESTANDEN | 0 Findings, 0 Fehler; lokale Kopie SHA-256-identisch zum USB-Original |
| `bierpong.lshow` Live-Validierung | BESTANDEN | 30 Fixtures geladen, 0 bindungsbewusste Findings/Fehler; alle auf Universe 1 |
| Onboard-Ethernet | BESTANDEN | `eno1`, 1 Gbit/s Full Duplex; Gateway und `1.1.1.1` je 3/3 Pings; HTTPS zu GitHub explizit ueber `eno1` erfolgreich |
| ENTTEC DMX USB Pro | BESTANDEN (Host/Protokoll) | Seriennummer EN492875, `ftdi_sio`; stabiler by-id-Pfad; Port geoeffnet, drei 512-Kanal-Blackout-Frames gesendet, sauber geschlossen |
| Bierpong-Outputkonfiguration | BESTANDEN | Universe 1 oeffnet realen ENTTEC; 0 Art-Net- und 0 sACN-Ausgaenge; Port beim Shutdown geschlossen |
| Internes WLAN/Bluetooth | NEUSTART AUSSTEHEND | ThinkCentre M720q: beide Funkoptionen im BIOS von `Disabled` auf `Enabled` gesetzt; Treiber/Firmware vorhanden, Hardware muss nach Neustart neu enumeriert und real verbunden werden |
| VC-Raster auf breitem Touchscreen | BESTANDEN | Screenshot-Befund behoben; Canvas fuellt breite Viewports, Popout identisch; 28 VC-/Touch-/Frame-Tests bestanden |
| Netzwerk-/Output-Subsysteme | BESTANDEN (Software) | Art-Net, sACN, OSC, Web-Remote, Laser und Output-Tests liefen isoliert mit normalem Socket-Zugriff gruen |
| Physische DMX-Ausgabe | TEILWEISE BESTANDEN | Reales ENTTEC erkannt und Protokollframes geschrieben; elektrisches DMX-Signal bzw. Reaktion einer angeschlossenen Lampe noch nicht gemessen |

### Testmethodik und bekannte Testgrenze

Die monolithische PySide-Suite ist auf PySide6 6.11 nicht verlaesslich:
Qt-Objekte aus hunderten Tests akkumulieren pro Prozess und QtWebEngine kann
beim wiederholten Erzeugen/Zerstoeren nativer Views im Chromium-Thread
segfaulten. Daher wurde jede der 471 Dateien in einem frischen Prozess
ausgefuehrt. So waren Anwendungsfehler von Testprozess-Kontamination trennbar.
Ein zusaetzlicher monolithischer Lauf am Ende erreichte ca. 63 %, bevor er
waehrend `gc.collect()` in `test_snapshot_teardown_gc.py` mit noch laufenden,
aus frueheren Tests stammenden MIDI-Threads nativ segfaultete. Dieselbe Datei
bestand direkt danach allein mit 2/2; die direkt betroffenen Hotkey-, 3D-,
ENTTEC-, Serial- und Show-Portabilitaetsdateien bestanden frisch mit 72/72.
Versuche mit PySide6 6.8.3 und 6.10.3 zeigten denselben WebEngine-Nativfehler;
die Umgebung wurde danach auf die deklarierte Version 6.11.1 zurueckgesetzt.

### Reale Laufzeitbeobachtung

- Der reale Start erzeugt genau eine Python-Instanz; wiederholter Start erzeugt
  keine konkurrierenden ALSA-/Qt-Prozesse mehr.
- Der vorhandene Auto-Save-Recovery-Dialog ist modal und befindet sich auf dem
  oberen Display. Das kann wie ein nicht gestartetes Hauptfenster wirken. Die
  Datei wurde nicht geloescht oder verworfen; die Entscheidung bleibt beim
  Benutzer.
- Der ALSA-Sequencer des Systems meldet aktuell `Cannot allocate memory` bzw.
  `can't open sequencer`. LightOS faengt dies ab; echte MIDI-Ein-/Ausgabe ist
  erst nach Behebung des System-/Treiberzustands messbar.
- Auch nach Halbierung des 2D-Preview-Takts liegt die Gesamtlast der sichtbaren
  Buehnenansicht auf diesem Rechner bei etwa 60 % eines CPU-Kerns. Der Prozess
  blieb dabei responsiv und speicherstabil (ca. 309 MiB RSS); weitere
  Renderoptimierung ist Performance-Arbeit, kein in diesem Lauf beobachteter
  Absturz.
- Der 3D-Absturz war kein Renderer- oder GPU-Fehler. Eine einzelne
  `QWebEngineView` und das komplette Visualizer-Fenster waren jeweils stabil;
  erst die Kombination mit der Virtual Console stuerzte ab. Komponentenweise
  Tests schlossen GIFs, MIDI, Engine-Anbindung und alle anderen MainWindow-
  Views aus. Ausschliesslich der app-weite Python-Eventfilter fuer VC-Hotkeys
  reproduzierte Exit 139. Der fokusgebundene Ersatz besteht sowohl den
  isolierten Reproduktionstest als auch den realen Bierpong-Show-Lauf.

## Hardwaregrenzen

- Der ENTTEC-Hostpfad ist bestaetigt. Ohne angeschlossene DMX-Leuchte bzw.
  Messgeraet kann das elektrische Signal hinter dem Adapter nicht bestaetigt
  werden.
- Ohne funktionierenden ALSA-Sequencer und MIDI-Geraet kann der robuste
  Fehlerpfad, nicht ein reales MIDI-Signal bestaetigt werden.
- Touch-Zuordnung ist systemseitig getauscht: USB 1-5 -> HDMI-2 und USB 1-6 ->
  HDMI-1. Diese Zuordnung ist ausserhalb des LightOS-Codes.
