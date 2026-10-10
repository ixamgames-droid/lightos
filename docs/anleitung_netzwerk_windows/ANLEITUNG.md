# Netzwerk vorbereiten (Windows): Firewall, feste Adresse, Fehlerbilder

> LightOS spricht über das Netzwerk mit Art-Net- und sACN-Nodes, mit dem Handy
> (Web-Remote) und mit anderen Pulten (DMX-Eingang, MIDI Show Control). **Senden**
> klappt unter Windows ohne Vorbereitung. **Empfangen** nicht: Die Windows-Firewall
> lässt von außen nur herein, was freigegeben ist. Diese Anleitung zeigt, welche
> Funktion welchen Port braucht, wie du dem Rechner eine feste Adresse im Lichtnetz
> gibst, wie du die Freigaben anlegst und wieder entfernst — und woran du die
> häufigsten Fehler erkennst.

Die Beschriftungen stammen von **Windows 11 (24H2, deutsch)**. Die Ports gelten auf
jedem Betriebssystem.

## Was du brauchst

- Einen Windows-Rechner mit LightOS ([INSTALL.md](../../INSTALL.md)).
- Ein **Administrator-Konto** — feste Adresse und Firewall-Regeln lassen sich nur damit
  ändern.
- Für Art-Net und sACN: ein Netzwerkkabel zum Node oder zum Switch des Lichtnetzes.

---

## 1. Welche Funktion braucht eine Freigabe?

| Funktion | Einschalten in LightOS | Protokoll und Port | Freigabe nötig? |
|---|---|---|---|
| Art-Net-**Ausgabe** | **Ausgabe → Konfigurieren...**, Reiter **Art-Net** | sendet an UDP 6454 | nein |
| sACN-**Ausgabe** | Reiter **sACN (E1.31)** | sendet an UDP 5568 | nein |
| Art-Net-**Eingang** | Reiter **DMX Input** → **Art-Net Input aktivieren** | lauscht auf UDP 6454 | **ja** |
| sACN-**Eingang** | Reiter **DMX Input** → **sACN Input aktivieren** | lauscht auf UDP 5568 | **ja** |
| Web-Remote (Handy) | **Ausgabe → Web-Interface (Port 5000)** | lauscht auf TCP 5000 | **ja** |
| MIDI Show Control über Netzwerk | Sektion **MIDI** → **GMA-MSC über Netzwerk** | lauscht auf UDP 6004 | **ja** |
| OS2L (Tempo aus der DJ-Software) | **Ausgabe → OS2L-Server (Port 1234)** | lauscht auf TCP 1234 | nur wenn die DJ-Software auf einem **anderen** Rechner läuft |
| OSC | **Ausgabe → OSC-Server (Port 7770)** | lauscht auf UDP 7770 | nein — in der Voreinstellung nur für Programme auf diesem Rechner erreichbar |

Die Regel dahinter: Was LightOS **sendet**, lässt Windows in der Voreinstellung durch.
Was von außen **hereinkommt**, braucht eine Freigabe. Wer nur Art-Net oder sACN ausgibt,
kann Schritt 4 überspringen und braucht höchstens die feste Adresse aus Schritt 3.

Den Schalter **GMA-MSC über Netzwerk** gibt es erst in Versionen mit MIDI Show Control.
Fehlt er bei dir, lass die Zeile mit Port 6004 weg.

## 2. Netzwerkprofil prüfen: „Privat“ oder „Öffentlich“

Windows ordnet jedes Netz einem Profil zu. **Jede Firewall-Regel gilt nur für die
Profile, für die sie angelegt wurde** — das ist die häufigste Ursache für „gestern ging
es noch“.

Welches Profil gerade gilt, zeigt die PowerShell:

```powershell
Get-NetConnectionProfile | Format-Table InterfaceAlias, NetworkCategory
```

`Public` heißt „Öffentlich“, `Private` heißt „Privat“.

