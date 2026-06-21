# Drahtlose Remote-Konsole (Handy als virtuelle Konsole) — Konzept & Optionen

> Status: **Nur Planung / Ideensammlung.** Noch nichts umgesetzt.
> Erstellt: 2026-06-15
> Ziel: Auf einem Handy/Tablet im selben WLAN eine schlanke, touch-optimierte
> zweite virtuelle Konsole anzeigen (BPM-Tap, Strobe, Blackout, Master, Executor-Pads),
> ohne eine native iOS-App programmieren zu müssen.

---

## 1. Kernaussage zuerst

**Der mit Abstand sinnvollste Weg ist der, den du fast schon fertig hast:** eine
**selbst-gehostete Web-Seite über WLAN**. LightOS bringt bereits einen
Flask-+-WebSocket-Server mit, der auf `0.0.0.0:5000` lauscht — d. h. **jedes Gerät
im selben WLAN kann die Konsole heute schon im Browser öffnen**. Es fehlt im Kern
nur eine *touch-optimierte Seite* mit BPM/Strobe, ein bequemer Verbindungsweg
(fester Name statt IP) und ein kleiner WLAN-Router für unterwegs.

Telegram-Bot und „fremde App kapern" sind **nicht** der Hauptweg (Begründung unten),
aber es gibt einen eleganten *Profi-Zusatz*: fertige **OSC-Apps** (TouchOSC /
Open Stage Control) — auch dafür ist der Server schon da.

---

## 2. Ausgangslage — was in LightOS bereits existiert

Wichtig, damit wir nicht doppelt bauen. Verifiziert im Code:

| Baustein | Datei | Was es kann |
|---|---|---|
| **Web-Server (Flask + SocketIO)** | `src/web/app.py` | Lauscht auf `0.0.0.0:5000`, REST-API **+** Live-WebSocket. Endpunkte: `go`/`back`/`blackout`/`fader`/`channel`/`programmer/clear`/`executor/<n>/go`. |
| **Mobile-Web-Template** | `src/web/templates/index.html` | Schon dunkles Touch-Layout mit `viewport`-Meta + `@media`-Breakpoint, GO/BACK/STOP/Blackout + 10 Executor-Fader. |
| **Menü-Schalter** | `src/ui/main_window.py` | „Web-Interface (Port 5000)" und „OSC-Server (Port 7770)" als an/aus-Schalter im Menü. |
| **OSC-Server** | `src/core/osc/osc_server.py` | UDP :7770, Adress-Schema **kompatibel zu TouchOSC/Lemur** (`/lightos/go`, `/lightos/exec/{n}/fader` …) + `OscSender` für Rück-Feedback. |
| **OS2L-Server** | `src/core/audio/os2l.py` | TCP :1234, **VirtualDJ / Mixxx**-Integration (Beat- & Cmd-Events → BPM-Manager / Cues). |
| **BPM-Manager** | `src/core/engine/bpm_manager.py` | Globales Tap-Tempo (`tap()`), `set_bpm()`, Audio-Quelle, Beat-Broadcast an Subscriber. |
| **Netzwerk-DMX** | `src/core/dmx/artnet*.py`, `sacn*.py` | Art-Net & sACN In/Out (für ganz andere Szenarien relevant, s. u.). |
| **Abhängigkeiten** | `requirements.txt` | `Flask`, `flask-socketio`, `python-osc` sind **bereits deklariert**. |

**Fazit:** Die ganze Server-Infrastruktur steht. Es ist kein „bei null anfangen",
sondern „die vorhandene Web-Seite aufbohren + sauber zugänglich machen".

---

## 3. Die Optionen im Vergleich

### Option A — Selbst-gehostete Web-Seite über WLAN  ⭐ EMPFOHLEN
PC hostet die Seite (läuft schon), Handy öffnet `http://<PC>:5000` im Browser.

