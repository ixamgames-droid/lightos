# LightOS – Laser bedienen

So steuerst du einen Laser in LightOS: Muster wählen, als abrufbares Muster
speichern und auf der Virtuellen Konsole auf einen Knopf legen. Grundlagen
(Patchen, Gruppen, Programmer) stehen in [ANLEITUNG.md](../ANLEITUNG.md).

> Stand 2026‑07. Die Oberfläche ist deutsch; der Laser-Tab erscheint im
> **Programmer**, sobald ein Laser-Gerät ausgewählt ist.

---

## 0. Zwei Arten von Lasern — was deiner kann

LightOS unterscheidet ehrlich, was ein Laser wirklich ausgeben kann. Woran du den
Typ erkennst: Nur beim **Netzwerk-Laser** erscheinen im Laser-Tab der Bereich
**„Laser-Ausgabe (Netzwerk)"** (Scharf/Unscharf + NOT-AUS) und der Knopf
**„✏️ Zeichnen…"**. Öffnest du damit das **Zeichen-Studio**, zeigt dir dort ein
ehrliches **Fähigkeits-Banner**, ob deine Zeichnung 1:1 ausgegeben wird (grün) oder
auf diesem Gerät nur als Vorlage/Näherung dient (bernstein):

- **DMX-Muster-Laser** (z. B. **Ehaho L2600 „3D Partylight"**): gibt nur seine
  **eingebauten Werksmuster** aus. Du wählst Muster über DMX-Werte an — eine
  frei gemalte Figur kann er **nicht** darstellen. Für dieses Gerät ist der
  ganze Abschnitt **1–5** gedacht.
- **Netzwerk-Laser** (Ether Dream / IDN / ILDA): gibt **exakt gemalte Figuren**
  aus. Für dieses Gerät gibt es zusätzlich das **Zeichen-Studio** (Abschnitt 7).

> Der L2600 hat **nur DMX** (kein ILDA/SD/USB). Deshalb dreht sich seine
> Bedienung um die Werksmuster, nicht um eigene Zeichnungen.

---

## 1. Patchen

**Patch → „+ Gerät hinzufügen"** → Hersteller **Ehaho**, Gerät
**L2600 3D Animation RGB Laser**, Modus **34-Kanal (Professional DMX)**. Die
Adresse schlägt LightOS automatisch vor. (Es gibt auch einen 6-Kanal-Modus für
einfache Bedienung.)

---

## 2. Laser-Tab öffnen

Wechsle in den **Programmer** und **wähle den Laser** in der Geräteliste. Es
erscheint der Tab **„Laser"**. Er ist nach Bedeutung gegliedert statt roher
DMX-Kanäle:

- **Betriebsart** (Kacheln)
- **Mustergruppe** und **Muster** (Bank + Musterauswahl)
- **Farbe**, **Bewegung & Geschwindigkeit**, **Zeichnen**
- einklappbare **„Weitere Kanäle"** für den Rest

Neben jedem Regler steht der **Klartext des Wertebereichs** — z. B. zeigt das
Muster-Farbfeld bei Wert 40 automatisch „40–47 Blau", die Musterbank
„0–223 Animations-Bänke 1–14". So musst du keine DMX-Tabelle neben der Konsole
liegen haben.

---

## 3. Betriebsart wählen

Die Kacheln unter **„Betriebsart"** entsprechen den Grund-Betriebsarten des
Geräts (**Aus · Auto-Programm · Sound-Modus · Muster-Modus**). Für die manuelle
Steuerung die Kachel **„Muster-Modus (DMX-Steuerung)"** wählen — nur dann wirken
Bank/Muster/Farbe-Regler.

---

## 4. Ein Muster einstellen

1. **Mustergruppe** (Bank) wählen — grobe Vorauswahl der Animations-Bank.
2. **Muster** (Musterauswahl) — das konkrete Werksmuster in der Bank
   (1 Wert = 1 Muster).
3. **Farbe** und **Bewegung & Geschwindigkeit** nach Geschmack.

> Der **Geschwindigkeits-/Rotations-Regler** hält den Laser im Dreh-Modus; über
> die Virtuelle Konsole lässt sich genau darauf ein Tempo-Fader legen
> (Abschnitt 6).

---

## 5. Muster als abrufbares Muster speichern

Damit du ein schönes Muster später mit **einem Klick** wiederbekommst:

- **„💾 Muster speichern…"** (Box **„Muster-Paletten"**) legt die aktuellen
  Laser-Werte der Auswahl als **benanntes Muster** ab. Es erscheint als Kachel
  in „Muster-Paletten" und lässt sich per Klick wieder auf den Laser anwenden.

### 5b. Werksmuster-Bibliothek mit eigenen Fotos (nur DMX-Muster-Laser)

Die Werksmuster des L2600 sind herstellerseitig **unbenannt und ohne
Vorschau**. Deshalb baust du dir in der Box **„Werksmuster (Gerät)"** deine
eigene Vorschau-Bibliothek:

