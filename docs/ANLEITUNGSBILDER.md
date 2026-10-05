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

Mehrere Anleitungen (`--alle` oder mehrere Namen) laufen **je in einem eigenen Prozess**:
jede bekommt eine frische Sandbox, ein frisches Hauptfenster und eine frisch geladene
Demo-Show. Was eine Anleitung einstellt (Programmer-Auswahl, Tempo, Playback-Optionen …),
sieht die nächste so nicht mehr. Das kostet je Anleitung die 5–6 Sekunden Aufbau
zusätzlich; dafür entsprechen Bilder und `--pruefen` genau dem Einzellauf der Anleitung.

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
| `docs/<anleitung>/img/NN_name.gif` | animierte Abläufe (Szenen mit `frames`, siehe [GIFs](#gifs)) |
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
| `braucht_gpu` | 3D-Visualizer: wird offscreen mit Meldung übersprungen, mit `--bildschirm` gebaut (siehe [Grenzen](#grenzen)) |
| `beschriftungen` | Beschriftung zusätzlich als Schild ins Bild schreiben |
| `frames` | Liste von `Frame`: statt einer PNG entsteht ein GIF (siehe [GIFs](#gifs)) |
| `gif_breite` | GIF auf diese Breite verkleinern, z. B. `1200` (nie vergrößern) |
| `gif_zuschnitt` | `(x, y, b, h)` im aufgenommenen Bild: nur diesen Bereich ins GIF |

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
im selben Fenster: was eine Szene einstellt, sieht die nächste *derselben Anleitung*
noch. Eine andere Anleitung startet dagegen immer frisch (eigener Prozess).
Zusätzliche `szenen_*.py` außerhalb des Pakets (nur für Tests) liest das Werkzeug aus
dem Ordner in `LIGHTOS_DOKU_SZENEN_ORDNER`.

Neue Anleitung anlegen, Szenen schreiben, dann:

```bash
venv/bin/python tools/anleitungsbilder.py <anleitung>
```

Jedes Bild vor dem Commit ansehen: sinnvoller Inhalt, keine Pfade oder Namen, keine
abgeschnittenen Texte.

## GIFs

Ein Ablauf (Knopf drücken → Wirkung → loslassen) wird als animiertes GIF gezeigt.
Eine GIF-Szene ist eine normale `Szene` mit einer Liste `frames`; jeder `Frame` ist
ein Einzelbild mit eigener Anzeigedauer. `vorher` stellt den Ausgangszustand her, dann
laufen die Frames der Reihe nach im selben Fenster: erst `schritt(ui)` (der
Bedienschritt), dann die Aufnahme. `nachher` räumt nach dem letzten Frame auf.

```python
from anleitungsbilder.runner import Frame, Szene

def _go(ui):
    ui.win._playback_view._go()        # echter Weg wie der Knopf

SZENEN = [
    Szene("13_go_ablauf", sektion="Playback", unterreiter="Playback",
          vorher=_liste_ohne_executor, nachher=_aufraeumen,
          gif_breite=1200,
          frames=[
              Frame(dauer_s=1.5, marken=[("GO", 1, "GO")]),
              Frame(dauer_s=2.2, schritt=_go,
                    marken=[("GO", 1, "GO"), (_hinweis, 2, "Hinweis")]),
              Frame(dauer_s=1.8, schritt=_go, marken=[("GO", 1, "GO")]),
          ]),
]
```

Felder eines `Frame`:

| Feld | Bedeutung |
|---|---|
| `dauer_s` | Anzeigedauer im GIF, Standard 1,2 s (1–2 s je Frame lesen sich gut) |
| `schritt` | `f(ui)`: Bedienschritt vor diesem Bild; der Zustand des vorigen Frames bleibt stehen |
| `marken` | wie `Szene.marken`; `None` = die Marken der Szene. Üblich: Kreis auf dem Knopf, der als Nächstes gedrückt wird |
| `dialog` | wie `Szene.dialog` (z. B. ein zusammengesetztes Bild); `None` = der Dialog der Szene |
| `warte_s` | echte Wartezeit nach `schritt`, Standard 0,3 s |

Was das Werkzeug daraus macht:

- **Eine Palette für alle Frames** (256 Farben, Median-Cut, ohne Dithering). Gleiche
  Flächen behalten so in jedem Frame denselben Farbindex, und ab dem zweiten Frame
  speichert das GIF nur das geänderte Rechteck. Nichts flimmert.
- **Endlosschleife**, je Frame die eigene Dauer.
- `gif_zuschnitt` schneidet zuerst zu, `gif_breite` verkleinert danach (Lanczos).
- **Größenbudget:** Ziel unter 1 MB, harte Grenze **2 MB** je GIF. Darüber bricht
  die Szene mit `GIF ist … MB groß` ab; ab 1 MB steht im Lauf ein Hinweis. Ein
  Vollbild-GIF mit drei Frames liegt bei 1200 px Breite um 100 KB. Wird es zu groß:
  weniger Frames, auf den wichtigen Bereich zuschneiden, `gif_breite` kleiner.
  Unter 1000 px Breite werden die Beschriftungen eines Vollbilds schwer lesbar —
  dann lieber zuschneiden.
- **Stabil:** Gleiche Eingabe ergibt ein byte-gleiches GIF. Weicht ein neu gerendertes
  GIF nur unmerklich ab (gleiche Frame-Zahl und Dauern, je Frame unter derselben
  Schwelle wie bei PNGs), bleibt die alte Datei liegen. `--pruefen` vergleicht GIFs
  genauso.
- Im Manifest `bilder.json` stehen zusätzlich `frames` (Anzahl) und `dauern_ms`;
  `marken` ist dort eine Liste je Frame.

Jedes GIF vor dem Commit ansehen — zum Beispiel in Einzelbilder zerlegen:

```bash
venv/bin/python -c "import sys; sys.path.insert(0, 'tools'); from anleitungsbilder import runner; [f.save(f'/tmp/frame{i}.png') for i, (f, _d) in enumerate(runner.gif_frames('docs/<anleitung>/img/NN_name.gif'))]"
```

`tests/test_anleitungsbilder.py` prüft außerdem, dass jedes GIF unter `docs/` höchstens
2 MB groß ist.

## Ausgabe und Neu-Rendern

- PNG, 8-Bit-Palette ohne Dithering (Pillow), ein Vollbild liegt bei 25–55 KB.
- Pixelgleich sind die Bilder nur auf demselben Rechner mit denselben Schriften.
  Das Theme wünscht „Roboto Condensed"; fehlt sie, nimmt Qt einen Ersatz. Welcher es
  war, steht im Manifest unter `schrift`.
- Weicht ein neu gerendertes Bild nur unmerklich vom vorhandenen ab (weniger als
  0,05 % der Pixel, zum Beispiel eine leicht anders glimmende Lampe), bleibt die alte
  Datei liegen. So ändert ein Neu-Rendern nicht jedes Mal alle Bilder im Diff.
  Vorsicht: Auch ein geänderter Knopftext (etwa „Yes“ → „Ja“) bleibt unter dieser
  Schwelle. Soll so eine Änderung ins Bild, die alte PNG vorher löschen.
- Qt-Standardtexte (Knöpfe wie „Ja“/„Abbrechen“, Tastenkürzel wie „Strg+N“) sind
  deutsch: Das Werkzeug lädt denselben Qt-Übersetzer wie die App.
- `--pruefen` rendert in die Sandbox, schreibt nichts nach `docs/` und meldet je Bild
  „wie im Repo", „weicht ab" oder „fehlt noch". Exit-Code 1, wenn eine Szene nicht
  mehr baubar ist.
- `--ausgabe ORDNER` schreibt nach `ORDNER/<anleitung>/` statt nach `docs/`.
- `--behalten` lässt den Sandbox-Ordner zur Fehlersuche liegen.

## Grenzen

- **3D-Visualizer:** WebGL bekommt offscreen keinen Kontext, die Fläche bleibt schwarz.
  Szenen mit `braucht_gpu=True` werden deshalb übersprungen. Gebaut werden sie am
  echten Bildschirm (X11) mit `--bildschirm`:

  ```bash
  DISPLAY=:0 venv/bin/python tools/anleitungsbilder.py vc_widgets --bildschirm
  ```

  Die Sandbox bleibt dabei genauso aktiv. Das Werkzeug zeichnet dann statt `offscreen`
  über `xcb`, das Fenster erscheint für die Dauer des Laufs auf dem Bildschirm (ohne
  den Fokus zu nehmen) und es entstehen **nur** die Szenen mit `braucht_gpu` — alle
  anderen bleiben offscreen gebaut und unverändert. Das 3D-Fenster braucht beim Start
  rund 20 s, bis die Szene steht. Beispiel: `05_blackout_links_3d.gif` in
  `szenen_vc_widgets.py` (Visualizer öffnen, Kamera setzen, nur die 3D-Fläche aufnehmen).
  Eine ganze Anleitung nur aus 3D-Szenen ist `szenen_3d_buehne.py`: sie baut eine
  Doku-Bühne in der Sandbox, öffnet den Visualizer einmal und nimmt den Inhalt des
  Visualizer-Fensters ohne Fensterrahmen auf (`QWidget.grab`, die WebGL-Fläche wird
  eigens eingesetzt; ein offenes Menü wird als eigenes Bild an seiner Stelle eingefügt).
- **Audio:** In der Sandbox gibt es keine Audio-Geräte. Bilder der BPM-Erkennung
  zeigen deshalb den manuellen Modus.
- Die Statusleiste zeigt „Enttec: nicht gefunden", weil die Sandbox nur einen
  Art-Net-Ausgang an die eigene Loopback-Adresse einrichtet und nicht nach
  Geräten sucht.