- ✅ **Keine App-Programmierung**, kein App Store, läuft auf iOS-Safari **und** Android.
- ✅ Volle Gestaltungsfreiheit — BPM, Strobe, Farben, Pads, *genau wie du willst*.
- ✅ Echtzeit über WebSocket (Latenz im WLAN typ. < 20–50 ms), bidirektional (Feedback aufs Handy möglich).
- ✅ Funktioniert **komplett offline** (kein Internet nötig), nur lokales WLAN.
- ✅ Server + Grundseite **existieren bereits**.
- ⚠️ Du musst die Seite einmal touch-optimieren (Backlog §6).
- ⚠️ Verbindung/Sicherheit sauber machen (fester Name, optional PIN — §7/§8).

### Option B — Fertige OSC-App (TouchOSC / Open Stage Control)  ✅ als Profi-Zusatz
Statt eigener App eine generische OSC-Controller-App nehmen und auf den **schon
vorhandenen** OSC-Server zeigen lassen.

- ✅ **Kein** App-Eigenbau; professionelle, haptische Touch-Layouts (Fader/XY/Pads).
- ✅ `TouchOSC` (Hexler, iOS/Android, ~6 €) ist schon adress-kompatibel zu unserem Server.
- ✅ `Open Stage Control` ist **gratis** und läuft selbst nur im Browser — kombinierbar mit Option A.
- ⚠️ Layout-Bau in der Fremd-App; Look folgt deren Design, nicht LightOS.
- ⚠️ OSC ist „nur senden" — Rück-Feedback (LED-Status) muss man extra über `OscSender` einrichten.
- → **Rolle:** Bonus für alle, die echte Hardware-Fader-Optik wollen. Nicht der Hauptweg, aber „fast geschenkt".

### Option C — Telegram-Bot  ❌ nicht als Live-Konsole
- ❌ Braucht **Internet** (Telegram-Cloud) — fällt im reinen Offline-WLAN aus.
- ❌ Latenz 300 ms bis mehrere Sekunden, Rate-Limits → für „Blackout JETZT" / Strobe untauglich.
- ❌ Keine durchgehenden Regler (Fader/XY), kein flüssiges Echtzeit-Feedback.
- ✅ Einzig sinnvoll als **Benachrichtigung** („Show gestartet", „Crash") oder simpler Not-Befehl aus der Ferne — *nicht* als Bühnen-Bedienoberfläche.

### Option D — Fremde App „kapern" (QLC+-/andere Lichtsoftware-App)  ❌ mehr Arbeit, nicht weniger
- QLC+ hat **keine** native App, sondern ein eigenes **HTML5-Web-Interface** — das steuert QLC+, nicht LightOS. „Kapern" hieße, dass LightOS exakt die QLC+-API nachbaut → mehr Aufwand als die eigene Seite zu verbessern.
- Der *einzige* übertragbare Teil ist der **offene Standard OSC** — und den deckt Option B sauber ab. Eine konkrete App nachzuäffen lohnt nicht.

### (Option E — Art-Net/sACN-App)  ℹ️ falscher Use-Case
Apps wie „Luminair" sprechen Art-Net/sACN — aber das sind **DMX-Endgeräte**, sie würden
am Pult vorbei direkt an die Lampen senden, nicht *LightOS fernsteuern*. Für deinen
Wunsch (zweite Konsole **für** LightOS) ist das das falsche Werkzeug. Nur erwähnt zur Vollständigkeit.

---

## 4. Empfehlung (Architektur)

**Zweischichtig, beide nutzen vorhandene Server:**

```
            ┌─────────────────────────── WLAN (privat, WPA2) ───────────────────────────┐
            │                                                                            │
  [ Handy/Tablet ]  ──HTTP/WebSocket──►  :5000  Flask-Web-Konsole   ⭐ HAUPTWEG          │
   (Browser)        ──OSC/UDP (optional)─►  :7770 OSC-Server       (TouchOSC/OSC-App)   │
            │                                                                            │
            │                          [ PC mit LightOS ]                               │
            └────────────────────────────────────────────────────────────────────────────┘
                                    (kein Internet nötig)
```

1. **Primär:** die eigene Web-Konsole (Option A) als touch-optimierte zweite Seite
   `/live` — maßgeschneidert für BPM-Tap, Strobe, Master, Blackout, Executor-Pads, Farb-Schnelltasten.