1. Am Gerät (oder über die Regler) Bank + Muster einstellen.
2. **„➕ Muster merken…"** → **Name** vergeben.
3. Der Foto-Dialog fragt nach einem **Foto vom echten Laser-Output** (optional —
   „Abbrechen" merkt das Muster ohne Bild). Mach einfach ein Handyfoto vom
   Muster an der Wand und wähle es aus.
4. Es erscheint eine **Kachel**: mit Foto als Vorschau, sonst mit der
   Bank/Muster-Nummer („B32/M7").

**Kachel anklicken** ruft das Muster ab (schreibt Bank + Muster in den
Programmer). **Rechtsklick** auf eine Kachel löscht den Slot. Die Bibliothek
wird mit der Show gespeichert.

---

## 6. Auf die Virtuelle Konsole legen (Knopf + Tempo)

So bedienst du den Laser im Live-Betrieb ohne den Programmer:

1. **Virtual Console → Bearbeiten-Modus.** Element per **Rechtsklick auf die
   Fläche → „Hinzufügen"** (oder Toolbar) anlegen.
2. **Muster-Knopf:** einen **Button** anlegen, in seinen Einstellungen die
   Aktion **„Laser-Muster abrufen"** wählen und die zuvor gespeicherte
   **Muster-Palette** (Abschnitt 5) zuordnen. Ein Druck ruft das Muster ab.
3. **Tempo-Fader:** einen **Fader** anlegen, Modus **„Programmer-Attribut"**,
   **Attribut** `gobo_rotation`, und das Wert-Teilband **„Wert bei 0 %" = 192**,
   **„Wert bei 100 %" = 223** setzen. Der Fader hält den Laser dann im
   Dreh-Modus und regelt nur das **Tempo**.
4. **Sicherheit auf Tasten:** die Aktionen **„Laser scharf/unscharf"** und
   **„Laser NOT-AUS"** lassen sich ebenfalls auf VC-Buttons legen (auch per
   MIDI-Pad auslösbar).

> Muster lassen sich außerdem in **Snaps/Szenen** aufnehmen (Programmer →
> „Speichern" bzw. Assistent-Tab „Programmer → Szene") und so über Chaser abspielen.

---

## 7. Netzwerk-Laser: Zeichnen-Studio (nur exakte Laser)

Hat dein Laser eine Netzwerk-Ausgabe (Ether Dream / IDN), erscheint zusätzlich:

- **„✏️ Zeichnen…"** öffnet das Vollbild-**Zeichen-Studio**: Formen (Kreis /
  Rechteck / Linie / Polygon / Stern) aufziehen, Freihand mit Glätten,
  Undo/Redo (Strg+Z/Y), Raster-Einrasten, Figuren-Bibliothek. Über
  **„🖼️ Bild importieren…"** wird ein Bild automatisch in eine Figur vektorisiert.
- Die gemalten Figuren sind Show-persistent und erscheinen mit ★ in der
  Ausgabe-Auswahl.

---

## 8. Sicherheit (wichtig)

- Netzwerk-Laser starten **unscharf** — solange nicht bewusst **scharf
  geschaltet**, wird jeder Frame geblockt (Vorschau ohne Lichtaustritt).
- Der Bereich **„Laser-Ausgabe (Netzwerk)"** hat einen großen
  **Scharf/Unscharf-Umschalter** und einen **NOT-AUS**. Beim Scharfschalten
  tritt **echtes Laserlicht** aus — Publikum/Augen schützen, Not-Aus
  bereithalten.
- Ein Show-Load schaltet automatisch auf **unscharf** zurück.

### Grand Master und Laser

- Ein Laser **mit** Dimmer- oder Farbkanal wird vom **Grand Master** ganz
  normal mitgedimmt.
- Ein Laser **ohne** Dimmer (z. B. SH-LASER3W, ZQB370 — nur ein Kanal
  „Betriebsart“ bzw. „Laser An/Aus“) lässt sich **nicht stufenlos dimmen**.
  Der Grand Master **schaltet ihn bei 0 % aus**: die Betriebsart geht auf den
  Wert „Laser aus“ aus dem Geräteprofil. Zwischen 1 % und 100 % läuft der Laser
  unverändert weiter.
- Hat der Shutter-Kanal gar keine Bereichsangaben, wird er auf 0 gezogen; ein
  Programmwahl-Kanal ohne „Aus“-Bereich bleibt unangetastet. Ein bloßes „Off“
  zählt nur am Shutter oder an einem Betriebsart-Kanal (Name „Mode“/„Modus“) —
  „Macros: Off“ heißt nur „kein Makro“.
- Ein Laser **mit** Dimmerkanal bekommt bei 0 % zusätzlich die eindeutig
  benannten Aus-Werte („Laser off“, „Blackout“) — der Dimmer gilt nicht immer
  für den Laser (z. B. DJ Lase BlueStar: Dimmer nur für die LED).
- **Viele Profile kennen keinen Aus-Wert** (z. B. Boom Box Fx2 3-Kanal, Galaxian
  Sky, Wookie): solche Laser **strahlen bei Grand Master 0 % weiter**.
  Verlässlich aus ist ein Laser nur mit dem **NOT-AUS**.

