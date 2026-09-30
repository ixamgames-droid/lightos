# Anleitungsbilder aus dem Code erzeugen

Die Bilder der Anleitungen entstehen mit einem Werkzeug statt per Hand-Screenshot.
Es startet die LightOS-Oberfläche **offscreen** (ohne Fenster auf dem Bildschirm) in
fester Größe 1600 × 900, lädt eine mitgelieferte Doku-Demo-Show und nimmt je Anleitung
eine Liste von Szenen auf. Ändert sich die Oberfläche, rendert man die Bilder mit einem
Befehl neu.

```bash
venv/bin/python tools/anleitungsbilder.py projektseite         # eine Anleitung
venv/bin/python tools/anleitungsbilder.py --alle               # alle Anleitungen
venv/bin/python tools/anleitungsbilder.py projektseite --nur 02_patch
venv/bin/python tools/anleitungsbilder.py --alle --pruefen     # nur prüfen, nichts schreiben
venv/bin/python tools/anleitungsbilder.py --liste              # Szenen anzeigen
```

Ein Lauf dauert rund 12 Sekunden (davon 5–6 Sekunden für Fenster und Demo-Show).

## Was wo liegt

| Datei | Inhalt |
|---|---|
| `tools/anleitungsbilder.py` | Aufruf, Optionen, Abgleich der echten Datenorte nach dem Lauf |
| `tools/anleitungsbilder/sandbox.py` | lenkt alle Datenpfade in einen Wegwerf-Ordner um und prüft das |
| `tools/anleitungsbilder/demo_show.py` | Doku-Demo-Show, nur aus eingebauten Generic-Profilen |
| `tools/anleitungsbilder/runner.py` | `Szene`, die kleine UI-API, Aufnahme, Verkleinerung, Manifest |
| `tools/anleitungsbilder/marker.py` | roter Rahmen und Nummernkreis, freie Lage für den Kreis |
| `tools/anleitungsbilder/szenen_<anleitung>.py` | die Szenen einer Anleitung |
| `docs/<anleitung>/img/NN_name.png` | die Bilder |
| `docs/<anleitung>/img/bilder.json` | Manifest: Szene, Titel, Bildgröße, Markierungen, md5, Schrift, git-Stand |

## Datenschutz: die Sandbox

Das Werkzeug baut ein volles Hauptfenster. Das würde sonst die echte
Fixture-Bibliothek, `recent.json`, `auto_save.lshow`, die sACN-Kennung und – relativ
zum Arbeitsverzeichnis – `data/` im Repo anfassen. Deshalb gilt:

1. **Vor dem ersten `src`-Import** werden `HOME`, `XDG_DATA_HOME`, `XDG_CONFIG_HOME`,
   `XDG_CACHE_HOME`, `XDG_STATE_HOME`, `XDG_RUNTIME_DIR`, `APPDATA`,
   `LIGHTOS_SHOW_DB`, `LIGHTOS_FIXTURE_DB`, `LIGHTOS_CRASH_LOG`, `LIGHTOS_SACN_CID`,
   `LIGHTOS_PREFS_DIR` und `LIGHTOS_UNIVERSES_JSON` auf einen frischen Temp-Ordner
   gesetzt, und das Arbeitsverzeichnis wechselt dorthin. Ausgabe-Thread, Audio-Start,
   Enttec-Prozess und die Wiederherstellungsfrage sind abgeschaltet.
2. **Selbstprüfung:** Vor dem ersten Bild fragt das Werkzeug die Pfade ab, die die
   geladenen Module *tatsächlich* benutzen (Fixture-DB, Show-DB, Datenordner,
   `universes.json`, `ui_prefs.json`, `recent.json`, `data/*.json`, Qt-Standardpfade).
   Liegt einer außerhalb der Sandbox, bricht es ab.
3. Wofür es keinen Schalter gibt, wird abgeschaltet: MIDI-Autoconnect (öffnete sonst
   echte ALSA-Ports), Web-Remote, Autosave-Timer und die Suche nach seriellen Ports
   für die Enttec-Anzeige.