2. **Optional/Profi:** OSC (Option B) für alle, die TouchOSC-Layouts mit echten Fadern wollen — *schon unterstützt*, nur dokumentieren + ein fertiges Template beilegen.
3. **DJ-Anbindung** ist über **OS2L** bereits abgedeckt (VirtualDJ/Mixxx → Beat/BPM). Das ist genau die „virtuelle DJ-Software"-Brücke, nach der du gefragt hast — sie muss nur eingeschaltet & dokumentiert werden.
4. **Telegram** höchstens als *Benachrichtigungs*-Kanal, nicht als Konsole.

---

## 5. Hardware — Router & WLAN

Du brauchst ein eigenes, von Internet/Hausnetz unabhängiges WLAN, in dem PC und Handy
zuverlässig dieselben Adressen behalten.

**Empfohlen: kleiner Reise-/Mini-Router** (z. B. GL.iNet „Mini"-Serie, ~25–40 €):
- ✅ Eigenes, privates WLAN nur für die Show → stabil, kein fremder Traffic, keine Hotel-/Hausnetz-Sperren.
- ✅ PC per LAN-Kabel an den Router (latenz- & störungsärmer als WLAN am PC), Handy per WLAN.
- ✅ Internet nicht erforderlich; bei Bedarf trotzdem über WAN nachrüstbar.
- ✅ Feste IP/DHCP-Reservierung für den PC einrichtbar → Adresse ändert sich nie.

**Alternative ohne Extra-Hardware: Windows „Mobiler Hotspot"** (PC spannt selbst ein WLAN auf):
- ✅ Null Zusatzkosten, sofort testbar.
- ⚠️ Reichweite/Stabilität schlechter als echter Router; WLAN-Adapter muss es können; teilt sich die Karte mit anderem WLAN.
- → Gut zum **Ausprobieren**, für den Live-Einsatz lieber der Mini-Router.

**Komfort-Tipp gegen das „welche IP?"-Problem:**
- mDNS/Zeroconf (`http://lightos.local:5000`) oder eine feste IP per DHCP-Reservierung,
  damit das Handy das Pult immer unter demselben Namen findet (Detail → Backlog §6).

---

## 6. Backlog — was zu bauen wäre (NICHT jetzt, nur Liste)

Sortiert nach Wirkung/Aufwand. Reihenfolge ist auch eine sinnvolle Umsetz-Reihenfolge.

**A. Touch-Konsole `/live` (Kern, rein Frontend + ein paar Endpunkte)**
1. Neue Route/Seite `/live` (oder `index.html` aufbohren): große Kacheln statt Maus-Layout.
2. **BPM-Sektion:** großer Tap-Button (→ `bpm_manager.tap()`), BPM-Anzeige, +/- & Direkteingabe (→ `set_bpm()`), „Audio-Sync an/aus".
3. **Strobe:** momentan (Halten) **und** Latch (Umschalten) + Rate-Regler. *Hinweis:* exakte Strobe-API im Engine vor der Umsetzung verifizieren (Strobe taucht in `universe.py`, `programmer_view.py`, `simple_desk.py` auf — sauberen Einstiegspunkt festlegen).
4. **Master-Dimmer** + **Blackout** (Blackout-Endpunkt existiert schon).
5. **Executor-/Cue-Pads** als großes Raster (Endpunkte existieren), mit Aktiv-Status-Feedback per WebSocket.
6. **Farb-Schnelltasten** (rot/blau/…/Weiß) für schnellen Stimmungswechsel.

**B. Neue/erweiterte Server-Endpunkte in `src/web/app.py`**
7. `POST /api/bpm/tap`, `POST /api/bpm` (set), `POST /api/strobe`, `POST /api/master` + passende SocketIO-Events.
8. Status-Push: BPM, Beat-Blink, aktive Executor → per WebSocket ans Handy (Feedback).

**C. Komfort & Auffindbarkeit**
9. mDNS-Hostname (`lightos.local`) **oder** Doku zur DHCP-Reservierung.
10. **QR-Code im Desktop-Fenster**, der die aktuelle URL (`http://<ip>:5000/live`) zeigt → Handy scannt, fertig. (IP automatisch ermitteln.)
11. Beim Einschalten des Web-Servers die erreichbare Adresse in der Statusleiste/Log anzeigen.

**D. OSC-Profi-Schiene (Option B)**
12. Fertiges **TouchOSC**-Layout **und/oder** **Open-Stage-Control**-Session beilegen (`docs/` oder `tools/`), das auf `:7770` zeigt — als „Plug-and-Play"-Vorlage.
13. OSC-Feedback (`OscSender`) für LED-/Status-Rückmeldung dokumentieren/aktivieren.

**E. Sicherheit (siehe §7)**
14. Optionaler **PIN/Token** + Bindung an das WLAN-Interface; `cors_allowed_origins` einschränken.

---

## 7. Sicherheit (kurz, aber wichtig)

Aktuell: `cors_allowed_origins="*"`, **keine Authentifizierung**, Bindung an `0.0.0.0`
(= alle Netzwerk-Interfaces). In einem **privaten, WPA2-geschützten Show-WLAN** ist das
praktisch unkritisch — wer im WLAN ist, ist eingeladen. Für mehr Robustheit:

- Einfaches **PIN/Token** vor den Steuer-Endpunkten (verhindert „Spaßvögel" im selben Netz).
- `cors_allowed_origins` auf den eigenen Origin einschränken.
- Optional Server nur an die **WLAN-IP** binden statt `0.0.0.0`.
- Niemals dieses WLAN offen (ohne Passwort) und gleichzeitig mit dem Internet/Hausnetz verbinden, solange ohne PIN.

Das ist **kein Blocker** für einen ersten Test — aber sollte vor „echtem" Live-Einsatz mit Fremden im Netz passieren.

---

## 8. Sofort-Test HEUTE — ganz ohne neuen Code

Damit du das Prinzip in 5 Minuten siehst (nutzt die *bestehende* `index.html`):

1. PC und Handy ins **gleiche WLAN** (Hausnetz reicht zum Testen; für Show später Mini-Router).
2. In LightOS: Menü → **„Web-Interface (Port 5000)"** einschalten.
3. PC-IP herausfinden: PowerShell → `ipconfig` → „IPv4-Adresse" des WLAN-Adapters (z. B. `192.168.0.42`).
4. Am Handy im Browser öffnen: `http://192.168.0.42:5000`
5. Du solltest GO/BACK/STOP, Blackout und die Executor-Fader sehen — und live steuern können.
6. (Optional) Windows-Firewall fragt evtl. beim ersten Start nach Freigabe für Port 5000 → erlauben (privates Netz).

Wenn das läuft, ist der Rest „nur" das schönere `/live`-Layout aus §6 — und der Mini-Router für ein eigenes, internetunabhängiges Show-WLAN.

---

## 9. Offene Entscheidungen (für dich)

- **Router:** eigener Mini-Reise-Router (empfohlen) **oder** erst mal Windows-Hotspot zum Testen?
- **Profi-Schiene:** zusätzlich OSC/TouchOSC anbieten — ja/nein? (Wenig Aufwand, schon unterstützt.)
- **Sicherheit:** PIN-Schutz von Anfang an, oder bewusst „offen im privaten WLAN"?
- **Auffindbarkeit:** mDNS-Name `lightos.local` einbauen, oder QR-Code reicht?
- Soll dieser Punkt in `docs/OPEN_POINTS_OVERVIEW.md` als offizielle Aufgabe aufgenommen werden?

---

## 10. Empfohlene nächste Schritte (wenn du loslegen willst)

1. **Sofort-Test (§8)** machen → bestätigt, dass der Weg trägt.
2. Mini-Router besorgen (~30 €), PC per LAN dran, DHCP-Reservierung für den PC.
3. `/live`-Seite bauen (Backlog A) + die paar Endpunkte (Backlog B).
4. QR-Code + Adressanzeige im Desktop (Backlog C) für komfortables Verbinden.
5. Optional: TouchOSC-/Open-Stage-Control-Vorlage beilegen (Backlog D).
6. Vor Live mit Fremden im Netz: PIN/CORS (Backlog E / §7).
