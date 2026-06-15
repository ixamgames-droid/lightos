# LightOS — Smoke-Test-Checkliste

> Vor jedem Release oder nach größeren Änderungen durchführen.
> Jeder Bereich kann unabhängig getestet werden.

---

## 1. Audio / BPM-Detection

**Voraussetzung:** Soundcard / WASAPI-Gerät verfügbar, Musik abspielbar.

- [ ] Ansicht „Audio Input" öffnen (`Ansicht → Audio Input`)
- [ ] Eingabegerät aus Dropdown wählen und „Start" klicken
- [ ] Pegel-Anzeige reagiert auf Musiksignal (Balken bewegt sich)
- [ ] BPM-Anzeige aktualisiert sich bei konstantem Beat (±5 BPM Toleranz)
- [ ] „Tap BPM"-Button setzt erkannten Wert korrekt
- [ ] Stopp-Button beendet Capture ohne Exception im Log
- [ ] Beat-Sync auf Chaser wirkt sich auf Abspielrate aus (Chaser läuft mit BPM)

**Erwartetes Ergebnis:** Kein Absturz, BPM-Anzeige stabil innerhalb 2 Sekunden nach Musikstart.

---

## 2. MIDI

**Voraussetzung:** Mindestens ein MIDI-Interface oder -Controller angeschlossen (z.B. APC Mini).

### 2a. MIDI-Eingang (Mapping)
- [ ] `Ansicht → Input-Profile` öffnen
- [ ] MIDI-Port in der Liste sichtbar
- [ ] Note On / CC-Nachrichten erscheinen im MIDI-Monitor
- [ ] MIDI Learn auf einem VC-Button: Button drücken, Controller-Taste drücken → Binding gesetzt
- [ ] Binding auslösen: Controller-Taste → Button reagiert in der UI

### 2b. APC Mini LED-Feedback
- [ ] „APC LEDs"-Toggle in der Virtual Console aktivieren
- [ ] Executor starten → entsprechende APC-LED leuchtet grün
- [ ] Executor stoppen → LED schaltet auf grün blinkend
- [ ] Flash-Modus → LED leuchtet rot
- [ ] Page-Wechsel → aktuelle Page-LED gelb

### 2c. MIDI-Ausgabe
- [ ] MIDI-Mapping auf VC-Button mit „Send Note"-Aktion konfigurieren
- [ ] Button klicken → Extern (z.B. DAW MIDI-Monitor) empfängt Note On

**Erwartetes Ergebnis:** Kein Freeze des UI-Threads, alle Bindings reagieren in <50 ms.

---

## 3. OSC

**Voraussetzung:** OSC-Client (z.B. TouchOSC, oscstatus, oder Python-Script).

### 3a. OSC-Empfang (LightOS als Server)
- [ ] OSC-Server in Einstellungen aktivieren (Standard-Port: 7700)
- [ ] Von Client senden: `/lightos/executor/1/go` → Executor 1 startet
- [ ] Von Client senden: `/lightos/executor/1/fader 0.75` → Fader auf 75%
- [ ] Von Client senden: `/lightos/master 0.5` → Grand-Master auf 50%
- [ ] Ungültige Adresse wird ignoriert (kein Absturz)

### 3b. OSC-Senden (LightOS als Client)
- [ ] OSC-Ausgabe aktivieren und Ziel-IP/Port konfigurieren
- [ ] Executor-Statuswechsel → OSC-Feedback-Paket empfangen

**Erwartetes Ergebnis:** Latenz <10 ms im LAN, kein Paketverlust bei <100 Paketen/s.

---

## 4. Web-Remote

**Voraussetzung:** LightOS läuft, Browser (Chrome/Edge) auf gleichem oder anderem Gerät im LAN.

- [ ] Flask-Server startet beim App-Start (Log: „Running on http://0.0.0.0:5000")
- [ ] `http://<PC-IP>:5000` im Browser öffnen → Startseite lädt ohne 404
- [ ] Executor-Grid sichtbar: alle aktiven Executors mit Label angezeigt
- [ ] GO-Button im Browser klicken → Cueliste startet in LightOS
- [ ] Fader im Browser ziehen → Fader-Wert in LightOS aktualisiert sich live (SocketIO)
- [ ] LightOS-seitige Änderung (GO über UI) → Browser-State aktualisiert sich ohne Reload
- [ ] Verbindung trennen (Browser schließen) → kein Absturz in LightOS
- [ ] Mehrere Browser-Tabs gleichzeitig → alle erhalten Updates

**Erwartetes Ergebnis:** Ladezeit <2 s, Live-Updates <200 ms Latenz im WLAN.

---

## 5. DMX-Ausgabe (Basis-Smoke-Test)

- [ ] Enttec Pro / Open DMX: COM-Port wählen, Universe 1 zuweisen
- [ ] Fixture patchen (FID 1, Adresse 1, 3-Kanal RGB)
- [ ] Programmer: FID 1 auswählen, Rot 255 setzen
- [ ] DMX-Monitor zeigt Kanal 1–3 = 255, 0, 0
- [ ] Physisches Gerät leuchtet rot (falls angeschlossen)
- [ ] Art-Net: Paket-Counter steigt in Netzwerkanalyse (Wireshark / Art-Net-View)

---

## Fehler melden

Wenn ein Schritt fehlschlägt: [Bug-Report öffnen](../.github/ISSUE_TEMPLATE/bug_report.md) und Schritt + Fehlermeldung aus dem Log (`logs/lightos.log`) beifügen.