4. **Nach dem Lauf** vergleicht das Werkzeug den echten Datenordner sowie `data/` und
   `shows/` im Repo mit dem Stand vor dem Lauf (Änderungszeit, Größe, Existenz). Eine
   Abweichung beendet den Lauf mit Exit-Code 3. Läuft gleichzeitig eine LightOS-App,
   bleiben deren Lebenszeichen-Dateien (`last_alive.txt`, Autosave …) außen vor.

Der Test `tests/test_anleitungsbilder.py` hält das fest.

## Die Doku-Demo-Show

Nur eingebaute Generic-Profile, damit kein echtes Gerät und kein echtes Rig
nachgestellt wird: PAR 1–8 (Dimmer+RGB, Adresse 1–29), Wash 1/2 (Moving Head Wash
RGB), Spot 1/2 (Moving Head Spot mit Pan/Tilt), eine LED-Leiste, vier Gruppen, drei
Farb-Szenen, ein Lauflicht, eine Regenbogen-Matrix, ein Kreis-EFX, die Cue-Liste
„Doku-Cues" mit drei Cues und eine VC-Seite mit Knöpfen und Fadern. Die fids der
Rollen stehen in den Szenen unter `ui.info` (`pars`, `washes`, `spots`, `mover`,
`leiste`).

## Eine Szene hinzufügen

Eine Anleitung ist eine Datei `tools/anleitungsbilder/szenen_<anleitung>.py` mit der
Liste `SZENEN`. Optional legt `ZIEL` den Zielordner fest (repo-relativ, Standard
`docs/<anleitung>/img`).

```python
from anleitungsbilder.runner import Szene

ZIEL = "docs/anleitung_patch/img"

def _pars_waehlen(ui):
    ui.waehle(ui.info["pars"])
    ui.wert(ui.info["pars"], "intensity", 255)
    ui.reiter("Color")

SZENEN = [
    Szene("01_patch", sektion="Patchen", unterreiter="Patch",
          titel="Patch-Tabelle",
          marken=[("+ Gerät hinzufügen", 1, "Gerät hinzufügen"),
                  ("Auto-Patch", 2, "Adressen automatisch vergeben")]),
    Szene("02_farbe", sektion="Programmer", vorher=_pars_waehlen,
          ausschnitt="stack"),
]
```

Felder einer `Szene`:

| Feld | Bedeutung |
|---|---|
| `name` | Dateiname ohne Endung, Konvention `NN_name` |
| `sektion` | Name aus der Sektionsleiste (`"Bühne"`, `"Patchen"`, `"Programmer"`, `"Virtual Console"`, `"Simple Desk"`, `"Playback"`, `"E/A"`, `"BPM"`) oder Index |
| `unterreiter` | Text eines Reiters auf der Seite (auch innere Reiter wie `"Color"`) |
| `titel` | kurze Beschreibung für Manifest und `--liste` |
| `vorher` / `nachher` | `f(ui)` stellt den Zustand her bzw. räumt danach auf |
| `dialog` | `f(ui) -> QWidget`: statt des Fensters diesen Dialog aufnehmen |
| `marken` | Liste `(finder, nummer, beschriftung[, lage])`; `lage` (`"links"`, `"rechts"`, `"oben"`, `"unten"`) ist nur ein Vorzug für den Nummernkreis |
| `ausschnitt` | `None` (ganzes Fenster), `"stack"` (nur die Sektion), ein Finder oder `(x, y, b, h)` |
| `warte_s` | echte Wartezeit vor der Aufnahme, für Timer-gesteuerte Anzeigen |
| `groesse` | Fenster- bzw. Dialoggröße, Standard 1600 × 900 |
| `braucht_gpu` | 3D-Visualizer: wird offscreen mit Meldung übersprungen |
| `beschriftungen` | Beschriftung zusätzlich als Schild ins Bild schreiben |

Ein **Finder** ist ein `objectName`, der sichtbare Text eines Knopfs oder einer
Beschriftung („…" und „..." gelten als gleich) oder eine Funktion `f(ui) -> QWidget`.
Findet das Werkzeug ein markiertes Widget nicht, bricht es mit einer klaren Meldung
ab – ein umbenannter Knopf fällt so auf, statt dass ein Bild ohne Markierung entsteht.

