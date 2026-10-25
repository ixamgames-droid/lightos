# Web-Remote — das Handy als Konsole

> Mit der **Handy-Konsole** bedienst du LightOS vom Smartphone oder Tablet:
> **deine** Tasten, Fader und Cuelisten aus der virtuellen Konsole, dazu Grand
> Master und Blackout — im Browser, ohne App-Installation. Voraussetzung: Handy
> und PC hängen im **selben WLAN/LAN**.
>
> Ab Werk ist alles **aus**: das Web-Interface, der Zugriff aus dem WLAN und die
> Handy-Konsole. Ein Knopf — **„📱 Handy verbinden"** — schaltet zusammen ein,
> was das Handy braucht ([Abschnitt 1](#1-handy-verbinden--in-einem-schritt)).
>
> Die ältere **feste Fernbedienung** (GO/BACK/STOP, zehn Executor-Fader,
> Blackout) gibt es weiterhin, aber nur noch unter **„Erweitert"** und mit eigenem
> Schlüssel ([Abschnitt 6](#6-erweitert-feste-fernbedienung-und-roh-dmx)).
>
> **Internet braucht das Handy nicht:** Die Seite kommt vollständig vom LightOS-PC,
> auch ihre Verbindungs-Bibliothek (socket.io). Ein reines Technik-WLAN ohne
> Internetzugang genügt (WEB-06).

---

## 1. Handy verbinden — in einem Schritt

1. Im Menü **Ausgabe → „Web-Remote: Verbindung & Token…"** öffnen — oder in der
   virtuellen Konsole in der Seitenleiste **„📱 Handy-Konsole"** auf
   **„📱 Handy verbinden"** drücken.
2. Im Dialog **„📱 Handy verbinden"** drücken. Das schaltet in einem Schritt ein:
   - **„LAN-/Handy-Remote"** (das Handy darf den PC über das WLAN erreichen),
   - die **„Handy-Konsole"**,
   - das **Web-Interface** auf Port 5000 — läuft es schon, aber nur für diesen
     PC, startet LightOS es neu.

   Aus der Seitenleiste heraus öffnet sich der Dialog und erledigt diesen
   Schritt sofort.
3. Der Knopf heißt jetzt **„📱 Handy verbunden — QR-Code scannen"**, darunter
   steht der **QR-Code**. Mit der Handy-Kamera scannen, den Link antippen — die
   Handy-Konsole öffnet sich und ist angemeldet.

Oben im Dialog steht, was gerade gilt: **„Web-Interface: aus"**, **„… läuft — nur
dieser PC (127.0.0.1:5000)"** oder **„… läuft — im (W)LAN erreichbar (Adresse)"**,
dazu **„Handy-Konsole: bereit"**, sobald ein Handy verbinden kann. In der
Statusleiste des Hauptfensters steht **„Web: :5000 OK"**.

Unter dem QR-Code steht derselbe Link als Text, `http://<PC-IP>:5000/konsole?k=<Schlüssel>`,
mit **„Link kopieren"** daneben. Das ist die **einzige** Stelle im Dialog, an der
der Schlüssel steht.

Die Schalter im Dialog einzeln:

| Schalter | Wirkung | ab Werk |
|---|---|---|
| **Handy-Konsole (bedient nur Elemente der Handy-Seiten)** | das Handy bedient, was auf einer Handy-Seite liegt — sonst nichts | aus |
| **LAN-/Handy-Remote (aus = nur dieser PC)** | an: der Server lauscht auf `0.0.0.0`, das Handy erreicht ihn; aus: nur `127.0.0.1`, kein anderes Gerät kommt dran | aus |
| **Laser vom Handy erlauben** | Elemente mit Laser-Inhalt lassen sich vom Handy bedienen — nur nach einem Bestätigungsfenster ([Bedingungen](LASER_VOM_HANDY.md)) | aus |
| **Erweitert → Feste Fernbedienung** | die ältere feste Seite mit eigenem Schlüssel ([Abschnitt 6](#6-erweitert-feste-fernbedienung-und-roh-dmx)) | aus |
| **Erweitert → Roh-DMX** | einzelne DMX-Kanäle über die feste Fernbedienung | aus |

**„LAN-/Handy-Remote"** wird beim Serverstart gelesen. Läuft das Web-Interface
gerade, startet LightOS es beim Umschalten deshalb **automatisch neu** — „aus"
heißt so sofort „aus".

Den Server ein- und ausschalten geht auch einzeln im Menü **Ausgabe →
„Web-Interface (Port 5000)"**; beim Einschalten öffnet sich derselbe Dialog.
Zum Ausschalten das Häkchen wieder entfernen — die Statusleiste zeigt dann
**„Web: aus"**, und alle verbundenen Geräte werden getrennt.

Der Flask-`SECRET_KEY` steht nicht im Code: Ist die Umgebungsvariable
`LIGHTOS_FLASK_SECRET` gesetzt, gilt sie, sonst erzeugt LightOS bei jedem Start
einen zufälligen. Im normalen Betrieb musst du hier nichts tun.

---

## 2. Handy-Konsole bauen

Die Handy-Konsole zeigt **deine** Elemente aus der virtuellen Konsole als
**Verknüpfungen**: das Handy drückt das Original — gleiche Funktion, gleicher
Zustand, auch wenn das Element auf einer anderen Bank oder in einem Kasten
liegt. Nichts wird doppelt programmiert.

Die Seitenleiste **„📱 Handy-Konsole"** zeigt das Handy im Hochformat als
**Raster aus 4 Spalten × 10 Zeilen** — so, wie es am Handy aussieht —, darunter
fest **Master** und **BLACKOUT** (die liegen am Handy immer unten und lassen
sich nicht belegen).

1. **Leiste einblenden:** In der Werkzeugleiste der virtuellen Konsole auf
   **„📱 Handy-Konsole"** drücken. Die Leiste erscheint rechts neben der
   Konsole. Ohne „Bearbeiten" ist sie eine **Vorschau**; zum Bauen
   **„Bearbeiten"** einschalten. (Im Kiosk gibt es die Leiste nicht.)
2. **Element ablegen** — zwei Wege:
   - **Ziehen:** das Element in der Konsole anfassen und in die Leiste ziehen.
     Die Zielzelle wird **grün** umrandet (frei) oder **rot** (belegt bzw.
     nicht möglich). Loslassen legt die Verknüpfung ab; das Element selbst
     springt an seinen Platz zurück.
   - **Rechtsklick → „📱 Auf Handy-Konsole legen":** legt es auf den nächsten
     freien Platz der Seite, die die Leiste gerade zeigt. Ist die Seite voll,
     kommt es auf die nächste, notfalls auf eine neue.

   Aufs Handy können **Tasten, Fader und Cuelisten**. Bei allem anderen
   (XY-Pad, Drehregler, Anzeigen, Kästen …) ist der Menüpunkt **ausgegraut**,
   und der Grund steht darunter. Ebenso bei einem Element mit **Laser-Inhalt**,
   solange **„Laser vom Handy erlauben"** aus ist (siehe
   [Abschnitt 5](#5-sicherheit)).
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
   ganz unten; was nicht passt, kommt auf die nächste Seite. Elemente mit
   **Laser-Inhalt** lässt es weg, solange **„Laser vom Handy erlauben"** aus
   ist. Gibt es schon Seiten, werden sie nach einer Rückfrage **ersetzt**.
   **„Alles leeren"** entfernt alle Handy-Seiten (ebenfalls mit Rückfrage).
8. **Verbinden:** oben in der Leiste steht der Schalter **„Handy-Konsole:
   aus/an"**, darunter der Zustand (**aus** · **an · 0 Handys verbunden** ·
   **an · 2 Handys verbunden**) und — sobald das Web-Interface im WLAN läuft
   und die Handy-Konsole an ist — der **QR-Code** fürs Handy (Klick vergrößert
   ihn). **„📱 Handy verbinden"** öffnet den Dialog und schaltet alles Nötige
   ein ([Abschnitt 1](#1-handy-verbinden--in-einem-schritt)). Der Schalter geht
   auch ohne „Bearbeiten" — die Handy-Konsole lässt sich so jederzeit mit einem
   Griff ausschalten.

Jeder Schritt ist **ein** Rückgängig-Schritt (**Strg+Z**, wiederholen mit
**Strg+Y**). Ein **verbundenes Handy** zeigt jede Änderung sofort, ohne
Nachladen. Elemente, die auf einer Handy-Seite liegen, tragen im
Bearbeiten-Modus in der großen Konsole ein kleines **grünes Handy-Abzeichen**
oben rechts.

Die Handy-Seiten gehören zur Show: sie werden mit der Show gespeichert und
gehen auch bei **„Canvas exportieren…/importieren…"** mit. Eine Show von früher
lädt unverändert — sie hat einfach noch keine Handy-Seiten. Löschst du ein
Element in der Konsole, verschwindet seine Verknüpfung; machst du das Löschen
rückgängig, ist auch die Verknüpfung wieder da.

---

## 3. Bedienen am Handy

| Element | Am Handy |
|---|---|
| **Taste** | Antippen löst aus. Der Zustand kommt vom Pult zurück: läuft die Funktion, leuchtet die Taste in ihrer Farbe aus der Konsole. Tasten mit dem Zusatz **„halten"** (Flash, „nur gehalten", Blackout, Alles Weiß, Bibliothek-Snap im Flash-Modus) wirken, solange der Finger darauf liegt. Hält das Pult oder ein anderes Handy eine solche Taste gerade, ändert ein Antippen nichts. |
| **Fader** | Senkrecht oder waagerecht, mit Prozentanzeige. Gezogen wird **relativ**: ein versehentliches Antippen verstellt nichts. Bewegt jemand den Fader am Pult, wandert er am Handy mit. |
| **Cueliste** | Laufende Cue, die nächste Cue und **GO / BACK / STOP** — für genau diese Cueliste. |
| **Master** (unten, immer da) | Grand Master als waagerechter Fader. |
| **BLACKOUT** (unten, immer da) | Antippen = dunkel; noch einmal antippen hebt den Blackout auf — aber **nur, wenn dieses Handy ihn gesetzt hat**. Leuchtet rot, solange das Pult dunkel ist. |
| **Seiten** | Reiter oben, oder auf freier Fläche seitlich wischen. |

Oben rechts steht die Verbindung: **verbunden** (grün) oder **getrennt** (rot).
Solange das Handy getrennt ist, ist die Bedienung **gesperrt** — nichts wird
„blind" gedrückt und später nachgeholt. Sobald die Verbindung wieder steht,
gleicht das Handy den ganzen Zustand neu ab.

Was das Handy außerdem anzeigt:

- **„LASER NOT-AUS AKTIV"** — ein roter Balken oben, solange am Pult der
  Laser-NOT-AUS ausgelöst ist. Lösen lässt er sich nur am Pult.
- **🔒 Laser – Freigabe am Pult** — ein graues Element mit Laser-Inhalt, solange
  **„Laser vom Handy erlauben"** aus ist. Antippen meldet nur den Grund.
- **⚠ mit rot gestricheltem Rand** — das Element hat sein **Ziel verloren**
  (Funktion gelöscht, Blackout-Gruppe nicht mehr da), genau wie am Pult. Es
  leuchtet dann auch nicht „aktiv", denn es schaltet nichts.
- Eine kurze Meldung unten, wenn das Pult etwas abgelehnt hat — zum Beispiel
  **„Blackout kam nicht von diesem Handy – aufheben am Pult"**.

---

## 4. QR-Code und Startbildschirm

### QR-Code scannen

Den QR-Code gibt es an zwei Stellen:

- im Dialog **Ausgabe → „Web-Remote: Verbindung & Token…"**, groß;
- in der Seitenleiste **„📱 Handy-Konsole"** der virtuellen Konsole, klein unter
  dem Schalter — **ein Klick darauf vergrößert ihn** in einem eigenen Fenster.

Am Handy die **Kamera** auf den Code halten und den angezeigten Link antippen.
Das Handy muss im **selben WLAN** sein wie der PC. Der Code wird auf dem PC
erzeugt — ohne Internet und ohne zusätzliches Programm.

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

**Statt des Codes steht ein Hinweis?** Am schnellsten hilft **„📱 Handy
verbinden"**. Einzeln:

| Hinweis | Was zu tun ist |
|---|---|
| „Das Web-Interface läuft nicht." | **„📱 Handy verbinden"** — oder **Ausgabe → Web-Interface (Port 5000)** anhaken. |
| „… nur auf diesem PC erreichbar." | **„📱 Handy verbinden"** — oder im Dialog **„LAN-/Handy-Remote"** anhaken. |
| „Die Handy-Konsole ist ausgeschaltet." | **„📱 Handy verbinden"** — oder den Schalter **„Handy-Konsole"** einschalten. |
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
  Dialog im Link hinter `?k=`) und **„Verbinden"** drücken.
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
4. **Läuft das Web-Interface im WLAN?** Zeigt der Dialog „nur dieser PC" oder
   statt des Codes einen Hinweis: **„📱 Handy verbinden"** drücken.
5. **Die Seite lädt, zeigt aber „Kein Zugang" oder „Neu verbinden":** Der
   Schlüssel passt nicht (mehr) — den aktuellen QR-Code scannen.

---

## 5. Sicherheit

- **Zwei Schlüssel, getrennte Rechte.** Der Schlüssel im QR-Code öffnet **nur
  die Handy-Konsole**. Die feste Fernbedienung hat einen **eigenen** Schlüssel
  und ist ab Werk aus ([Abschnitt 6](#6-erweitert-feste-fernbedienung-und-roh-dmx)).
  Mit dem Link der Handy-Konsole kommt man also nicht an GO aller Listen, an
  alle Executor-Fader oder an rohe DMX-Kanäle.
- **Nur was auf einer Handy-Seite liegt**, ist vom Handy aus zu sehen und zu
  bedienen. Alles andere beantwortet der Server mit **403** — auch wenn jemand
  die Kennung eines Elements kennt.
- **Jede Bedienung wird geprüft.** Der Schlüssel wird beim Verbinden geprüft
  und bei jeder einzelnen Bedienung noch einmal — über die Socket-Verbindung
  genauso wie über HTTP. Nach **„Schlüssel erneuern"** kann auch ein noch
  verbundenes Gerät nichts mehr auslösen; es wird getrennt. „Schlüssel
  erneuern" erneuert **beide** Schlüssel.
- **Kaputte Anfragen ändern nichts.** Fehlt ein Wert oder ist er ungültig
  (kein Zahlwert, außerhalb des Bereichs), antwortet der Server mit einem Fehler
  und lässt alles, wie es ist — kein Fader springt auf 100 %, kein Blackout geht
  auf.
- **Blackout:** Vom Handy (und von der festen Fernbedienung) wird nie ein
  Blackout aufgehoben, den nicht **dieses Gerät** gesetzt hat. Hat ihn jemand am
  Pult oder ein anderes Handy gesetzt — oder seitdem am Pult umgeschaltet —,
  hebt ihn nur das Pult auf. Eine Taste, deren Zusatzaktion den Blackout
  ausschaltet, lehnt das Handy ab, solange der Blackout steht.
- **Gehaltene Tasten** werden losgelassen, wenn die Verbindung abreißt (WLAN
  weg, Seite geschlossen, Akku leer), wenn du die Handy-Konsole ausschaltest,
  den Schlüssel erneuerst oder das Web-Interface stoppst — und wenn die Taste am
  Pult gelöscht, ihr Typ geändert oder eine Show geladen wird. Hält eine Taste
  das Pult oder ein zweites Handy, lässt das Loslassen **eines** Handys sie nicht
  los. Halten geht nur über die Socket-Verbindung der Handy-Seite; über HTTP
  gibt es nur das Antippen.
- **Laser:** Elemente mit Laser-Inhalt sind am Handy gesperrt, bis jemand am
  Pult **„Laser vom Handy erlauben"** einschaltet und die Bedingungen bestätigt
  — siehe [Laser vom Handy erlauben](LASER_VOM_HANDY.md). Scharf geschaltet
  wird ein Laser in jedem Fall nur am Pult; vom Handy aus geht nur „unscharf".
  Den **Laser-NOT-AUS** kann das Handy auslösen, aber nie aufheben.
- **Der Schlüssel steht in keinem Protokoll.** Im Sitzungs-Log und im
  Diagnosepaket erscheint statt des Schlüssels `<schluessel>`.
- **Ab Werk zu.** Web-Interface, Zugriff aus dem WLAN, Handy-Konsole, feste
  Fernbedienung, Roh-DMX und Laser-Freigabe sind ab Werk aus.

Unter der Haube (Design-Entscheidung
[DESIGN_DECISION_REMOTE_SECURITY_2026-07-14.md](../DESIGN_DECISION_REMOTE_SECURITY_2026-07-14.md)):
ein Gate vor jeder Anfrage lässt nur durch, wer das Recht der jeweiligen Route
hat (jede Route steht in einer Rechte-Tabelle; eine Route ohne Eintrag ist für
alle gesperrt). Nach dem Öffnen des Links merkt sich ein
`HttpOnly`/`SameSite=Strict`-Cookie die Anmeldung. Die Socket-Verbindung nimmt
nur Seiten an, die von einer eigenen Adresse des PCs kommen (CORS-Allowlist
statt `*`).

**Rest-Risiko im Blick behalten:** Der Schlüssel ist ein **geteiltes**
Geheimnis, keine Benutzer-Anmeldung. Wer den Link oder den QR-Code kennt, kann
bedienen. Deshalb: eigenes Technik-WLAN, das Web-Interface nach Gebrauch
ausschalten, Port 5000 **nie** ins Internet weiterleiten, bei Verdacht
**„Schlüssel erneuern"**.

> **Offene Follow-ups:** eine Absender-Liste für OSC und ein neuer Schlüssel bei
> jedem Start sind bewusst noch offen (siehe Design-Doc). Der OSC-Eingang ist
> separat über den Schalter „OSC über Netzwerk" (ab Werk aus) abgesichert; eine
> Oberfläche dafür gibt es noch nicht, er steht als `osc_network_enabled` in
> `ui_prefs.json` im App-Datenordner.

---

## 6. Erweitert: feste Fernbedienung und Roh-DMX

Die **feste Fernbedienung** ist die ältere Seite **„⚡ LightOS Remote"**: GO/BACK/
STOP für die Cueliste, ein großer **Blackout**-Schalter und zehn
**Executor-Fader** (Ex 1–10). Sie bedient unabhängig von den Handy-Seiten.

**Einschalten:** im Dialog auf **„Erweitert"** klicken und **„Feste
Fernbedienung (GO, Executor-Fader, Blackout) — eigener Schlüssel"** anhaken.
Darunter erscheint ihr Link `http://<PC-IP>:5000/?k=<Schlüssel>` mit
**„Kopieren"** — ein **anderer** Schlüssel als der der Handy-Konsole. Das Handy
braucht außerdem **„LAN-/Handy-Remote"**. Ausschalten wirkt sofort, auch auf
schon verbundene Geräte.

| Element | Wirkung |
|---|---|
| **GO ▶** | nächster Cue der **GO-Zielliste** (siehe unten) |
| **◀◀ BACK** | einen Cue zurück (GO-Zielliste) |
| **■ STOP** | GO-Zielliste anhalten |
| **Blackout** | schaltet die gesamte Ausgabe dunkel; erneutes Tippen hebt den Blackout auf — nur, wenn dieses Gerät ihn gesetzt hat |
| **Fader Ex 1–10** | Pegel der Executor-Fader der aktuellen Page (0–100 %); beim Öffnen stehen sie auf dem echten Stand |

**Welche Cueliste trifft GO / BACK / STOP?** Dieselbe wie die Leertaste am Pult:

1. die im Playback gewählte Cueliste, **wenn sie auf einem Executor liegt**;
2. sonst die Cueliste des ersten belegten Executors der aktuellen Page;
3. sonst die erste Cueliste, die auf irgendeinem Executor liegt.

Liegt gar keine Cueliste auf einem Executor, schaltet GO die gewählte (bzw.
erste) Cueliste trotzdem weiter — es kommt aber **kein Licht**; die Antwort
nennt dann eine Warnung. Gibt es gar keine Cueliste, passiert nichts.

**Laser gilt auch hier:** Ohne **„Laser vom Handy erlauben"** lehnt die feste
Fernbedienung GO und BACK auf eine Cueliste mit Laser-Cues ab, ebenso GO und
das **Hochziehen** eines Executor-Faders mit Laser-Inhalt; Herunterziehen und
STOP gehen immer.

**Roh-DMX:** Mit **„Roh-DMX über die feste Fernbedienung"** (nur zusammen mit
der festen Fernbedienung) nimmt der Server einzelne DMX-Kanäle an
(`POST /api/channel/<universe>/<channel>` mit `{"value": 0..255}`). Das ist zum
Einmessen gedacht und ab Werk aus. Kanäle eines Lasers bleiben ohne
**„Laser vom Handy erlauben"** gesperrt.

Für eigene Skripte die Adressen der festen Fernbedienung: `POST /api/go`,
`/api/back`, `/api/stop`, `/api/blackout` (`{"enabled": true|false}`),
`/api/executor/<slot>/fader` (`{"level": 0..1}`), `/api/executor/<slot>/go`,
`/api/programmer/clear`, `GET /api/status`. Ein fehlender oder ungültiger Wert
wird mit **400**, ein unbekannter Slot oder Kanal mit **404** beantwortet — und
ändert nichts.

---

## Kurz-Referenz

1. **Ausgabe → „Web-Remote: Verbindung & Token…"** (oder Seitenleiste **„📱 Handy-Konsole"**) → **„📱 Handy verbinden"** → QR-Code mit dem Handy scannen (gleiches WLAN).
2. Handy-Seiten bauen: VC → **„📱 Handy-Konsole"** → Bearbeiten → Elemente hineinziehen oder **„Automatisch füllen"**.
3. Am Handy auf den **Startbildschirm** legen; bei „Neu verbinden" den aktuellen QR-Code scannen.
4. Ab Werk ist alles aus; **Laser** am Handy nur mit **„Laser vom Handy erlauben"** ([Bedingungen](LASER_VOM_HANDY.md)); Blackout hebt ein Handy nur auf, wenn es ihn selbst gesetzt hat.
5. Feste Fernbedienung und Roh-DMX nur unter **„Erweitert"**, mit eigenem Schlüssel.
6. Bei Verdacht: **„Schlüssel erneuern (neues Token)"** — alle alten Links und QR-Codes gelten sofort nicht mehr.

Zurück zur Übersicht: [../ANLEITUNGEN.md](../ANLEITUNGEN.md)