### Blackout, Ziel-Blackout und NOT-AUS

Dieselben **Aus-Werte aus dem Geräteprofil** wie beim Grand Master gelten auch
hier — ein Laser bekommt also nicht einfach überall 0:

- **BLACKOUT** (global): alle Laser bekommen ihre Aus-Werte (z. B. Betriebsart
  „Laser aus“, Shutter zu). Der Aus-Wert ist **nicht immer 0** — bei manchen
  Lasern bedeutet DMX 0 an der Betriebsart „Auto“; eine reine Null würde
  sie einschalten.
- **Blackout-Taste mit Ziel:** nur die Laser im Ziel bekommen ihre Aus-Werte,
  alle anderen laufen weiter.
- **Laser-NOT-AUS:** schreibt an jede Laser-Adresse mit bekanntem Aus-Wert
  diesen Wert, an alle übrigen Laser-Adressen 0 — und gewinnt immer (auch
  gegen Kanal-Modifier, Grand Master und Blackout).
- **NOT-AUS lösen:** nur mit dem Knopf **LASER NOT-AUS** oben rechts im
  Hauptfenster — klicken und die Rückfrage bestätigen. Der Knopf im Laser-Tab
  und die VC-Taste „Laser NOT-AUS“ lösen nur aus. Solange der NOT-AUS aktiv
  ist, werden Werte gemerkt, der Laser bleibt dunkel: Betriebsart, Muster,
  Regler, Snaps und MIDI lösen ihn nicht. Nach dem Lösen gibt der Laser sofort
  wieder aus, was eingestellt ist.
- Kennt das Profil **keinen** Aus-Wert (siehe oben), gibt es nichts zu
  schreiben: Blackout und Ziel-Blackout setzen dann die Lichtkanäle auf 0,
  ein Laser ohne Dimmer kann trotzdem weiterstrahlen. Im DMX-Monitor sieht man
  bei Lasern deshalb nach einem Blackout nicht unbedingt überall 0.

### Was als Laser gilt (für NOT-AUS, Blackout und „Alles Weiß“)

An diesen Stellen behandelt LightOS ein Gerät als Laser, wenn **eines** davon
zutrifft:

- der Gerätetyp ist „Laser“,
- es hat einen Laser-Kanal (Muster, X/Y, Laserfarbe …),
- ein Kanal trägt „Laser“ im Namen – z. B. „Laser: Red“ an einem Lichtset oder
  „Laser Helligkeit“ an einem Moving Head,
- „Laser“ steht im Geräte-, Hersteller- oder Patch-Namen.

Für alle gilt dasselbe: **LASER NOT-AUS** und **Blackout** schalten das
**ganze** Gerät dunkel (bei einem Lichtset also auch Derby und Strahler),
**„Alles Weiß“** lässt es aus. Wird ein Gerät nur über einen Namen erkannt, sagt
LightOS das beim Patchen in der Statusleiste. Der Tooltip des NOT-AUS-Knopfs
nennt die Zahl der erkannten Laser – steht dort **0**, schaltet der Knopf über
DMX nichts dunkel.

- **Lösen des NOT-AUS:** an keinem dieser Geräte durch einen Wert – weder ein
  Muster-Abruf am Laser noch ein Gobo- oder Shutter-Wert an einem Moving Head
  mit Laserdiode. Gelöst wird nur über den Knopf **LASER NOT-AUS** mit
  Rückfrage.
- **Grenze:** Erkannt wird am gepatchten Modus. Ein Kombigerät in einem
  Kurz-Modus ohne eigenen Laserkanal (z. B. Chauvet GigBAR 2 im 3-Kanal-Modus,
  Cameo Multi FX Bar im 2-Kanal-Modus – der Laser läuft dort über
  Automatikprogramme) gilt nur als Laser, wenn Typ oder Name es sagen. Wer so
  ein Gerät im Kurz-Modus betreibt, nimmt „Laser“ in den Patch-Namen auf.
- Der **Laser-Tab** erscheint weiterhin nur für Geräte vom Typ „Laser“ oder mit
  Laser-Kanälen.

### Laser-EFX (Bewegung)

- Ein EFX bewegt bei Lasern die Achsen **„X-Bewegung“/„Y-Bewegung“**
  (`laser_x`/`laser_y`) statt Pan/Tilt. Diese Zuordnung wird in der Show-Datei
  mitgespeichert; der Show-Check (`tools/lint_show.py`) warnt, wenn ein EFX auf
  ein Gerät zeigt, das keine der beiden Achsen hat.

---

### Siehe auch
- [ANLEITUNG.md](../ANLEITUNG.md) – Oberfläche, Patchen, Gruppen, Programmer
- [EFFEKTE.md](../EFFEKTE.md) – Effekte, Snaps/Szenen, Virtuelle Konsole
- [Übersicht bebilderte Anleitungen](../ANLEITUNGEN.md)
