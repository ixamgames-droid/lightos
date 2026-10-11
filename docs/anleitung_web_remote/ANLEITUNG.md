# Web-Remote — das Handy als Konsole

> Mit dem eingebauten **Web-Interface** steuerst du LightOS vom Smartphone oder
> Tablet: GO/BACK/STOP für die Cueliste, ein großer **Blackout**-Schalter und
> zehn **Executor-Fader** (Ex 1–10) — alles über den Browser, ohne App-Installation.
> Voraussetzung: Handy und PC hängen im **selben WLAN/LAN**.
>
> Wer **eigene** Tasten, Fader und Cuelisten aus der virtuellen Konsole aufs Handy
> legen will, nimmt die **Handy-Konsole** — siehe [Abschnitt 5](#5-handy-konsole--eigene-tasten-fader-und-cuelisten-aufs-handy-web-09).
>
> **Internet braucht das Handy nicht:** Die Seite kommt vollständig vom LightOS-PC,
> auch ihre Verbindungs-Bibliothek (socket.io). Ein reines Technik-WLAN ohne
> Internetzugang genügt (WEB-06).

---

## 1. Server starten

Der Web-Server ist standardmäßig aus. Einschalten im Menü **Ausgabe →
„Web-Interface (Port 5000)"** (Häkchen setzen). LightOS startet dann einen
kleinen Hintergrund-Server auf **Port 5000** und meldet den Erfolg mit einer
Info-Box; in der Statusleiste erscheint **„Web: :5000 OK"** (grün).

Ein paar Fakten zum Server (aus `src/web/app.py`):

- **Port:** `5000` (fest; `start_server(5000)` wird beim Einschalten aufgerufen).
- **Bind-Adresse:** hängt am Schalter **„LAN-/Handy-Remote"** (siehe unten).
  Eingeschaltet (Standard) lauscht der Server auf `0.0.0.0`, also auf **allen**
  Netzwerk-Schnittstellen, damit ihn andere Geräte im LAN erreichen — genau
  deshalb gilt der Sicherheitshinweis in Abschnitt 4. Ausgeschaltet bindet er
  `127.0.0.1`, dann kommt nur dieser PC dran.
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

Die Remote-Seite hat die Blöcke **Transport** (mit dem **Blackout**-Schalter),
**Executor Fader** und **Log**; oben rechts steht der Verbindungsstatus
(„Verbinde...“, „Verbunden“, „Getrennt“). Jede Aktion läuft direkt auf die
laufende Show (die Befehle sind in `src/web/app.py` als Routen/SocketIO-Handler
umgesetzt):

| Element | Wirkung | Route / Handler in `app.py` |
|---|---|---|
| **GO ▶** | nächster Cue der **GO-Zielliste** (siehe unten) | `POST /api/go` · SocketIO `go` |
| **◀◀ BACK** | einen Cue zurück (GO-Zielliste) | `POST /api/back` · SocketIO `back` |
| **■ STOP** | GO-Zielliste anhalten | `POST /api/stop` · SocketIO `stop` |
| **Blackout** | schaltet die gesamte Ausgabe dunkel und wieder hell (Toggle) — derselbe Blackout wie oben rechts in der App: alles auf 0, nur Positionen/Gobo von Moving Heads bleiben | `POST /api/blackout` · SocketIO `blackout` |
| **Fader Ex 1–10** | setzen den Pegel der **Executor-Fader** (Slots 1–10, 0–100 %) | `POST /api/executor/<slot>/fader` · SocketIO `fader` |

**Welche Cueliste trifft GO / BACK / STOP?** Dieselbe wie die Leertaste am Pult:

1. die im Playback gewählte Cueliste, **wenn sie auf einem Executor liegt**;
2. sonst die Cueliste des ersten belegten Executors der aktuellen Page;
3. sonst die erste Cueliste, die auf irgendeinem Executor liegt.

Liegt gar keine Cueliste auf einem Executor, schaltet GO die gewählte (bzw.
erste) Cueliste trotzdem weiter — es kommt aber **kein Licht**. Die Antwort von
`/api/go|back|stop` und das SocketIO-`ack` nennen dazu `liste` (Name), `licht`
(`true`/`false`) und bei fehlendem Licht eine `warnung`. (Regel im Code:
`src/core/cueliste_ziel.py`.)

Weitere Details:

- Gibt es gar keine Cueliste, passiert bei **GO/BACK/STOP** nichts (kein Fehler).
- **Blackout** ist ein Umschalter: erneutes Tippen hebt den Blackout wieder auf.
  Der Button färbt sich, solange Blackout aktiv ist.
- **Executor-Fader** entsprechen den Playback-Executoren 1–10 in LightOS; die
  Remote zeigt alle zehn (Ex 1–10). Beim Öffnen liest die Seite über `GET /api/status`
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
  `HttpOnly`/`SameSite=Strict`-Cookie die Anmeldung. Token und Direkt-Link zeigt der Dialog
  **„Ausgabe → Web-Remote: Verbindung & Token…"** (er öffnet sich auch beim Einschalten);
  dort macht **„Schlüssel erneuern (neues Token)"** alle bisherigen Links, QR-Codes und
  angemeldeten Geräte sofort ungültig — auch am **laufenden** Server, ohne Neustart. Schon verbundene Geräte werden dabei
  aktiv getrennt (ein offener WebSocket läuft nicht mehr durch das HTTP-Gate und könnte sonst
  weitersteuern), und ein Wiederverbinden mit der alten Anmeldung wird abgewiesen.
- **CORS-Allowlist (NET-03).** Statt `cors_allowed_origins="*"` erlaubt der SocketIO-Endpunkt
  nur noch die bekannten Origins (die eigenen Adressen des PCs als `http://<lan-ip>:5000`,
  dazu `127.0.0.1` und `localhost`) — eine fremde Webseite im selben Netz kann sich nicht
  mehr einfach drauf verbinden. Die Liste entsteht beim Einschalten des Web-Interface.
- **LAN-Bind steuerbar.** Die Checkbox **„LAN-/Handy-Remote"** im selben Dialog (Default AN,
  sicher weil Token davor) bindet `0.0.0.0` (das Handy erreicht es); AUS bindet `127.0.0.1`
  (nur der PC selbst). Die Bind-Adresse wird beim Serverstart gesetzt — läuft das
  Web-Interface gerade, startet LightOS es beim Umschalten deshalb **automatisch neu**, damit
  „aus" auch wirklich sofort „aus" heißt (die Statusleiste bestätigt das).

