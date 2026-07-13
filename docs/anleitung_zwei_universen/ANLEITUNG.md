# Anleitung: Zwei Universen über zwei verschiedene Ausgabe-Adapter

> Ziel: **Universe 1** geht über einen **Enttec USB Pro** (DMX über USB/COM-Port),
> **Universe 2** parallel über **Art-Net** (DMX über Netzwerk). LightOS kann pro
> Universe einen **eigenen** Ausgabe-Adapter fahren — so mischst du klassisches
> USB-DMX und Netzwerk-Nodes in einer Show. Diese Anleitung führt durch
> (1) Patchen auf U1/U2, (2) Ausgabe-Konfig pro Universum, (3) Verifikation im
> Output-Monitor.

---

## Überblick

| Universe | Adapter | „Patch" (Ziel) | Wofür |
|---|---|---|---|
| **U1** | Enttec USB Pro | COM-Port (z. B. `COM3`) | Geräte direkt am USB-Interface |
| **U2** | Art-Net | Ziel-IP / Broadcast (z. B. `192.168.0.50` oder `255.255.255.255`) | Netzwerk-Nodes, Dimmer, weitere Interfaces |

Beide Universen laufen **gleichzeitig**. LightOS hält pro Universe genau **einen**
Adapter — ein Typwechsel schließt den alten Adapter sauber, bevor der neue öffnet.

---

## 1. Fixtures auf U1 und U2 patchen

Sektion **Patchen** → Tab **Patch**. Mit **+ Gerät hinzufügen** öffnet sich der
Dialog *Gerät hinzufügen*: links das Profil wählen, rechts unter *Patch-Optionen*
den **Modus** (Kanal-Layout), das Feld **Universe:** und die **DMX-Adresse:**
setzen, dann **Hinzufügen**.

Das **Universe:**-Feld entscheidet, auf welchem Universe das Gerät landet:

- Geräte, die am Enttec hängen sollen → **Universe: 1**.
- Geräte, die über Art-Net gehen sollen → **Universe: 2**.

Mehrere gleiche Geräte auf einmal: Feld **Anzahl:** hochzählen und den
**Adress-Offset:** setzen (0 = dicht hintereinander). Reicht ein Universe nicht
mehr aus (über Kanal 512), rollt LightOS automatisch ins nächste — willst du eine
saubere Trennung zwischen U1 und U2, patch die beiden Blöcke also getrennt und
prüfe das **Universe:**-Feld pro Block.

Bereits gepatchte Geräte umziehen: **Doppelklick** auf die Zeile öffnet *Gerät
bearbeiten*, dort lässt sich **Universe** (und Adresse) ändern. In der Tabelle
zeigt die Spalte **Univ.** je Zeile, auf welchem Universe ein Gerät liegt — so
kontrollierst du die Aufteilung auf einen Blick. Adresskonflikte werden **je
Universe** geprüft: betroffene Zeilen färben sich rot und die FID bekommt ein
**⚠** (U1-Adresse 1 und U2-Adresse 1 kollidieren also **nicht** — es sind zwei
getrennte Adressräume).

> Details zum Patchen und zu Fixture-Gruppen:
> [Patchen & Gruppen](../anleitung_patch_gruppen/ANLEITUNG_PATCH_GRUPPEN.md).

---

## 2. Ausgabe pro Universum konfigurieren

Menü **Ausgabe → Konfigurieren…** öffnet den Dialog **„Ausgabe konfigurieren"**
mit mehreren Tabs. Es gibt zwei Wege — der **Universe-Manager** (empfohlen) setzt
beide Universen in einer Tabelle, die Einzel-Tabs richten je Universe live eine
Verbindung ein.

### Weg A (empfohlen): Tab „Universen" — beide auf einmal

Tab **Universen**. Die Tabelle hat die Spalten **#** · **Name** · **Output** ·
**Patch (Port/IP)**. Pro Zeile ein Universe:

1. Zeile 1 → **#** `1`, **Name** z. B. *Bühne*, **Output** = `Enttec`,
   **Patch** = dein COM-Port, z. B. `COM3`.
2. **+ Universe hinzufügen** → neue Zeile. **#** `2`, **Name** z. B. *Art-Net*,
   **Output** = `ArtNet`, **Patch** = Ziel-IP oder Broadcast, z. B.
   `192.168.0.50` (leer = Standard-Broadcast `255.255.255.255`).
3. **Speichern**. LightOS schreibt die Konfiguration nach `data/universes.json`
   **und** wendet sie **sofort ohne Neustart** an (Bestätigung mit dem Pfad).

