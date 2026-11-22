ID: VCB-51
Prioritaet: P2
Status: teils
Status-Notiz: Element, Gruppen-Bindung, Malen (Pinsel/Radierer/Fuellen/Loeschen, Aufloesung 1/2/4), eigene Ebene mit Pegel, Merken/Abruf, Speichern geliefert; Matrix-Geraet-Bindung (FM-80), Mischarten und 20x40-Messung offen
Titel: VC-Pixelraster: Matrix als eigenes Konsolen-Element, live darauf zeichnen, Aufloesung einstellbar

**Herkunft:** Wunsch des Betreibers vom 22.11.2026 (loest den Rest „VC-Steuerung“ aus FM-13 ab: heute ist ein Panel in der Konsole nur ueber einzelne Koepfe ansprechbar).

**Ziel:** Neues VC-Element „Pixelraster“, gebunden an ein Matrix-Geraet oder eine Kopf-Gruppe (Raster aus `positions_json`). Darin live mit dem Finger/der Maus zeichnen: Pinsel mit Farbe (Farbwahl wie VC-Farbe), Radierer, Fuellen, Alles loeschen; Aufloesung des Zeichenrasters einstellbar (z. B. 2 x 2 Pixel zu einer Zelle zusammenfassen). Die Zeichnung ist eine eigene Ebene mit Pegel/Mischart ueber laufenden Matrix-Effekten, kann als Bild gespeichert und wieder abgerufen werden (Knopf). Touch-tauglich (Kiosk, Handy-Gruppe pruefen).

**Erledigt, wenn:** auf einem 20 x 40-Panel live gezeichnet werden kann und die Pixel ohne Verzoegerung folgen, die Aufloesung umschaltbar ist, Zeichnungen gespeichert/abgerufen werden, Tests und Anleitung.

**Geliefert (22.11.2026):** `src/ui/virtualconsole/vc_pixelraster.py` (Element `VCPixelraster`, registriert in Canvas, Leiste, Inspector, Schaukasten, Hochzeit-Show, Capability-Manifest), Bindung an eine Fixture-Gruppe ueber `AppState.gruppen_raster` (aufgeloestes Raster, FM-20 Gruppe-in-Gruppe, Kopf-Zellen). Pinsel, Radierer, Fuellen (Flutfuellung je Malpunkt), Loeschen (zweimal tippen), Aufloesung 1x1/2x2/4x4 (Zeichnung bleibt in voller Rasteraufloesung), Merken/Abruf bis 12 Bilder, Pegel-Regler. Ausgabe als eigene Ebene `src/core/engine/zeichen_ebene.py`, im Renderer direkt nach den Modify-Effekten und vor Mastern/Blackout/NOT-AUS: `u + (w - u) * Pegel`, nur color_r/g/b, nie Dimmer. Begruendung gegen den Programmer: der schreibt von laufenden Matrix-Effekten getriebene Farbkanaele bewusst nicht (WP-6) und kennt keinen Pegel. Speichern/Laden beim Element, Show-Reset raeumt alle Ebenen ab. Touch: Knoepfe/Pegel im Touch-Modus >= 44 px, Touch-Lock und Bearbeiten-Modus malen nicht, Finger malt. Tests `tests/test_vcb51_pixelraster.py`, Anleitung `docs/anleitung_vc_widgets/25_pixelraster.md`.

**Offen:** Bindung direkt an ein Matrix-Geraet (wartet auf FM-80; bis dahin Kopf-Gruppe), Mischarten neben Ueberblenden (z. B. Addieren/Nur-wo-hell), Messung „Pixel folgen ohne Verzoegerung" auf einem echten 20x40-Panel (Malen meldet je Zug die ganze Ebene neu; bei 800 Zellen unkritisch geschaetzt, nicht gemessen), Handy-Konsole (Element ist dort noch nicht fernbedienbar), eigenes Bild im Schaukasten.
