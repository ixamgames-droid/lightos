# Web-Remote — das Handy als Konsole

> Mit dem eingebauten **Web-Interface** steuerst du LightOS vom Smartphone oder
> Tablet: GO/BACK/STOP für die Cueliste, ein großer **Blackout**-Schalter und
> fünf **Executor-Fader** — alles über den Browser, ohne App-Installation.
> Voraussetzung: Handy und PC hängen im **selben WLAN/LAN**.

---

## 1. Server starten

Der Web-Server ist standardmäßig aus. Einschalten im Menü **Ausgabe →
„Web-Interface (Port 5000)"** (Häkchen setzen). LightOS startet dann einen
kleinen Hintergrund-Server auf **Port 5000** und meldet den Erfolg mit einer
Info-Box; in der Statusleiste erscheint **„Web: :5000 OK"** (grün).

Ein paar Fakten zum Server (aus `src/web/app.py`):

- **Port:** `5000` (fest; `start_server(5000)` wird beim Einschalten aufgerufen).
- **Bind-Adresse:** `0.0.0.0` — der Server lauscht bewusst auf **allen**
  Netzwerk-Schnittstellen, damit ihn andere Geräte im LAN erreichen. Genau
  deshalb gilt der Sicherheitshinweis in Abschnitt 4.
- **Secret-Key:** Der Flask-`SECRET_KEY` wird **nicht** hart im Code hinterlegt.
  Ist die Umgebungsvariable `LIGHTOS_FLASK_SECRET` gesetzt, wird sie verwendet;
  sonst erzeugt LightOS bei jedem Start einen zufälligen Key. Für den normalen
  LAN-Betrieb musst du hier **nichts** tun. Wenn du einen stabilen Key willst
  (z. B. für Tests), setze ihn vor dem Start, etwa in der PowerShell:

  ```powershell
  $env:LIGHTOS_FLASK_SECRET = "mein-geheimer-key"
  ```

Zum Ausschalten das Häkchen im selben Menüpunkt wieder entfernen — die
Statusleiste zeigt dann **„Web: aus"**.

---

## 2. LAN-IP finden und am Handy öffnen

Auf dem PC selbst erreichst du das Remote unter **`http://localhost:5000`** —
das zeigt auch die Info-Box beim Einschalten an. Fürs **Handy** brauchst du aber
die **LAN-IP-Adresse deines PCs**, denn `localhost` zeigt beim Handy auf das
Handy selbst.

**LAN-IP herausfinden (Windows):** PowerShell öffnen und eingeben:

```powershell
ipconfig
```

Suche unter deinem aktiven WLAN-/Ethernet-Adapter die Zeile **„IPv4-Adresse"** —
typisch etwas wie `192.168.x.y` oder `10.0.x.y`. Kurzform, die nur die WLAN-IP
ausgibt:

```powershell
(Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.IPAddress -like '192.168.*' -or $_.IPAddress -like '10.*' }).IPAddress
```

**Am Handy öffnen:** Handy ins **gleiche WLAN** bringen, den Browser öffnen und

```
http://<PC-IP>:5000/?k=<token>
```

eingeben — z. B. `http://192.168.1.42:5000/?k=ab12cd`. Das **Token** (`?k=…`) ist nötig,
seit das Remote per Token abgesichert ist (siehe Abschnitt 4). Den genauen Wert **und einen
fertigen Direkt-Link** zeigt LightOS im **Verbindungs-Dialog** beim Einschalten — am
einfachsten dort kopieren. Ohne gültiges Token antwortet der Server mit **403**. Nach dem
ersten Öffnen merkt sich das Handy die Anmeldung (Cookie); es erscheint die Seite
**„⚡ LightOS Remote"**. Tipp: Als Lesezeichen/Startbildschirm-Verknüpfung speichern.

> **Hinweis:** Nutze für das Handy immer die per `ipconfig` ermittelte **LAN-IP** (nicht
> `localhost` — das zeigt beim Handy auf das Handy selbst). Firewall-Abfrage beim ersten
> Start mit **„Zugriff erlauben"** (privates Netz) bestätigen, sonst ist Port 5000 von
> außen dicht.

---

## 3. Was die Bedien-Elemente tun

Die Remote-Seite hat drei Blöcke: **Transport**, **Blackout** und
**Executor-Fader**. Jede Aktion läuft direkt auf die laufende Show (die Befehle
sind in `src/web/app.py` als Routen/SocketIO-Handler umgesetzt):

