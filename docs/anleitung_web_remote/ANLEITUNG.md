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
http://<PC-IP>:5000
```

eingeben — z. B. `http://192.168.1.42:5000`. Es erscheint die Seite
**„⚡ LightOS Remote"**. Tipp: Als Lesezeichen/Startbildschirm-Verknüpfung
speichern, dann ist die Remote beim nächsten Mal ein Fingertipp entfernt.

> **Hinweis:** Die Info-Box in LightOS nennt derzeit nur `localhost:5000`, nicht
> die echte LAN-IP (siehe Backlog `NET-02`). Nutze für das Handy immer die per
> `ipconfig` ermittelte Adresse. Firewall-Abfrage beim ersten Start mit
> **„Zugriff erlauben"** (privates Netz) bestätigen, sonst ist Port 5000 von
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

## 4. Sicherheitshinweis — offenes LAN, keine Authentifizierung

Wichtig zu wissen, bevor du das Remote in einem fremden Netz (Club-WLAN,
Gäste-WLAN, offener Hotspot) nutzt:

- **Keine Anmeldung.** Es gibt **kein** Passwort, keinen PIN und kein Token.
  Der Server bindet auf `0.0.0.0:5000` — **jedes** Gerät im selben WLAN/LAN kann
  die Seite `http://<PC-IP>:5000` öffnen und damit **GO/BACK/STOP, Blackout und
  die Fader** auslösen (Backlog `NET-01`).
- **Offene SocketIO-Origins.** Der SocketIO-Endpunkt erlaubt derzeit beliebige
  Ursprünge (`cors_allowed_origins="*"`), es gibt keinen CSRF-/Origin-Schutz
  (Backlog `NET-03`). Eine beliebige Webseite im selben Netz könnte sich
  theoretisch verbinden.

**Empfehlung für den Live-Betrieb:**

- Nur in einem **vertrauenswürdigen, kontrollierten Netz** verwenden — am besten
  ein **eigenes WLAN** nur für die Technik, kein Gäste-/Publikums-WLAN.
- Das Web-Interface **nur einschalten, solange du es brauchst**, und danach im
  Menü wieder ausschalten.
- Den PC **nicht** direkt ins Internet hängen bzw. Port 5000 **nicht** im Router
  weiterleiten.

> Auth/PIN und eine LAN-Freigabe als bewusste Option sind als Verbesserung
> vorgemerkt (`NET-01`/`NET-03`). Bis dahin gilt: LightOS-Web-Remote ist ein
> **lokaler LAN-Controller ohne Zugangsschutz** — behandle das Netz entsprechend.

---

## Kurz-Referenz

1. **Ausgabe → „Web-Interface (Port 5000)"** anhaken → Server läuft auf `0.0.0.0:5000`.
2. PC-LAN-IP per `ipconfig` holen → am Handy `http://<PC-IP>:5000` (gleiches WLAN) öffnen.
3. **GO/BACK/STOP** = Cueliste · **Blackout** = alles dunkel (Toggle) · **Fader 1–5** = Executor-Pegel.
4. **Kein Passwort, `0.0.0.0`-Bind** → nur im vertrauenswürdigen Netz nutzen, sonst ausschalten (`NET-01`/`NET-03`).

Zurück zur Übersicht: [../ANLEITUNGEN.md](../ANLEITUNGEN.md)
