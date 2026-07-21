# Enttec (USB) und Art-Net gleichzeitig benutzen

> LightOS steuert **jedes Universum mit seinem eigenen Ausgabe-Backend**. Du kannst also
> ein Universum über einen **Enttec-USB-Adapter** und ein anderes über **Art-Net (Netzwerk)**
> ausgeben — **gleichzeitig**. Enttec, Art-Net und sACN lassen sich frei mischen (bis zu 32
> Universen).
>
> Beispiel dieser Anleitung (live verifiziert): **EventPar** (Universe 1) über **Art-Net** an
> einen Node (`192.168.178.99`) + **Hydrabeam 4000** (Universe 3) über **Enttec** auf `COM3`.

## Kurz-Prinzip

Ausgabe-Backend gilt **pro Universum**, nicht global:

| Universum | Geräte darauf | Ausgabe | Ziel |
|---|---|---|---|
| 1 | EventPar (Art-Net-Node) | **Art-Net** | Node-IP `192.168.178.99` (oder Broadcast) |
| 3 | Hydrabeam 4000 (USB-Interface) | **Enttec** | COM-Port `COM3` |

Ein Gerät hängt immer an dem Universum, das über das gewünschte Interface läuft. Also:
**Erst die Geräte auf die richtigen Universen patchen, dann pro Universum das Backend setzen.**

## 1. Geräte auf die passenden Universen patchen

Beim Patchen (Sektion **Patchen**) je Gerät das **Universe** wählen:

- EventPar → **Universe 1** (kommt über Art-Net raus).
- Hydrabeam 4000 → **Universe 3** (kommt über Enttec raus).

Die DMX-Adresse ist pro Universum normal (1–512) — zwei Geräte auf verschiedenen Universen
dürfen dieselbe Adresse haben.

## 2. Ausgabe konfigurieren — beide Backends setzen

**Menü `Ausgabe` → `Konfigurieren…`** öffnet den Dialog *Ausgabe konfigurieren*. Er hat die
Tabs **Enttec Pro USB · Art-Net · sACN (E1.31) · DMX Input · Universen**.

Der eigentliche Dual-Output-Schalter ist der Tab **Universen**. Dort steht pro Universum:
**Name · Output-Typ (Disabled / Enttec / sACN / ArtNet) · Patch (Port/IP) · Ext-Universe**.

Setze:

| # | Name | Output | Patch (Port/IP) |
|---|---|---|---|
| 1 | EventPar (Art-Net) | **ArtNet** | `192.168.178.99` *(Node-IP; oder `255.255.255.255` für Broadcast)* |
| 3 | Hydra (Enttec) | **Enttec** | `COM3` *(dein Enttec-COM-Port)* |

Fehlt ein Universum, mit **`+ Universe hinzufügen`** anlegen; dann Output-Typ und Patch
eintragen. Mit **`Speichern`** übernehmen.

> **Enttec-Port finden:** Der Tab **Enttec Pro USB** listet den erkannten Adapter, z. B.
> `COM3 — USB Serial Port (COM3) [Enttec Pro]`. Diesen Port trägst du im Universen-Tab bei
> „Patch" ein. `Ports aktualisieren` frischt die Liste nach dem Einstecken auf.

Im **Universen**-Tab siehst du dann beide Zeilen nebeneinander — Universe 1 mit Output
`ArtNet` / Patch `192.168.178.99` und Universe 3 mit Output `Enttec` / Patch `COM3`: das
ist „Enttec und Art-Net gleichzeitig".

## 3. Prüfen, dass beide laufen

- **Statusleiste unten links** zeigt den Enttec-Zustand: **`Enttec: COM3 OK`** (grün) = Adapter
  verbunden. Art-Net braucht keinen Verbindungsstatus (verbindungsloses UDP) — es sendet,
  sobald der Output-Typ auf ArtNet steht.
- **Test:** Sektion **Programmer** → beide Geräte auswählen (`Alle`) → im Tab **Intensity** den
  **Master Dimmer** hochziehen und im Tab **Color** eine Farbe wählen. Jetzt leuchten
  **beide** Geräte **gleichzeitig** — der EventPar über Art-Net, der Hydrabeam über Enttec.

## 4. ⚠️ Netzwerk-Falle bei Art-Net (wichtig!)

Art-Net ist Netzwerk-Ausgabe. Dein PC (bzw. der USB-Netzwerk-Adapter, an dem der Node hängt)
**muss eine IP im selben Subnetz wie der Node** haben:

- Node = `192.168.178.99` → der PC braucht z. B. `192.168.178.x` (gleiche `192.168.178`).
- **Häufiger Fehler:** Ein USB-Ethernet-Adapter ohne DHCP bekommt nur eine **APIPA-Adresse**
  (`169.254.x.x`) → dann findet Art-Net den Node **nicht**. Lösung: dem Adapter eine **feste
  IP** im Node-Subnetz geben (z. B. `192.168.178.50`, Maske `255.255.255.0`).
- Prüfen: `ping 192.168.178.99` muss antworten. Alternativ **Broadcast** (`255.255.255.255`)
  im Patch nutzen — dann erreicht Art-Net alle Nodes im lokalen Netz, unabhängig von der
  Node-IP (aber die Subnetz-Regel oben gilt trotzdem).

## Merksätze

- **Ausgabe-Typ ist pro Universum** — Enttec, Art-Net und sACN beliebig mischen.
- **Gerät → Universum → Backend:** erst patchen (Universe), dann das Universum auf das
  richtige Interface stellen.
- **Enttec:** COM-Port aus dem Enttec-Tab; Status „`… OK`" in der Statusleiste = verbunden.
- **Art-Net:** Node-IP oder Broadcast, und der PC muss **im selben Subnetz** liegen (sonst
  stumm trotz „konfiguriert").