Umstellen: **Einstellungen → Netzwerk und Internet → Ethernet** (bei WLAN: das verbundene
Netz öffnen). Unter **Netzwerkprofiltyp** stehen **Öffentliches Netzwerk (Empfohlen)** und
**Privates Netzwerk**.

- **Eigenes Lichtnetz** (eigener Switch oder Router, nur deine Geräte): **Privates
  Netzwerk** wählen und die Freigaben aus Schritt 4 für „Privat“ anlegen.
- **Fremdes Netz** (WLAN der Location, Hotel): bei **Öffentliches Netzwerk** bleiben und
  dort nichts freigeben. Für das Handy-Remote lieber einen eigenen kleinen Router
  mitbringen.

> **Achtung beim Umstellen:** Der Wechsel wirkt auf **alle** Firewall-Regeln des Rechners,
> nicht nur auf die von LightOS. Zwei Folgen:
>
> - Regeln, die nur für das alte Profil angelegt waren, gelten nicht mehr. Ein Programm,
>   das im Profil „Öffentlich“ erreichbar war, ist es unter „Privat“ erst wieder, wenn es
>   auch dafür eine Regel gibt.
> - Regeln anderer Programme, die nur für „Privat“ angelegt sind, werden wirksam —
>   typisch die Netzwerkerkennung, je nach Rechner auch ein installierter SSH-Server
>   oder Fernwartungs-Programme. Der Rechner ist dann im Netz sichtbar und auf diesen
>   Wegen erreichbar.

**Vorher nachsehen, was „Privat“ öffnen würde.** Diese Abfrage ändert nichts; sie listet
die eingehenden Freigaben, die nur im Profil „Privat“ gelten:

```powershell
Get-NetFirewallRule -Direction Inbound -Enabled True -Action Allow |
    Where-Object { "$($_.Profile)" -match 'Private' -and "$($_.Profile)" -notmatch 'Public' } |
    Select-Object -ExpandProperty DisplayName | Sort-Object -Unique
```

Steht dort etwas, das im Lichtnetz nicht erreichbar sein soll, bleib bei „Öffentlich“
und lege die Freigaben aus Schritt 4 für `Public` an.

## 3. Feste Adresse für das Lichtnetz

Nötig ist das, wenn im Lichtnetz **kein Router** Adressen verteilt — also wenn der Rechner
direkt am Node hängt oder nur ein einfacher Switch dazwischen sitzt. Dann gibt sich
Windows nach etwa einer Minute selbst eine Adresse `169.254.x.x`, und der Node ist nicht
erreichbar. Hängt alles an einem Router mit DHCP, kannst du diesen Schritt auslassen.

1. **Einstellungen → Netzwerk und Internet → Ethernet**. Bei mehreren Netzwerkkarten:
   die Karte, an der das Lichtnetz hängt.
2. In der Zeile **IP-Zuweisung:** auf **Bearbeiten**.
3. Im Dialog **IP-Einstellungen bearbeiten** von **Automatisch (DHCP)** auf **Manuell**
   stellen und den Schalter **IPv4** einschalten.
4. Eintragen:

   | Feld | Wert | Hinweis |
   |---|---|---|
   | **IP-Adresse** | `192.168.1.10` | dasselbe Netz wie der Node, aber eine **andere** letzte Zahl |
   | **Subnetzmaske** | `255.255.255.0` | |
   | **Gateway** | leer | ein reines Lichtnetz hat keinen Router |
   | **Bevorzugter DNS** | leer | |

5. **Speichern**.

Die Adresse richtet sich nach dem Node. Hat er `192.168.1.50`, passt `192.168.1.10`.
Viele Art-Net-Geräte kommen ab Werk mit einer Adresse `2.x.x.x` oder `10.x.x.x` und der
Maske `255.0.0.0` — dann bekommt der Rechner zum Beispiel `2.0.0.10` mit Maske
`255.0.0.0`. Keine Adresse darf im Netz doppelt vorkommen.