Die **Output**-Spalte ist ein Auswahlfeld mit `Disabled / Enttec / sACN /
ArtNet`. Bedeutung der **Patch**-Spalte je Typ:

- **Enttec** → COM-Port (z. B. `COM3`).
- **ArtNet** → Ziel-IP oder Broadcast (leer = `255.255.255.255`).
- **sACN** → Unicast-IP (leer = Multicast).

Weil die Konfiguration in `data/universes.json` persistiert wird, richtet LightOS
beide Adapter beim **nächsten Start automatisch** wieder ein.

### Weg B: Einzel-Tabs (live verbinden)

Alternativ pro Universe direkt eine Verbindung aufbauen:

- **Tab „Enttec Pro USB":** **COM-Port** wählen (Knopf **Ports aktualisieren**,
  falls das Interface neu angesteckt wurde; ein erkanntes Enttec ist mit
  `[Enttec Pro]` markiert), Feld **Universe:** auf `1` stellen, **Verbinden**.
  Der Status zeigt `Verbunden: COM… -> Universe 1 (gespeichert)`.
- **Tab „Art-Net":** **Art-Net aktivieren** anhaken, Feld **Universe:** auf `2`
  stellen, **Ziel-IP / Broadcast** eintragen (z. B. `192.168.0.50`), bei Bedarf
  das **Art-Net Startuniversum** (die *externe* Art-Net-Universe-Nummer am Node)
  setzen, dann **Übernehmen**. Status: `Aktiv → … · Universe 2 (gespeichert)`.

> **Wichtig — kein „alle Universen"-Effekt mehr:** Die **Übernehmen**/**Verbinden**-
> Knöpfe wirken **nur** auf das Universe, das im **„Universe:"**-Feld desselben
> Tabs steht. Stelle das Feld also **vor** jedem Klick bewusst ein (Enttec-Tab
> auf `1`, Art-Net-Tab auf `2`). So überschreibt die Art-Net-Zuweisung nicht die
> Enttec-Zuweisung — jede Zeile in `data/universes.json` bleibt für sich erhalten.

Beide Wege schreiben in dieselbe `data/universes.json`; du kannst sie mischen.

> Netzwerk-/Protokoll-Details zu Art-Net (Port 6454, PortAddress, Broadcast):
> [ARTNET.md](../ARTNET.md). Grundlagen DMX/Universe/Adressraum:
> [DMX_PROTOCOL.md](../DMX_PROTOCOL.md).

---

## 3. Verifikation im Output-Monitor

Sektion **E/A** (Eingabe / Ausgabe) → Tab **Output**. Der **Output-Monitor** zeigt
die 512 DMX-Kanäle eines Universums als Live-Kacheln (Wert `0–255`, aktive Kanäle
werden blau/hell). Oben links steht das Feld **Universe:** (Bereich 1–32).

So prüfst du beide Ausgänge:

1. **Universe:** auf `1` stellen → an den Kanälen deiner U1-Geräte (Enttec) müssen
   Werte erscheinen, sobald du Fader/Effekte/Programmer bewegst. Kommen keine
   Werte an, ist entweder nichts auf U1 gepatcht oder der Enttec-Port stimmt nicht.
2. **Universe:** auf `2` stellen → an den Kanälen deiner U2-Geräte (Art-Net)
   müssen Werte erscheinen. So siehst du, dass der Art-Net-Adapter das getrennte
   Universe wirklich bespielt.
3. Zum Gegencheck einen Master/Blackout ziehen: die Werte müssen in **beiden**
   Universen reagieren.

Zeigt ein Universe im Monitor Werte, aber am realen Gerät kommt nichts an, liegt
es an der **Ausgabe-Konfig** (Tab „Universen": falscher COM-Port / falsche
Ziel-IP), nicht am Patch — der Monitor spiegelt den **berechneten** Universe-Inhalt
vor dem Adapter.

> Ergänzend: Der Tab **DMX Monitor** daneben zeigt dieselben Daten in einer
> kompakteren Listenform.

---

## Kurz-Checkliste

- [ ] Geräte im **Patch** aufgeteilt: U1-Block auf **Universe 1**, U2-Block auf **Universe 2** (Spalte *Univ.* kontrollieren).
- [ ] **Ausgabe → Konfigurieren… → Universen:** Zeile 1 = `Enttec` / COM-Port, Zeile 2 = `ArtNet` / Ziel-IP → **Speichern**.
- [ ] (Alternativ) Einzel-Tabs: **Universe:**-Feld je Tab bewusst auf 1 bzw. 2 gestellt, dann **Verbinden** / **Übernehmen**.
- [ ] **E/A → Output:** Universe **1** und **2** durchgeschaltet, beide zeigen Live-Werte.