**Trotzdem Rest-Risiko im Blick behalten:**

- Das Token ist ein **geteiltes** Setup-Geheimnis (keine Einzel-Benutzer/PIN). Wer den
  Direkt-Link oder den QR-Code kennt, kann steuern → Link, Token und QR-Code nicht im
  Publikum herumzeigen; bei Verdacht **„Schlüssel erneuern (neues Token)"**.
- Weiterhin sinnvoll: ein **vertrauenswürdiges** Netz (eigenes Technik-WLAN), das Interface
  nach Gebrauch ausschalten, und Port 5000 **nicht** ins Internet weiterleiten.

> **Offene Follow-ups:** OSC-Source-Allowlist und Token-Rotation pro Start sind bewusst
> noch offen (siehe Design-Doc); den QR-Code gibt es für die Handy-Konsole
> ([Abschnitt 6](#6-handy-verbinden--qr-code-und-startbildschirm-web-11)). Der OSC-Eingang ist separat nur über den
> Loopback-/„OSC über Netzwerk"-Schalter (Default AUS) abgesichert. Für diesen Schalter gibt
> es derzeit keine Oberfläche; er steht als `osc_network_enabled` in `ui_prefs.json` im
> App-Datenordner (Befund WEB-06).

---

## 5. Handy-Konsole — eigene Tasten, Fader und Cuelisten aufs Handy (WEB-09)

Die feste Seite aus Abschnitt 3 kennt nur GO, Blackout und die Executor-Fader.
Die **Handy-Konsole** zeigt stattdessen **deine** Elemente aus der virtuellen
Konsole: Tasten, Fader und Cuelisten als **Verknüpfungen**. Das Handy drückt
dabei das Original — gleiche Funktion, gleicher Zustand, auch wenn das Element
auf einer anderen Bank oder in einem Kasten liegt. Nichts wird doppelt
programmiert.

### Einrichten

1. **Handy-Konsole bauen:** In der virtuellen Konsole die Seitenleiste
   **„📱 Handy-Konsole"** einblenden (Knopf in der Werkzeugleiste),
   **„Bearbeiten"** einschalten und die Elemente hineinlegen — Schritt für
   Schritt im Abschnitt [Handy-Konsole bauen](#handy-konsole-bauen-web-10)
   weiter unten. Am schnellsten geht der Anfang mit **„Automatisch füllen"**.
2. **Einschalten:** in der Seitenleiste oben den Schalter **„Handy-Konsole:
   aus/an"** umlegen — oder **Ausgabe → „Web-Remote: Verbindung & Token…"** →
   Haken bei **„Handy-Konsole"**. Beides ist dieselbe Einstellung; Standard ist
   **aus**. Den Link fürs Handy (`http://<PC-IP>:5000/konsole?k=<token>`) zeigt
   der Dialog, den **„Verbinden…"** in der Seitenleiste öffnet.
3. **Am Handy öffnen:** den **QR-Code** scannen (er steht in der Seitenleiste
   und im Dialog) und die Seite auf den Startbildschirm legen — siehe
   [Abschnitt 6 „Handy verbinden"](#6-handy-verbinden--qr-code-und-startbildschirm-web-11).
   Die feste Seite zeigt oben rechts zusätzlich **„Handy-Konsole ▸"**, solange
   die Konsole eingeschaltet ist.

Die Handy-Seiten gehören zur Show: sie werden mit der Show gespeichert und
gehen auch bei **„Canvas exportieren…/importieren…"** mit. Eine Show von früher
lädt unverändert — sie hat einfach noch keine Handy-Seiten. Löschst du ein
Element in der Konsole, verschwindet seine Verknüpfung; machst du das Löschen
rückgängig, ist auch die Verknüpfung wieder da.

### Handy-Konsole bauen (WEB-10)

Die Seitenleiste **„📱 Handy-Konsole"** zeigt das Handy im Hochformat als
**Raster aus 4 Spalten × 10 Zeilen** — so, wie es am Handy aussieht —, darunter
fest **Master** und **BLACKOUT** (die liegen am Handy immer unten und lassen
sich nicht belegen). Was du hier ablegst, sind **Verknüpfungen**: das Element
in der großen Konsole bleibt, wo es ist, und behält seine Funktion.

1. **Leiste einblenden:** In der Werkzeugleiste der virtuellen Konsole auf
   **„📱 Handy-Konsole"** drücken. Die Leiste erscheint rechts neben der
   Konsole. Ohne „Bearbeiten" ist sie eine **Vorschau**; zum Bauen
   **„Bearbeiten"** einschalten.
2. **Element ablegen** — zwei Wege:
   - **Ziehen:** das Element in der Konsole anfassen und in die Leiste ziehen.
     Die Zielzelle wird **grün** umrandet (frei) oder **rot** (belegt bzw.
     nicht möglich). Loslassen legt die Verknüpfung ab; das Element selbst
     springt an seinen Platz zurück.
   - **Rechtsklick → „📱 Auf Handy-Konsole legen":** legt es auf den nächsten
     freien Platz der Seite, die die Leiste gerade zeigt. Ist die Seite voll,
     kommt es auf die nächste, notfalls auf eine neue.

   Aufs Handy können **Tasten, Fader und Cuelisten**. Bei allem anderen
   (XY-Pad, Drehregler, Anzeigen, Kästen …) und bei **Laser-Muster-Tasten** ist
   der Menüpunkt **ausgegraut** und der Grund steht darunter.
3. **Anordnen:** eine Kachel im Raster anfassen und **verschieben**. Auf ein
   belegtes Feld lässt sie sich nicht legen.
4. **Größe ändern:** die Kachel am **Griff unten rechts** ziehen (er erscheint,
   sobald die Kachel angeklickt ist).

   | Art | kleinste … größte Größe (Spalten × Zeilen) |
   |---|---|
   | Taste | 1 × 1 … 4 × 2 |
   | Fader senkrecht | 1 × 2 … 1 × 5 |
   | Fader waagerecht | 2 × 1 … 4 × 1 (in **einer** Zeile nach rechts ziehen) |
   | Cueliste | 4 × 2 … 4 × 4 (immer volle Breite) |
5. **Herunternehmen:** Kachel anklicken und **Entf** drücken, oder Rechtsklick
   → **„Von der Handy-Konsole nehmen"**. Das löscht nur die Verknüpfung, nie das
   Element in der Konsole.
6. **Seiten:** über dem Raster stehen die Reiter. **„+"** legt eine Seite an
   (höchstens 12), **„−"** löscht die gezeigte Seite (Rückfrage, wenn etwas
   darauf liegt). **Doppelklick** auf einen Reiter benennt um, **Ziehen**
   ändert die Reihenfolge. Ein Element darf auf **mehreren Seiten** liegen
   (zum Beispiel der Master-Fader), je Seite aber nur einmal — dafür die
   Seite zuerst über ihren Reiter wählen.
7. **„Automatisch füllen"** legt alle fernbedienbaren Elemente auf einmal ab:
   Cuelisten oben (4 × 3 Felder), darunter die Tasten (1 Feld; lange
   Beschriftungen und Not-Tasten 2 Felder breit), dann die Fader senkrecht
   nebeneinander (1 × 3 Felder) und eine Blackout-Taste über die volle Breite
   ganz unten; was nicht passt, kommt auf die nächste Seite. Gibt es schon
   Seiten, werden sie nach einer Rückfrage **ersetzt**. **„Alles leeren"**
   entfernt alle Handy-Seiten (ebenfalls mit Rückfrage).
8. **Verbinden:** oben in der Leiste steht der Schalter **„Handy-Konsole:
   aus/an"**, darunter der Zustand (**aus** · **an · 0 Handys verbunden** ·
   **an · 2 Handys verbunden**) und — sobald das Web-Interface läuft und die
   Handy-Konsole an ist — der **QR-Code** fürs Handy (Klick vergrößert ihn).
   **„Verbinden…"** öffnet den Dialog mit QR-Code, Link und Schlüssel. Der Schalter geht auch ohne „Bearbeiten" — die Handy-Konsole
   lässt sich so jederzeit mit einem Griff ausschalten.

Jeder Schritt ist **ein** Rückgängig-Schritt (**Strg+Z**, wiederholen mit
**Strg+Y**). Ein **verbundenes Handy** zeigt jede Änderung sofort, ohne
Nachladen. Elemente, die auf einer Handy-Seite liegen, tragen im
Bearbeiten-Modus in der großen Konsole ein kleines **grünes Handy-Abzeichen**
oben rechts.

### Bedienen

| Element | Am Handy |
|---|---|
| **Taste** | Antippen löst aus. Der Zustand kommt vom Pult zurück: läuft die Funktion, leuchtet die Taste in ihrer Farbe aus der Konsole. Tasten mit dem Zusatz **„halten"** (Flash, „nur gehalten", Blackout, Alles Weiß) wirken, solange der Finger darauf liegt. |
| **Fader** | Senkrecht, mit Prozentanzeige. Gezogen wird **relativ**: ein versehentliches Antippen verstellt nichts. Bewegt jemand den Fader am Pult, wandert er am Handy mit. |
| **Cueliste** | Laufende Cue, die nächste Cue und **GO / BACK / STOP** — für genau diese Cueliste (nicht die „GO-Zielliste" der festen Seite). |
| **Master + BLACKOUT** (unten, immer da) | Grand Master als Fader; **BLACKOUT** schaltet um (antippen = dunkel, noch einmal = hell) und leuchtet rot, solange das Pult dunkel ist. |
| **Seiten** | Reiter oben, oder auf freier Fläche seitlich wischen. |

Oben rechts steht die Verbindung: **verbunden** (grün) oder **getrennt** (rot).
Solange das Handy getrennt ist, ist die Bedienung **gesperrt** — nichts wird
„blind" gedrückt und später nachgeholt. Sobald die Verbindung wieder steht,
gleicht das Handy den ganzen Zustand neu ab.

### Was dabei zur Sicherheit gilt

- **Nur was auf einer Handy-Seite liegt**, ist vom Handy aus zu sehen und zu
  bedienen. Alles andere beantwortet der Server mit **403** — auch wenn jemand
  die Kennung eines Elements kennt.
- **Gehaltene Tasten werden losgelassen**, wenn die Verbindung abreißt (WLAN
  weg, Seite geschlossen, Akku leer), wenn du die Handy-Konsole ausschaltest,
  den Schlüssel neu erzeugst oder das Web-Interface stoppst. Eine Flash-Taste
  bleibt so nicht hängen.
- Es gilt **derselbe Schlüssel** wie für die feste Seite. Er wird beim Verbinden
  geprüft und bei jeder einzelnen Bedienung noch einmal; nach „Schlüssel
  erneuern" kann auch ein noch verbundenes Handy nichts mehr auslösen.
- **Laser:** Scharf geschaltet wird ein Laser nur am Pult — vom Handy aus geht
  nur „unscharf". Laser-Muster lassen sich nicht aufs Handy legen. Den
  **Laser-NOT-AUS** kann das Handy auslösen, aber nie aufheben, auch nicht über
  einen Fader oder eine Farb-Taste, die Laser-Werte setzt.
- Die Seite kommt vollständig vom LightOS-PC und braucht **kein Internet**.

Technik in Kürze: Seite `GET /konsole`, Stand `GET /api/vc/konsole`, Bedienung
über die Socket-Verbindung (`vc_hallo`, `vc_aktion`, `vc_pult`; Rückmeldung
`vc_konsole`, `vc_zustand`, höchstens zehnmal je Sekunde) — die Adressen
`POST /api/vc/widget/<Kennung>/aktion` und `POST /api/vc/pult` gibt es
zusätzlich. Wer über diese HTTP-Adressen eine Halte-Taste drückt, muss sie
selbst wieder loslassen; das automatische Loslassen hängt an der
Socket-Verbindung.

---

## 6. Handy verbinden — QR-Code und Startbildschirm (WEB-11)

### QR-Code scannen

1. **Web-Interface einschalten** (Ausgabe → „Web-Interface (Port 5000)") und die
   **Handy-Konsole** einschalten (Schalter in der Seitenleiste oder Haken im
   Dialog). Der QR-Code erscheint **nur, wenn beides an ist**.
2. Den Code findest du an zwei Stellen:
   - in der Seitenleiste **„📱 Handy-Konsole"** der virtuellen Konsole, klein
     unter dem Schalter — **ein Klick darauf vergrößert ihn** in einem eigenen
     Fenster;
   - im Dialog **Ausgabe → „Web-Remote: Verbindung & Token…"** (den öffnet auch
     **„Verbinden…"** in der Seitenleiste), groß, unter dem Link.
3. Am Handy die **Kamera** auf den Code halten und den angezeigten Link
   antippen. Das Handy muss im **selben WLAN** sein wie der PC. Die Seite
   öffnet sich und ist sofort angemeldet.

Im Code steht derselbe Link wie im Feld darüber:
`http://<PC-IP>:5000/konsole?k=<Schlüssel>`. Der Code wird auf dem PC erzeugt —
ohne Internet und ohne zusätzliches Programm.

> **Nur im eigenen WLAN zeigen — wer den Code scannt, kann die Handy-Konsole
> bedienen.** Den Code nicht auf eine Leinwand, in einen Stream oder in ein
> Foto geraten lassen. Ist das doch passiert: im Dialog **„Schlüssel erneuern
> (neues Token)"** drücken. Alle alten Codes und Links gelten dann sofort nicht
> mehr, verbundene Handys werden getrennt, und der angezeigte Code wechselt auf
> den neuen Schlüssel.

**Mehrere Netzwerkkarten** (zum Beispiel WLAN und Kabel, oder eine virtuelle
Karte): unter dem Code erscheint die Auswahl **„Netzwerkkarte"** mit Name und
Adresse. Wähle die Karte, die im selben Netz hängt wie das Handy — meist das
WLAN. LightOS merkt sich die Wahl. Angeboten werden nur Adressen, die der PC
gerade wirklich hat.

**Statt des Codes steht ein Hinweis?** Dann fehlt genau der genannte Schritt:

| Hinweis | Was zu tun ist |
|---|---|
| „Das Web-Interface läuft nicht." | **Ausgabe → Web-Interface (Port 5000)** anhaken. |
| „… nur auf diesem PC erreichbar." | Im Dialog **„LAN-/Handy-Remote"** anhaken — sonst kommt kein anderes Gerät an die Seite. |
| „Die Handy-Konsole ist ausgeschaltet." | Schalter **„Handy-Konsole"** einschalten. |
| „Keine Netzwerkverbindung gefunden." | Den PC mit dem WLAN (oder per Kabel mit dem Router) verbinden. |
| „Das Netzwerk hat sich geändert …" | Der PC hat seine Adresse erst bekommen, als das Web-Interface schon lief. **Web-Interface einmal aus- und wieder einschalten.** |

### Auf den Startbildschirm legen

Danach startet die Handy-Konsole mit einem Fingertipp, im Vollbild und ohne
Adresszeile — wie eine App.

- **iPhone / iPad (Safari):** **Teilen** (das Quadrat mit dem Pfeil nach oben)
  → **„Zum Home-Bildschirm"** → **„Hinzufügen"**.
- **Android (Chrome):** **Menü ⋮** → **„App installieren"** bzw. **„Zum
  Startbildschirm hinzufügen"**.

Beim ersten Besuch zeigt die Seite dazu unten einen kleinen Tipp; mit **×**
verschwindet er dauerhaft.

Was du dabei wissen solltest:

- **Die Seite braucht die laufende Verbindung zum Pult.** Sie ist keine
  eigenständige App und funktioniert nicht „offline": ohne laufendes LightOS
  und ohne das gemeinsame WLAN zeigt sie „getrennt". (Ein Offline-Speicher im
  Handy würde eine verschlüsselte Verbindung mit Zertifikat voraussetzen, die
  es im Heimnetz nicht gibt — und ohne Pult gäbe es ohnehin nichts zu bedienen.)
- **Der Schlüssel steht nicht im Symbol.** Das Handy merkt sich die Anmeldung
  und den zuletzt gültigen Schlüssel selbst (nur auf diesem Gerät). Deshalb
  kommst du vom Startbildschirm aus wieder hinein, auch nach einem Neustart von
  LightOS.
- **Nach „Schlüssel erneuern"** zeigt die Seite **„Neu verbinden"**. Dann den
  neuen QR-Code scannen — oder, wenn die Seite als Symbol vom Startbildschirm
  läuft, den Schlüssel in das Feld auf der Seite **eintippen** (er steht im
  Dialog hinter „Token:") und **„Verbinden"** drücken.
- **iPhone:** Je nach iOS-Version führt das Symbol auf dem Home-Bildschirm
  seinen eigenen Speicher, getrennt von Safari. Zeigt der erste Start vom
  Home-Bildschirm „Kein Zugang", den Schlüssel dort einmal eintippen — danach
  merkt ihn sich auch das Symbol.
- **Die Adresse des PCs muss gleich bleiben.** Das Symbol zeigt auf die
  Adresse, unter der du es angelegt hast. Vergibt der Router dem PC eine neue,
  läuft das Symbol ins Leere: neu scannen und das Symbol neu anlegen — oder dem
  PC eine feste Adresse geben
  ([Netzwerk vorbereiten, Schritt 3](../anleitung_netzwerk_windows/ANLEITUNG.md)).

### „Seite nicht erreichbar" — was tun?

Der Reihe nach prüfen:

1. **Gleiches WLAN?** Handy und PC müssen im selben Netz sein. Ein
   **Gast-WLAN** trennt die Geräte oft voneinander; mobile Daten am Handy
   führen gar nicht ins Heimnetz.
2. **Richtige Netzwerkkarte gewählt?** Hat der PC mehrere, unter dem QR-Code
   die Karte wählen, die im WLAN des Handys hängt, und neu scannen. Eine
   Adresse, die mit `172.` beginnt oder zu einer virtuellen Karte gehört
   (Docker, VPN, WSL), ist fast nie die richtige.
3. **Firewall:** Unter Windows muss **TCP-Port 5000** für eingehende
   Verbindungen freigegeben sein. Die Abfrage beim ersten Einschalten mit
   **„Zugriff erlauben"** (privates Netz) bestätigen; wie du die Freigabe
   nachträglich anlegst und prüfst, steht in
   [Netzwerk vorbereiten (Windows)](../anleitung_netzwerk_windows/ANLEITUNG.md).
4. **Läuft das Web-Interface, und ist „LAN-/Handy-Remote" an?** Zeigt LightOS
   statt des Codes einen Hinweis, zuerst den erledigen (Tabelle oben).
5. **Die Seite lädt, zeigt aber „Kein Zugang" oder „Neu verbinden":** Der
   Schlüssel passt nicht (mehr) — den aktuellen QR-Code scannen.

---

## Kurz-Referenz

1. **Ausgabe → „Web-Interface (Port 5000)"** anhaken → Server läuft auf `0.0.0.0:5000`.
2. PC-LAN-IP per `ipconfig` holen → am Handy `http://<PC-IP>:5000/?k=<token>` öffnen (Token/Direkt-Link aus dem Verbindungs-Dialog, gleiches WLAN).
3. **GO/BACK/STOP** = Cueliste · **Blackout** = alles dunkel (Toggle) · **Fader Ex 1–10** = Executor-Pegel.
4. **Token-geschützt** (`?k=…`, ohne → 403) + CORS-Allowlist; Token ist ein **geteiltes** Setup-Geheimnis → nur im vertrauenswürdigen Netz nutzen, danach ausschalten.
5. **Handy-Konsole** (eigene Tasten/Fader/Cuelisten): VC → **„📱 Handy-Konsole"** → Bearbeiten → Elemente hineinziehen oder **„Automatisch füllen"**, Schalter **„Handy-Konsole: an"** → am Handy den **QR-Code** scannen (Seitenleiste oder **„Verbinden…"**; Link: `http://<PC-IP>:5000/konsole?k=<token>`) → **„Zum Startbildschirm hinzufügen"**.

Zurück zur Übersicht: [../ANLEITUNGEN.md](../ANLEITUNGEN.md)