Unter Windows 10 fragt der Dialog statt der Subnetzmaske nach der
**Subnetzpräfixlänge**: `24` entspricht `255.255.255.0`, `8` entspricht `255.0.0.0`.

**Internet behalten:** Läuft das Internet über WLAN und das Lichtnetz über das Kabel,
bleibt das WLAN auf **Automatisch (DHCP)**. Weil die Lichtnetz-Karte kein Gateway hat,
geht alles andere weiter über das WLAN.

Dasselbe in der PowerShell (als Administrator), hier für die Karte `Ethernet`:

```powershell
New-NetIPAddress -InterfaceAlias 'Ethernet' -IPAddress 192.168.1.10 -PrefixLength 24
```

**Prüfen:**

```powershell
ipconfig
ping 192.168.1.50
```

Bei der Karte muss unter **IPv4-Adresse** deine Adresse stehen und unter
**Subnetzmaske** die Maske. Der `ping` zum Node muss Antworten bringen.

Hat der Rechner mehrere Karten, wähle zusätzlich in LightOS im Reiter **Art-Net** unter
**Netzwerkkarte:** die Karte des Lichtnetzes — siehe
[Ausgabe einrichten](../anleitung_ausgabe_einrichten/ANLEITUNG.md#3-art-net).

## 4. Firewall-Freigaben anlegen

### Was Windows von selbst anbietet — und warum das oft nicht reicht

Lauscht ein Programm zum ersten Mal auf einem Port, fragt Windows, ob es Zugriff aus dem
Netzwerk bekommen soll. Wer zustimmt, ist für den Moment fertig. Die Regel, die dabei
entsteht, hat aber drei Haken:

1. **Sie hängt am Programm, nicht am Port** — und zwar an genau dieser Datei. Beim
   Windows-Setup ist das `LightOS.exe`. Bei der Installation aus dem Quelltext ist es der
   Python-Interpreter der **Python-Installation** (`python.exe` oder `pythonw.exe`), nicht
   die gleichnamige Datei im Ordner `venv`. Nach einem Python-Update oder mit einer
   zweiten Python-Version zeigt die Regel auf die falsche Datei, und für Windows sind
   `python.exe` und `pythonw.exe` zwei verschiedene Programme.
2. **Sie gilt nur für das Profil**, das beim Klick aktiv war (Schritt 2).
3. **Wer die Abfrage wegklickt, bekommt eine Blockier-Regel.** Windows fragt dann nie
   wieder, und eine Blockier-Regel geht jeder Freigabe vor.

### Empfohlen: Regeln für die Ports

Port-Regeln hängen an keiner Datei und überstehen jedes Update. **Diese Befehle ändern
die Firewall** — führe sie nur auf deinem eigenen Rechner aus, und nur, wenn du die
Funktion wirklich brauchst. PowerShell **als Administrator** öffnen und nur die Zeilen
ausführen, deren Funktion du brauchst:

```powershell
$lightos = @{ Group = 'LightOS'; Direction = 'Inbound'; Action = 'Allow'; Profile = 'Private'; RemoteAddress = 'LocalSubnet' }
New-NetFirewallRule @lightos -DisplayName 'LightOS Web-Remote (TCP 5000)'      -Protocol TCP -LocalPort 5000
New-NetFirewallRule @lightos -DisplayName 'LightOS Art-Net-Eingang (UDP 6454)' -Protocol UDP -LocalPort 6454
New-NetFirewallRule @lightos -DisplayName 'LightOS sACN-Eingang (UDP 5568)'    -Protocol UDP -LocalPort 5568
New-NetFirewallRule @lightos -DisplayName 'LightOS MSC-Eingang (UDP 6004)'     -Protocol UDP -LocalPort 6004
```

- `Profile = 'Private'` — die Regeln gelten nur im Profil „Privat“. Im WLAN einer
  fremden Location bleibt der Rechner damit zu.
- `RemoteAddress = 'LocalSubnet'` — hinein darf nur, wer im selben Netz sitzt.
- `Group = 'LightOS'` — unter diesem Namen findest und entfernst du die Regeln wieder.

Wer erst sehen will, was ein Befehl täte, hängt `-WhatIf` an: Dann legt PowerShell nichts
an und meldet nur, was geschehen würde.

**Anzeigen:**

```powershell
Get-NetFirewallRule -Group 'LightOS' | Format-Table DisplayName, Enabled, Profile, Action
```

Meldet PowerShell, es seien keine Objekte gefunden worden, gibt es keine LightOS-Regeln.

**Wieder entfernen:**

```powershell
Remove-NetFirewallRule -Group 'LightOS'
```

Ohne PowerShell geht es über `wf.msc` (**Windows Defender Firewall mit erweiterter
Sicherheit**): **Eingehende Regeln → Neue Regel...**, Regeltyp **Port**, dann Protokoll
und Port aus der Tabelle in Schritt 1, **Verbindung zulassen**, als Profil nur **Privat**.

## 5. Prüfen, ob es wirkt

Alle Befehle in diesem Schritt **lesen nur** — sie ändern nichts am Rechner.

**Welches Profil, welche Regeln?**

```powershell
Get-NetConnectionProfile | Format-Table InterfaceAlias, NetworkCategory
Get-NetFirewallRule -Group 'LightOS' | Format-Table DisplayName, Enabled, Profile, Action
ipconfig
```

Das Profil aus der ersten Zeile muss zu dem Profil passen, für das die Regeln der
zweiten angelegt sind. Ohne PowerShell zeigt die Eingabeaufforderung das aktive Profil
und seine Grundregel (`Eingehend blockieren,Ausgehend zulassen`):

```
netsh advfirewall show currentprofile
```

**Lauscht LightOS überhaupt?** Funktion in LightOS einschalten, dann in der
Eingabeaufforderung oder PowerShell:

```powershell
netstat -ano | findstr ":5000 :6454 :5568 :6004"
```

Für jede eingeschaltete Funktion erscheint eine Zeile, die letzte Spalte ist die
Prozess-ID:

```
  TCP    0.0.0.0:5000           0.0.0.0:0              ABHÖREN         18040
  UDP    0.0.0.0:6454           *:*                                    18040
```

Steht beim Web-Remote `127.0.0.1:5000` statt `0.0.0.0:5000`, ist in LightOS der Schalter
**LAN-/Handy-Remote** aus — dann erreicht ihn nur dieser Rechner, ganz gleich, was die
Firewall erlaubt.

**Kommt etwas von außen an?** Das zeigt nur ein **zweites Gerät**. Ein Test vom selben
Rechner sagt über die Firewall nichts aus — er gelingt auch dann, wenn von außen alles
zu ist.

- **Web-Remote:** am Handy `http://<PC-IP>:5000/?k=<token>` öffnen (Adresse und Token:
  [Web-Remote](../anleitung_web_remote/ANLEITUNG.md)). Von einem zweiten Windows-Rechner
  aus:

  ```powershell
  Test-NetConnection 192.168.1.10 -Port 5000
  ```

  `TcpTestSucceeded : True` heißt: Der Port ist offen.
- **Art-Net-, sACN- und MSC-Eingang:** UDP lässt sich so nicht testen. Sender einschalten
  und in LightOS nachsehen, ob die Werte ankommen: Sektion **E/A**, Reiter **DMX
  Monitor**, dort das Universum, das im Reiter **DMX Input** unter **Merge in Universe:**
  steht.

## 6. Typische Fehlerbilder

| Was du siehst | Woran es liegt | Abhilfe |
|---|---|---|
| Handy: Die Seite lädt nicht, der Browser läuft in eine Zeitüberschreitung. | Freigabe für TCP 5000 fehlt oder gilt für das andere Profil. Oder das Handy hängt im Gastnetz, das Geräte voneinander trennt. | Schritt 2 und 4. Handy ins selbe Netz wie den Rechner bringen. |
| Am Rechner selbst geht `http://localhost:5000`, vom Handy nicht. | Firewall — oder **LAN-/Handy-Remote** ist aus. | Schritt 5: steht `127.0.0.1:5000` in `netstat`, den Schalter in LightOS einschalten. Sonst Schritt 4. |
| Handy: Antwort „403“. | Kein Netzwerkfehler — der Rechner wurde erreicht, es fehlt das Token. | Den Direkt-Link aus dem Verbindungs-Dialog verwenden ([Web-Remote](../anleitung_web_remote/ANLEITUNG.md)). |
| Art-Net: Der Dialog meldet „Aktiv“, der Node bleibt dunkel. | Rechner und Node liegen in verschiedenen Netzen, oder Art-Net geht über die falsche Karte hinaus. Mit der Firewall hat das nichts zu tun. | Schritt 3, `ping` zum Node, **Netzwerkkarte:** wählen. Ein laufendes VPN trennen. |
| `ipconfig` zeigt `169.254.x.x`. | Im Lichtnetz verteilt niemand Adressen. | Schritt 3: feste Adresse. |
| Art-Net-/sACN-Eingang ist eingeschaltet, es kommt nichts an. | Freigabe für UDP 6454 bzw. 5568 fehlt. Oder der Sender schickt an eine andere Adresse oder ein anderes Universum. | Schritt 4. Am Sender Ziel und Universum prüfen (Art-Net zählt ab 0). |
| Am anderen Ort ging es, hier nicht. | Windows hat das neue Netz als „Öffentlich“ eingestuft, die Regeln gelten für „Privat“. | Schritt 2. |
| Nach einem Python-Update oder einer Neuinstallation aus dem Quelltext kommt nichts mehr herein. | Die von Windows angelegte Regel zeigt auf das alte `python.exe`. | Port-Regeln aus Schritt 4 anlegen. |
| Die Windows-Abfrage kam nie — oder sie wurde weggeklickt. | Es gibt eine Blockier-Regel für das Programm; sie geht jeder Freigabe vor. | Siehe unten. |
| sACN kommt über WLAN nur ruckelnd oder gar nicht an. | Viele WLAN-Router bremsen oder filtern Multicast. | Kabel verwenden — oder am Sender **Unicast** auf die Adresse des Empfängers stellen. |

**Blockier-Regeln finden** (als Administrator):

```powershell
Get-NetFirewallRule -Direction Inbound -Action Block -Enabled True |
    Where-Object DisplayName -match 'python|LightOS' |
    Format-Table DisplayName, Profile
```

Was hier steht, hält LightOS zu. Dieselbe Abfrage mit `| Remove-NetFirewallRule` statt
`| Format-Table …` am Ende entfernt die gefundenen Regeln.

## 7. Wieder aufräumen

- Freigaben entfernen: `Remove-NetFirewallRule -Group 'LightOS'` (Schritt 4).
- Feste Adresse zurücknehmen: im Dialog **IP-Einstellungen bearbeiten** wieder
  **Automatisch (DHCP)** wählen und **Speichern**.
- Netzwerkprofil: unter **Netzwerkprofiltyp** zurück auf **Öffentliches Netzwerk
  (Empfohlen)**.

## Weiterlesen

- [Ausgabe einrichten: ENTTEC, Art-Net, sACN](../anleitung_ausgabe_einrichten/ANLEITUNG.md)
  — der Dialog **Ausgabe konfigurieren**, Monitore und Warnungen.
- [Web-Remote — das Handy als Konsole](../anleitung_web_remote/ANLEITUNG.md) — Token,
  Direkt-Link, Sicherheit.
- [Zwei Universen über zwei Adapter](../anleitung_zwei_universen/ANLEITUNG.md) — ENTTEC
  und Art-Net nebeneinander.

Zurück zur Übersicht: [../ANLEITUNGEN.md](../ANLEITUNGEN.md)