| Element | Wirkung | Route / Handler in `app.py` |
|---|---|---|
| **GO ▶** | nächster Cue der ersten Cueliste (`cue_stacks[0].go()`) | `POST /api/go` · SocketIO `go` |
| **◀◀ BACK** | einen Cue zurück (`cue_stacks[0].back()`) | `POST /api/back` · SocketIO `back` |
| **■ STOP** | laufende Cueliste anhalten (`cue_stacks[0].stop()`) | `POST /api/stop` · SocketIO `stop` |
| **Blackout** | schaltet die gesamte Ausgabe dunkel und wieder hell (Toggle) | `POST /api/blackout` · SocketIO `blackout` |
| **Fader 1–5** | setzen den Pegel der **Executor-Fader** (Slots 1–5, 0–100 %) | `POST /api/executor/<slot>/fader` · SocketIO `fader` |

Weitere Details:

- **GO/BACK/STOP** wirken auf die **erste Cueliste** der Show. Gibt es keine
  Cueliste, passiert nichts (kein Fehler).
- **Blackout** ist ein Umschalter: erneutes Tippen hebt den Blackout wieder auf.
  Der Button färbt sich, solange Blackout aktiv ist.
- **Executor-Fader** entsprechen den Playback-Executoren 1–10 in LightOS; die
  Remote zeigt fünf davon. Beim Öffnen liest die Seite über `GET /api/status`
  den **echten** aktuellen Fader-Stand aus und stellt die Regler passend ein
  (nicht pauschal auf 100 %).
- Neben diesen Buttons kennt der Server noch **weitere** Routen, die das
  Standard-UI nicht anzeigt (z. B. `POST /api/executor/<slot>/go`,
  `POST /api/channel/<universe>/<channel>`, `POST /api/programmer/clear`).
  Kaputte oder leere Payloads werden abgefangen und lösen keinen Server-Fehler
  aus (WEB-02/03).

---

## 4. Sicherheit — Token-Auth, CORS-Allowlist, LAN-Bind

Seit 2026-07 ist das Web-Remote **per Default abgesichert** (Design-Entscheidung
[DESIGN_DECISION_REMOTE_SECURITY_2026-07-14.md](../DESIGN_DECISION_REMOTE_SECURITY_2026-07-14.md)):

- **Token-Auth (NET-01).** Der Zugriff ist durch ein **pro Setup gespeichertes Token**
  geschützt (kurz & tippbar, als `?k=<token>` in der URL). Ein `@before_request`-Gate lässt
  nur authentisierte Sessions durch — jede API-Route ohne gültige Session antwortet mit
  **403**; auch SocketIO lehnt unauthentisierte Verbindungen ab. Nach dem Handshake merkt ein
  `HttpOnly`/`SameSite=Strict`-Cookie die Anmeldung. Das Token zeigt der Verbindungs-Dialog;
  „Token neu erzeugen" macht alte Links ungültig.
- **CORS-Allowlist (NET-03).** Statt `cors_allowed_origins="*"` erlaubt der SocketIO-Endpunkt
  nur noch die bekannten Origins (`http://<lan-ip>:5000`, `127.0.0.1`, `localhost`) — eine
  fremde Webseite im selben Netz kann sich nicht mehr einfach drauf verbinden.
- **LAN-Bind steuerbar.** Der Toggle **„LAN-/Handy-Remote"** (Default AN, sicher weil Token
  davor) bindet `0.0.0.0` (das Handy erreicht es); AUS bindet `127.0.0.1` (nur der PC selbst).

**Trotzdem Rest-Risiko im Blick behalten:**

- Das Token ist ein **geteiltes** Setup-Geheimnis (keine Einzel-Benutzer/PIN). Wer den
  Direkt-Link kennt, kann steuern → Link/Token nicht im Publikum herumzeigen; bei Verdacht
  **„Token neu erzeugen"**.
- Weiterhin sinnvoll: ein **vertrauenswürdiges** Netz (eigenes Technik-WLAN), das Interface
  nach Gebrauch ausschalten, und Port 5000 **nicht** ins Internet weiterleiten.

> **Offene Follow-ups:** QR-Bild des Direkt-Links, OSC-Source-Allowlist und Token-Rotation pro
> Start sind bewusst noch offen (siehe Design-Doc). Der OSC-Eingang ist separat nur über den
> Loopback-/„OSC über Netzwerk"-Toggle (Default AUS) abgesichert.

---

## Kurz-Referenz

1. **Ausgabe → „Web-Interface (Port 5000)"** anhaken → Server läuft auf `0.0.0.0:5000`.
2. PC-LAN-IP per `ipconfig` holen → am Handy `http://<PC-IP>:5000/?k=<token>` öffnen (Token/Direkt-Link aus dem Verbindungs-Dialog, gleiches WLAN).
3. **GO/BACK/STOP** = Cueliste · **Blackout** = alles dunkel (Toggle) · **Fader 1–5** = Executor-Pegel.
4. **Token-geschützt** (`?k=…`, ohne → 403) + CORS-Allowlist; Token ist ein **geteiltes** Setup-Geheimnis → nur im vertrauenswürdigen Netz nutzen, danach ausschalten.

Zurück zur Übersicht: [../ANLEITUNGEN.md](../ANLEITUNGEN.md)
