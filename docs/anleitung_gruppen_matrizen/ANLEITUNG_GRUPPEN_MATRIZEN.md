# Anleitung: Gruppen und Matrizen anlegen (Mehrkopf-Geräte & Panels)

> **Worum es geht:** Ein LED-Balken, ein Spider oder eine Beam-Bar ist für LightOS
> nicht *eine* Lampe, sondern **N einzeln färbbare Köpfe**. Diese Anleitung geht den
> kompletten Weg: Gerät patchen → automatische Kopf-Gruppe → als Raster legen → zu
> **einer** Zelle zusammenfassen → neben andere Geräte setzen → wieder aufteilen.
>
> **Das alles geht heute schon.** Es ist nur schwer zu finden: die Aktionen stecken im
> **Rechtsklick-Menü** des Rasters und in einem **Knopf-Menü** links neben dem Raster.
> Beide Wege stehen hier — sie führen zum selben Ergebnis.

**Lesehilfe:** Beschriftungen, die du wirklich anklickst, stehen in deutschen
Anführungszeichen — wörtlich so, wie sie in der Oberfläche stehen. Enthält ein Menüpunkt
den Gerätenamen, steht hier nur der feste Teil. Sektions- und Tab-Namen stehen **fett**.
*(Ein Test misst das nach: jede so zitierte Beschriftung muss es in der laufenden
Oberfläche wirklich geben.)*

> 🖼 **Bilder fehlen noch.** Screenshots und das GIF des Ablaufs sind bewusst **offen**
> (Backlog `DOC-13`): sie sollen am realen Aufbau am laufenden Programm entstehen, nicht
> an einer erfundenen Show. Der Text unten ist ohne Bilder vollständig benutzbar; die
> Raster sind als Textbilder dargestellt.

---

## Der Beispielaufbau

| Gerät | Modus | Was LightOS daraus macht |
|---|---|---|
| **LED-Balken ZQ06121** | `154-Kanal 48 Zonen RGB + 8x Weiss` | **48 einzeln färbbare Zonen** (= Köpfe) + 8 Warmweiß-Segmente |
| **2 × PAR** (z. B. `Stage Light ZQ01424`) | `8-Kanal RGBW` | je **ein** Kopf — eine Rasterzelle |

Der Balken hängt physisch als **12 Spalten × 4 Reihen**; die acht Warmweiß-Segmente
laufen mittig zwischen Reihe 2 und 3 durch.

**Das Ziel:** PAR / Balken / PAR nebeneinander in **einer** Gruppe — der Balken als
**ein** Element — und auf Knopfdruck wieder zerlegt in seine 48 Zonen.

---

## 1. Patchen — die Kopf-Gruppe entsteht von selbst

Gepatcht wird wie immer: Sektion **Patchen** → Tab **Patch** → **+ Gerät hinzufügen**
(Profil, Universe, DMX-Adresse). Der ausführliche Weg steht in
[Patchen & Fixture-Gruppen](../anleitung_patch_gruppen/ANLEITUNG_PATCH_GRUPPEN.md).

Sobald du ein Gerät mit **mehreren** färbbaren Köpfen patchst, legt LightOS automatisch
eine Gruppe an (beim Öffnen einer gespeicherten Show nicht — dort kommen die Gruppen aus
der Show-Datei):

* **Name:** *Geräte-Label* + ` · Köpfe` — im Beispiel `LED-Balken · Köpfe`
* **Ordner:** `Multi-Head`
* **Raster:** **1 Zeile × 48 Zellen** — jede Zelle ist **ein Kopf**, nicht das Gerät.

```
Automatische Kopf-Gruppe (1 × 48):
┌────┬────┬────┬─────────────────────────────┬────┐
│ K1 │ K2 │ K3 │  …                          │K48 │
└────┴────┴────┴─────────────────────────────┴────┘
```

★ **Warum das für ein Panel noch nicht reicht:** Matrix-Effekte lesen das Raster als
*Fläche*. Ein 1×48-Streifen ist eine Linie — jeder Flächeneffekt läuft darauf als
Lauflicht in einer Reihe. Für den Balken willst du 12 × 4. Genau das machen die
Abschnitte 3 und 4.

### Ausnahme: Pixel-Köpfe (LED-Ring) bekommen gleich ein Ring-Raster

