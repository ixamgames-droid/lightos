# Rig aus einer MVR-Datei übernehmen

MVR (*My Virtual Rig*) ist das offene Austauschformat vieler Lichtprogramme, etwa
grandMA, Vectorworks, Depence, Capture oder Chamsys. Eine `.mvr`-Datei sagt, welches
Gerät wo hängt, wie es ausgerichtet ist und auf welcher DMX-Adresse es liegt. Die
Gerätetypen stecken als GDTF-Dateien mit drin.

LightOS übernimmt daraus die **Geräte in den Patch** und ihre **Position und
Ausrichtung im 3D**. Noch ohne Bilder.

## So geht's

1. **Datei → MVR-Datei importieren …** wählen und die `.mvr`-Datei öffnen.
2. Es folgt eine **Vorschau**, angelegt wird noch nichts. Je Gerät eine Zeile:
   - **Name**, **Ebene** (Layer und Gruppe aus der Datei) und **Typ (Datei)**, also
     Gerätetyp und Modus, wie sie in der Datei stehen.
   - **Profil:** das passende Profil aus der Geräte-Bibliothek. LightOS vergleicht
     Hersteller, Modell und die Kanalzahl des Modus. Groß/klein und Leerzeichen
     zählen dabei nicht.
     - **„neu aus GDTF“**: die Bibliothek kennt den Typ nicht. Er wird beim Import
       als eigenes Profil mit den Kanälen aus der Datei angelegt. Pan/Tilt fein werden
       erkannt; was LightOS nicht kennt, wird ein einfacher Fader mit dem Namen aus
       der Datei. Nichts fällt weg.
     - **„nicht zugeordnet“**: in der Datei steht kein lesbarer Gerätetyp. Im
       Auswahlfeld ein Profil wählen (tippen sucht), sonst wird das Gerät nicht
       angelegt.
   - **Adresse** als Universum.Adresse.
   - **Konflikt:** belegt schon ein Gerät im Patch die Adresse, oder fehlt sie, steht
     hier, was passieren soll: **überspringen** (Vorgabe bei Überschneidungen) oder
     **auf freie Adresse** legen. Vorhandene Geräte werden nie verändert.
   - **Position (m)** im 3D und der **Status**.
3. **Importieren** legt alle Geräte an, bei denen „wird angelegt“ steht, und setzt
   ihre Position und Ausrichtung.
4. **Rückgängig (Strg+Z)** nimmt den ganzen Import in einem Schritt zurück.

## Gut zu wissen

- **Alles oder nichts:** geht unterwegs etwas schief, wird alles zurückgenommen,
  auch neu angelegte Profile. Der Patch bleibt dann, wie er war.
- **Achsen:** MVR rechnet in Millimetern mit der Höhe nach oben in Z. LightOS rechnet
  in Metern mit der Höhe in Y. Das Publikum (in MVR meist vorn bei −Y) liegt in
  LightOS bei +Z. Ein hängendes Gerät ohne Drehung strahlt nach unten.
- **Traversen und Fokuspunkte** zählt die Vorschau, übernimmt sie aber noch nicht.
- **Kaputte oder verdächtige Dateien** werden mit einer Meldung abgelehnt und nichts
  wird verändert. Dazu zählen beschädigte Archive, unzulässige Dateinamen,
  ungewöhnlich große oder stark gepackte Inhalte und XML mit Dokumenttyp-Angaben.
  Eine einzelne unlesbare GDTF-Datei trifft nur ihre Geräte, sie bleiben
  „nicht zugeordnet“.
- **Noch nicht drin:** der Export als MVR und die Umwandlung eigener Profile nach
  GDTF (Backlog VIZ-56, Teil 2 und 3).