**Wo der Nummernkreis sitzt**, entscheidet `marker.platzieren`: Es probiert Plätze
rund um den Rahmen (außen links, rechts, oben, unten, die Ecken, dann weiter weg mit
einer kurzen Verbindungslinie, zuletzt innen) und nimmt den ersten, der ganz im Bild
liegt, keinen fremden beschrifteten Bereich verdeckt (Knöpfe, Beschriftungen,
Eingabefelder, Reiter, Listen- und Tabelleneinträge, Menüpunkte) und keinen anderen
Rahmen oder Kreis berührt. Der Kreis muss außerdem seinem eigenen Rahmen am nächsten
sein, sonst läse man ihn als Nummer des Nachbarn. Eine `lage` in der Szene wird zuerst
probiert, bei einer Kollision aber verworfen. Findet sich gar kein freier Platz, nimmt
der Kern den, der am wenigsten verdeckt, und meldet im Lauf
`Hinweis: Marke N hat keinen freien Platz … Bild prüfen`. Selbst gemalte Anzeigen
(z. B. das DMX-Raster) kennt der Kern nicht als beschriftet; eine Szene gibt sie
`bild(..., hindernisse=[...])` mit. Zur Fehlersuche zeichnet
`LIGHTOS_DOKU_HINDERNISSE=1` alle erkannten Bereiche dünn grün ins Bild.

Die UI-API in `vorher`: `ui.sektion(...)`, `ui.reiter(text)`, `ui.waehle(fids)`,
`ui.wert(fids, attribut, wert)`, `ui.finde(finder)`, `ui.pump(sekunden)` sowie
`ui.win` (Hauptfenster), `ui.state` und `ui.info`. Die Szenen laufen der Reihe nach
im selben Fenster: was eine Szene einstellt, sieht die nächste noch.

Neue Anleitung anlegen, Szenen schreiben, dann:

```bash
venv/bin/python tools/anleitungsbilder.py <anleitung>
```

Jedes Bild vor dem Commit ansehen: sinnvoller Inhalt, keine Pfade oder Namen, keine
abgeschnittenen Texte.

## Ausgabe und Neu-Rendern

- PNG, 8-Bit-Palette ohne Dithering (Pillow), ein Vollbild liegt bei 25–55 KB.
- Pixelgleich sind die Bilder nur auf demselben Rechner mit denselben Schriften.
  Das Theme wünscht „Roboto Condensed"; fehlt sie, nimmt Qt einen Ersatz. Welcher es
  war, steht im Manifest unter `schrift`.
- Weicht ein neu gerendertes Bild nur unmerklich vom vorhandenen ab (weniger als
  0,05 % der Pixel, zum Beispiel eine leicht anders glimmende Lampe), bleibt die alte
  Datei liegen. So ändert ein Neu-Rendern nicht jedes Mal alle Bilder im Diff.
- `--pruefen` rendert in die Sandbox, schreibt nichts nach `docs/` und meldet je Bild
  „wie im Repo", „weicht ab" oder „fehlt noch". Exit-Code 1, wenn eine Szene nicht
  mehr baubar ist.
- `--ausgabe ORDNER` schreibt nach `ORDNER/<anleitung>/` statt nach `docs/`.
- `--behalten` lässt den Sandbox-Ordner zur Fehlersuche liegen.

## Grenzen

- **3D-Visualizer:** WebGL bekommt offscreen keinen Kontext, die Fläche bleibt schwarz.
  Szenen mit `braucht_gpu=True` werden deshalb übersprungen. 3D-Bilder entstehen
  weiterhin von Hand an einem Rechner mit echter Grafik.
- **Audio:** In der Sandbox gibt es keine Audio-Geräte. Bilder der BPM-Erkennung
  zeigen deshalb den manuellen Modus.
- Die Statusleiste zeigt „Enttec: nicht gefunden", weil die Sandbox nur einen
  Art-Net-Ausgang an die eigene Loopback-Adresse einrichtet und nicht nach
  Geräten sucht.