Ein **Pixel-Moving-Head** — ein Kopf, dessen Lichtaustritt in einzeln ansteuerbare
Pixel zerlegt ist (z. B. *Robe Robin Spiider* im Pixel-Modus) — zählt seine Pixel nicht
in Zeilen, sondern in **Ringen** um die Mitte. Eine 1×N-Reihe wäre dort keine Hilfe: ein
Lauflicht darüber liefe am Ring vorbei. Deshalb legt LightOS für solche Geräte gleich
das richtige Raster an:

* **Name:** *Geräte-Label* + ` · Pixel` (nicht ` · Köpfe` — in den Zellen stehen Pixel)
* **Raster:** **eine Zeile je Ring**, **eine Spalte je Winkelposition**

```
Ring-Raster eines 19-Pixel-Kopfes (3 × 12):
        Spalte →   0    1    2    3    4    5    6    7    8    9   10   11
Zeile 0 (Mitte)   P1    ·    ·    ·    ·    ·    ·    ·    ·    ·    ·    ·
Zeile 1 (Ring 2)   ·   P2    ·   P3    ·   P4    ·   P5    ·   P6    ·   P7
Zeile 2 (Ring 3)  P8   P9  P10  P11  P12  P13  P14  P15  P16  P17  P18  P19
```

Damit ist ein **waagerechtes** Lauflicht eine Drehung um den Kopf (alle Ringe drehen
gleichzeitig mit), ein **senkrechtes** eine Welle von der Mitte nach außen.

★ **Die Grundfarbe steht bewusst nicht im Raster.** Bank 0 eines Pixel-Kopfes ist die
Farbe des *ganzen* Geräts (Linse, Kegel, Bodenfleck) — als Matrix-Zelle würde jeder
Effekt sie mitziehen und den Ring, den er gerade zeichnet, sofort überstrahlen. In der
Geräteliste des **Programmers** trägt sie deshalb ihren Funktionsnamen statt einer
Kopfnummer, und die Zeilen darunter ihre **Pixelnummer** aus dem Geräte-Handbuch — sonst
griffe man beim ersten Pixel versehentlich ins ganze Gerät.

### Wie ein Segment überall heißt

Ein Segment hat **einen** Namen, und den zeigt jede Fläche, die es benennt — die
Geräteliste und die Kopfzeile des Programmers, die Reglerbeschriftung, die Rasterzelle
im Gruppen-Editor, der Zell-Tooltip der Matrix-Vorschau, die EFX-Zielliste, das
Fan-Werkzeug und die Statuszeile der Command-Line.

| | gewöhnliches Mehrkopf-Gerät | Pixel-Kopf |
|---|---|---|
| Bank 0 | `Kopf 1` / kurz `K1` | `Grundfarbe` / kurz `GR` |
| Bank 3 | `Kopf 4` / kurz `K4` | `Pixel 3` / kurz `P3` |

Die **Kurzform** ist dieselbe Beschriftung, nur abgekürzt (Anfangsbuchstabe + Nummer);
sie steht dort, wo nur wenige Zeichen Platz haben. Die Rasterzelle im Gruppen-Editor ist
die engste dieser Flächen — **fährst du mit der Maus darüber, nennt der Tooltip den
vollen Namen** (`Spiider · Pixel 3`).

Die Kurzform ist keine Erfindung dieser Ansicht: die Gerätebibliothek nennt die
Pixelkanäle des Spiiders selbst `P3 Rot`, `P3 Grün`, `P3 Blau` und die des ganzen Geräts
`Grundfarbe Rot`. Wer im Programmer `Pixel 3` wählt, findet also im Kanalnamen dasselbe
`P3` wieder.

> **Ein Regler über gemischte Geräte** — etwa ein Pixel-Kopf und eine Mover-Bar,
> beide auf Kopf 4 eingeschränkt — trägt weiter die Kopfnummer (`K4`). Er benennt
> dort kein einzelnes Segment mehr, sondern den Kopf-Index, den beide gemeinsam
> haben; `Pixel 3` wäre für die Mover-Bar schlicht falsch.

### Was im Dialog *Gerät bearbeiten* dazugehört

Doppelklick auf die Patch-Zeile öffnet den Dialog. Für Mehrkopf-Geräte gibt es dort:

* **„Mehrkopf-Programmierung:"** — „Automatisch (beim Patchen anlegen)",
  „Köpfe einzeln — Kopf-Matrix (48 Köpfe)" oder „Als EINE Lampe (keine Kopf-Matrix)".
  Die letzte Einstellung verhindert nur, dass beim Patchen automatisch eine Kopf-Gruppe
  entsteht. Keine der drei **löscht** je eine vorhandene Gruppe — eine von Hand
  angeordnete oder zusammengelegte Matrix bleibt also unangetastet.
