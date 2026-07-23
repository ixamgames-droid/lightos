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
| 3D-WebEngine-Funktionen | BLOCKIERT | Echter X11-Nutzerpfad segfaultet auf diesem System ca. 9 s nach dem Oeffnen auch mit PySide 6.8/6.10/6.11 sowie Hardware-/Software-Rendering |
| Netzwerk-/Output-Subsysteme | BESTANDEN (Software) | Art-Net, sACN, OSC, Web-Remote, Laser und Output-Tests liefen isoliert mit normalem Socket-Zugriff gruen |
| Physische Hardwareausgabe | NICHT MESSBAR | Kein reales DMX-, Laser-, Audio- oder MIDI-Testgeraet fuer Signal-End-to-End vorhanden |

### Testmethodik und bekannte Testgrenze

Die monolithische PySide-Suite ist auf PySide6 6.11 nicht verlaesslich:
Qt-Objekte aus hunderten Tests akkumulieren pro Prozess und QtWebEngine kann
beim wiederholten Erzeugen/Zerstoeren nativer Views im Chromium-Thread
segfaulten. Daher wurde jede der 471 Dateien in einem frischen Prozess
ausgefuehrt. So waren Anwendungsfehler von Testprozess-Kontamination trennbar.
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
- Der separate 3D-Visualizer ist auf diesem konkreten Grafik-/Qt-System noch
  nicht betriebssicher. Der Coredump endet im GUI-Hauptthread in
  `libpyside6.abi3.so`; Qt 6.8/6.10/6.11, Software-Rendering, deaktivierte GPU
  und korrekt gesetztes OpenGL-Context-Sharing aendern den Befund nicht. Dieser
  Punkt verhindert bewusst die Aussage „alle Features funktionieren“.

## Hardwaregrenzen

- Ohne angeschlossene DMX-/Laser-Hardware kann nur die komplette
  Software-Pipeline, nicht das elektrische/optische Ausgangssignal bestaetigt
  werden.
- Ohne funktionierenden ALSA-Sequencer und MIDI-Geraet kann der robuste
  Fehlerpfad, nicht ein reales MIDI-Signal bestaetigt werden.
- Touch-Zuordnung ist systemseitig getauscht: USB 1-5 -> HDMI-2 und USB 1-6 ->
  HDMI-1. Diese Zuordnung ist ausserhalb des LightOS-Codes.
