# EFX-Bewegung: Moving Heads (Kreis) und Spider (Tilt-Muster)

In dieser Anleitung lernst du, wie du eine EFX-Bewegungsfigur (Kreis) für die Moving Heads anlegst und prüfst – und wie du für die Spider (zwei Tilt-Bars, kein Pan) im **Spider-Modus** des EFX-Editors ein Tilt-Bewegungsmuster wählst. Bezug: `shows/Komplettshow_2026.lshow`.

## Moving Heads: EFX "Circle" anlegen

1. Öffne den **Programmer**, wähle die Gruppe **"MH"**, wechsle auf den Tab **"EFX"** und klicke auf **"+ Neu"**.
2. Wähle als Algorithmus **"Circle"** (Kreis) und vergib den Namen **"MH Circle"**.
3. Öffne das **"Große Fenster"** und stelle im Abschnitt **"Sichtbarkeit & Sonstiges"** ein:
   - **"Dimmer/Shutter mit öffnen"** anhaken (`open_beam`) – sonst bleiben die Moving Heads dunkel.
   - Unter **"Verhältnis der Geräte"**: **"Gegenläufig: jedes 2. Gerät entgegengesetzt"** aktivieren, damit das Bild symmetrisch wirkt.
4. Klicke auf **Start**.

## Bewegung verifizieren

5. Beachte: Die **2D-Live-View** zeigt die **Pan-Drehung** an – die Beam-Linie des Movers dreht sich mit der EFX. Der **Tilt** wird im Beam **nicht** dargestellt.
6. Prüfe die Bewegung über die Sektion **"Eingabe / Ausgabe" → "DMX Monitor"**: Die Pan-Kanäle **65** und **76** verlassen die Mitte **128** (z. B. **151** bzw. **104**) und laufen gegenläufig. Alternativ kannst du die Bewegung im **3D-Visualizer** kontrollieren.

![DMX-Monitor: MH-Kanäle 65 und 76 stehen auf 151 bzw. 104 statt Mitte 128 – Pan bewegt sich gegenläufig](img/02_dmx_mh_pan_bewegung.png)

## Spider: EFX im Spider-Modus (Tilt-Bewegungsmuster)

7. Die **Spider** sind Flower-Lichter mit **zwei separaten Tilt-Bars** und **ohne Pan**. Wählst du im Programmer die Gruppe **"Spider"** und legst über **"+ Neu"** eine EFX an, erkennt der Editor die Doppel-Tilt-Geräte und schaltet **automatisch in den Spider-Modus**: Statt der Pan/Tilt-Geometrie erscheint der Abschnitt **"Bewegungsmuster (Spider)"**, und die Geräte-Box zeigt **"Geräte: 2 Spider (folgen der Auswahl)"**. (Ist gar kein bewegliches Gerät gewählt, meldet der Editor **"keine beweglichen Geräte in der Auswahl"**.)
8. Wähle ein **Bewegungsmuster** – **Wippe**, **Welle**, **Zacken**, **Flackern** oder **Puls**. Jedes setzt eine reine **Tilt-Figur**; die EFX-Engine fährt die beiden Bars gegenläufig auf/zu (**Schere**). Feineinstellung über **"Schwung (Tilt-Hub)"**, **"Mitte (Tilt)"** und **"Welle (Versatz)"** – die **Scheren-Vorschau** zeigt die Bewegung live. Mit **Start** läuft das Muster. Aktiviere auch hier **"Dimmer/Shutter mit öffnen"**, sonst bleiben die Bars dunkel (der Spider-Master-Dimmer steht per Default auf 0).

Die Tilt-Stellung lässt sich alternativ **statisch** über den **Position-Tab (Tilt)** bzw. die **Virtuelle Konsole** setzen. Die Spider-Farbe ist **RGBW**.

## Tipps / Fallen

- **MH bleiben dunkel?** "Dimmer/Shutter mit öffnen" (`open_beam`) im Abschnitt "Sichtbarkeit & Sonstiges" muss aktiviert sein.
- **Keine Bewegung sichtbar?** Die 2D-Live-View zeigt die Pan-Drehung (Beam-Linie), aber keinen Tilt – zur genauen Kontrolle nutze den DMX Monitor (Kanäle 65/76 verlassen die Mitte 128) oder den 3D-Visualizer.
- **Spider bewegen sich nicht?** Prüfe, dass der **Spider-Modus** aktiv ist (Abschnitt "Bewegungsmuster (Spider)" sichtbar, Geräte-Box zeigt "… Spider"), ein **Muster** gewählt und **Start** gedrückt ist. Bleiben die Bars dunkel: **"Dimmer/Shutter mit öffnen"** aktivieren.
- Die **EFX-Geschwindigkeit** stellst du im Editor unter **"Tempo & Richtung"** (in Hz) ein.