* **„Kopf-Matrix-Gruppe:"** — Status („vorhanden" / über eine andere Gruppe abgedeckt /
  fehlt) und der Knopf **„Wiederherstellen"**. Der hilft, wenn die Auto-Gruppe einmal
  gelöscht wurde: er legt sie neu an, ohne das Gerät neu patchen zu müssen, und erzeugt
  kein Duplikat, wenn sie schon existiert.

Bei **Panels** (Gerätetyp Matrix) kommen drei Angaben zur Geometrie dazu:

* **„Pixel-Reihenfolge:"** — „Zeilenweise (links→rechts)",
  „Schlangenlinien (jede 2. Zeile rückwärts)" oder „Gespiegelt (rechts→links)".
  Das ist eine Aussage über das **Gerät** (wie es ab Werk zählt).
* **„Montage-Drehung:"** — 0° / 90° / 180° / 270°, und
  **„Waagerecht gespiegelt montiert"**. Das ist eine Aussage über die **Montage**.

★ **Ehrlich dazu, damit du nicht darauf wartest:** Diese drei Angaben wirken **nicht**
auf die automatische Kopf-Gruppe — die entsteht immer als 1×N, egal was hier steht. Sie
wirken beim Aufteilen **„als Block…"** (Abschnitt 3) und in der 3D-Vorschau. Wer sie
umstellt und nur die Auto-Gruppe ansieht, sieht deshalb keinen Unterschied.

---

## 2. Der Gruppen-Editor in 60 Sekunden

Sektion **Patchen** → Tab **Fixture-Gruppen**.

* **Links oben:** die Auswahl „Gruppe:" und die Knöpfe „+ Neu", „Umbenennen",
  „Bearbeiten…", „Löschen", „Speichern", „Ordner…" sowie
  **„⧉ Matrizen zusammenlegen…"** (Abschnitt 6).
* **Links unten:** der Gerätebaum „Fixtures (drag auf Raster):" und darunter
  **„Köpfe einzeln → Raster ▾"** (Abschnitt 4), „Alle → Raster",
  „Fixtures neu laden".
* **Rechts:** das Raster. Darüber steht
  „Raster (Drag&Drop für Platzierung, Rechtsklick zum Entfernen):" — die Beschriftung
  stammt aus der Zeit vor dem Kontextmenü; Rechtsklick öffnet heute das Menü aus
  Abschnitt 3.
* **Oben rechts:** das schwebende Panel „Rastergröße" mit „Spalten:" und „Zeilen:"
  (verschiebbar, zuklappbar über ▾).

> ⚠️ **Speichern nicht vergessen.** Platzierungen und Rastergröße stehen zunächst nur im
> Editor. Erst „Speichern" schreibt sie in die Gruppe.

---

## 3. Weg A — Rechtsklick im Raster (der kurze Weg)

1. Gruppe wählen (oder „+ Neu"). Das Gerät aus dem Baum **auf eine Rasterzelle ziehen** —
   so steht es als **ganzes Gerät** in einer Zelle.
2. **Rechtsklick auf genau diese Zelle.** Für ein Mehrkopf-Gerät bietet das Menü:
   * „Zelle entfernen"
   * **„aufteilen (48 Elemente)"** mit den Unterpunkten „als Zeile", „als Spalte",
     **„als Block…"**
   * „Alle Zellen von" *…Gerätename…* „entfernen"
3. **„als Block…"** öffnet den Dialog „Als Block aufteilen" mit der Frage
   „Spalten (bei 48 Elementen):". Vorbelegt ist ein **Teiler** der Elementzahl nahe der
   Quadratwurzel — bei 48 also 6. Für den Balken **12** eintragen.

Ergebnis: **12 Spalten × 4 Zeilen**.

```
Nach „als Block…" mit 12 Spalten (K1 = Kopf 1):
┌────┬────┬────┬────┬────┬────┬────┬────┬────┬────┬────┬────┐
│ K1 │ K2 │ K3 │ K4 │ K5 │ K6 │ K7 │ K8 │ K9 │K10 │K11 │K12 │
├────┼────┼────┼────┼────┼────┼────┼────┼────┼────┼────┼────┤
│K13 │K14 │K15 │K16 │K17 │K18 │K19 │K20 │K21 │K22 │K23 │K24 │
├────┼────┼────┼────┼────┼────┼────┼────┼────┼────┼────┼────┤
│K25 │K26 │K27 │K28 │K29 │K30 │K31 │K32 │K33 │K34 │K35 │K36 │
├────┼────┼────┼────┼────┼────┼────┼────┼────┼────┼────┼────┤
│K37 │K38 │K39 │K40 │K41 │K42 │K43 │K44 │K45 │K46 │K47 │K48 │
└────┴────┴────┴────┴────┴────┴────┴────┴────┴────┴────┴────┘
```

Dabei gilt:

* Das **Raster wächst selbst** auf die nötige Größe — es wird nie kleiner gemacht.
* Hier — und nur hier — wirken **„Pixel-Reihenfolge:"** und **„Montage-Drehung:"** aus
  Abschnitt 1: ein Panel, das ab Werk in Schlangenlinien zählt oder hochkant hängt,
  landet ohne Handarbeit richtig im Raster.
* Eine Zelle, in der schon ein **anderes** Gerät steht, wird **nicht** überschrieben —
  der betroffene Kopf weicht auf die nächste freie Zelle aus. Ist das Raster voll,
  bleibt der Rest ungesetzt und LightOS sagt, wie viele Elemente untergekommen sind.
* Dasselbe Gerät steht **nie doppelt** im Raster: eine frühere Platzierung wird
  freigegeben, nicht verdoppelt.

**Zwei Dinge kann nur dieser Weg:** Er nimmt das Zielgerät aus der Zelle **unter dem
Mauszeiger** (kein Suchen im Baum), und **„als Block…"** — also das Rechteck — gibt es
ausschließlich hier.

---

## 4. Weg B — die Knöpfe links (über die Baum-Auswahl)

Links im Baum das Gerät **anklicken**, dann **„Köpfe einzeln → Raster ▾"**:

* „als Zeile (waagerecht)" — ein waagerechter Streifen
* „als Spalte (hochkant)" — ein senkrechter Streifen
* **„Köpfe zusammenfassen (eine Zelle)"** — der Rückweg (siehe Abschnitt 5)

Auch hier wächst das Raster vorher so weit, dass der Streifen in der gewünschten
Richtung überhaupt Platz hat — sonst würde die Ausweichregel die Köpfe umbiegen und die
Orientierung wäre genau falsch herum.

> **Fallstrick:** Die **blaue Markierung** im Baum zeigt nur, welche Geräte schon in
> dieser Gruppe liegen — sie ist **keine Auswahl**. Wenn LightOS nach dem Gerät fragt,
> obwohl doch etwas markiert aussieht, ist genau das der Grund: einmal auf die
> Gerätezeile klicken.

---

## 5. Panel als EIN Element neben die PARs — und wieder auseinander

**Zusammenfassen:**

* Rechtsklick auf **eine der Kopf-Zellen** → „zu einer Zelle zusammenfassen"
* oder links über „Köpfe einzeln → Raster ▾" → „Köpfe zusammenfassen (eine Zelle)"

Die 48 Kopf-Zellen werden durch **eine** Zelle ersetzt, und zwar an der Stelle des
**ersten** bisherigen Kopfes (Raster-Reihenfolge: Zeile, dann Spalte). Alle **anderen**
Geräte im Raster bleiben unangetastet.

**Danebenlegen:** erst „Spalten:" auf 3 und „Zeilen:" auf 1 stellen, dann die beiden PAR
aus dem Baum links und rechts neben die Balken-Zelle ziehen, dann „Speichern".

> ⚠️ **Erst die Rastergröße, dann die Geräte** — und zwar aus einem handfesten Grund:
> **Verkleinern entfernt Zellen außerhalb des neuen Rasters** — ohne Nachfrage. Wer erst
> auf Spalte 8 legt und danach auf 3 Spalten verkleinert, hat das Gerät aus der Gruppe
> geworfen, ohne es zu merken.

```
PAR / Balken / PAR — der Balken als EIN Element:
┌──────────┬──────────┬──────────┐
│ PAR links│ LED-Balk.│ PAR rechts│
└──────────┴──────────┴──────────┘
```

**Wieder auseinander:** Rechtsklick auf die Balken-Zelle → „aufteilen (48 Elemente)" →
„als Block…". Der Rundweg ist verlustfrei in beide Richtungen, und die PAR daneben
überleben ihn.

---

## 6. Mehrere Matrizen zu einer zusammenlegen

Der Knopf **„⧉ Matrizen zusammenlegen…"** öffnet den Dialog „Matrizen zusammenlegen"
mit der Liste „Gruppen wählen (von oben nach unten gestapelt):".

* Mindestens **zwei** Gruppen auswählen.
* Gestapelt wird in **Listenreihenfolge** (nicht in der Reihenfolge deiner Klicks):
  Raster untereinander, Spaltenzahl auf die breiteste Gruppe.
* Die Zellen behalten ihre Bedeutung — Kopf-Zellen bleiben **pro Kopf** ansprechbar.
* Ergebnis ist eine **neue** Gruppe im Ordner `Matrizen`. Die **Quellgruppen bleiben
  erhalten** (nichts wird ersetzt oder gelöscht).

Typischer Fall: zwei Mehrkopf-Geräte mit je 1×4 Köpfen ergeben eine 4×2-Matrix, über die
ein Effekt dann als Fläche läuft.

> **Grenze, damit du sie nicht erst am Rig entdeckst:** Für eine *zusammengelegte* Gruppe
> gibt es kein Zurück auf die Einzelgruppen — beim Zusammenlegen wird nicht mitgeschrieben,
> woher welche Zeile stammt. Rückrechenbar ist nur das Aufteilen/Zusammenfassen **pro
> Gerät** aus den Abschnitten 3–5. Die Quellgruppen stehen aber noch da; im Zweifel
> arbeitest du weiter mit ihnen.

---

## 7. Fallstricke in einem Absatz

* **„Speichern"** — ohne den Klick ist die schönste Anordnung nur Bildschirminhalt.
* **Rechtsklick löscht nicht mehr sofort.** Früher verschwand die Zelle beim Rechtsklick
  ohne Nachfrage; heute öffnet er das Menü, „Zelle entfernen" ist der erste Eintrag.
* **Volles Raster zerstört nichts** — es bleibt nur der Rest ungesetzt. Erst „Spalten:" /
  „Zeilen:" erhöhen, dann erneut aufteilen.
* **Die Warmweiß-Segmente des Balkens sind keine eigenen Rasterzellen.** Sie hängen
  intern an den Köpfen 1–8, decken physisch aber je anderthalb Spalten ab und sitzen
  zwischen den Reihen. Ein Matrix-Effekt, der **auch Weiß** ansteuert, würde deshalb acht
  willkürliche Zonen weiß färben. Sauber ist: Farbeffekte über die 48 Zonen laufen
  lassen und Weiß getrennt über Szenen setzen.
* **Ein Gerät, das nur kopfweise im Raster steht**, gilt trotzdem als Mitglied der
  Gruppe — „Alle → Raster" legt es kein zweites Mal als ganzes Gerät ab.

---

## 8. Was heute (noch) nicht geht

* **Eine ganze Gruppe als ein Element in einer anderen Gruppe.** Das Zusammenfassen geht
  **pro Gerät**, nicht pro Gruppe. Solange das Panel *ein* gepatchtes Gerät ist — also im
  Beispielaufbau — reicht das vollständig aus; echte Gruppe-in-Gruppe steht als `FM-20`
  im Backlog.
* **Die Spaltenzahl beim Blockaufteilen kommt von Hand.** LightOS kennt die physische
  Anordnung des Panels nicht (12 × 4 steht nirgends), deshalb ist die Vorbelegung nur ein
  Teiler nahe der Quadratwurzel. Backlog: `FM-21`, `VIZ-50`.
* **Screenshots und GIF dieser Anleitung** — siehe Kasten ganz oben (`DOC-13`).

---

**Kurz:** Gerät patchen → LightOS legt *Label* ` · Köpfe` als 1×N an → Tab
**Fixture-Gruppen** → Gerät als **eine** Zelle ins Raster ziehen → **Rechtsklick** →
„aufteilen (48 Elemente)" → „als Block…" → 12 Spalten → **12 × 4** → „Speichern".
Zurück per Rechtsklick → „zu einer Zelle zusammenfassen". Beides geht auch links über
„Köpfe einzeln → Raster ▾" (dort ohne Block).

→ Weiter mit: [Farb-Matrix](../anleitung_farbmatrix/ANLEITUNG_FARBMATRIX.md) ·
[Matrix-Effekte](../anleitung_matrix_effekte/ANLEITUNG_MATRIX_EFFEKTE.md) ·
[Patchen & Fixture-Gruppen](../anleitung_patch_gruppen/ANLEITUNG_PATCH_GRUPPEN.md)
