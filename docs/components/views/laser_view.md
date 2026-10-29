# laser_view (LaserView)

> Laser-Tab im Programmer für DMX-Laser: Sicherheitsleiste mit NOT-AUS, darunter je
> nach Geräteprofil die Bausteine (LAS-34) oder die bisherige Bedienung aus
> Kacheln und Kanal-Reglern (LAS-02).

## Zweck

Sicherheits-bewusste Steuer-UI für als Laser erkannte Fixtures. Arbeitet auf der
aktuellen Programmer-Auswahl. Werte fließen ausschließlich über
`set_programmer_value(fid, attr, head=)`; die View schreibt nur auf ausdrückliche
Nutzeraktion, es gibt keinen Auto-Start.

Liefert das Geräteprofil **Laser-Angaben** (`laser_profilangaben`: Betriebsart,
Musterliste, Farbtabelle, Richtungen — LAS-33), stehen statt der Kanal-Zeilen die
**Bausteine** aus `src/ui/widgets/laser_tab_bausteine.py` da. Jeder Baustein fällt
**einzeln** auf die bisherige Bedienung zurück, wenn das Profil dazu nichts sagt
oder sich die gewählten Laser darin unterscheiden; kein Kanal geht verloren
(`bedienbare_attribute`, Plan in `_Plan`).

## Bedienung / Optionen

**Immer oben — Sicherheitsleiste** (LAS-34):

| Bedienung | Wirkung |
|---|---|
| Zustand links | „Laser AN" / „Laser AUS" laut Betriebsart, „Laser AN (n von m)", bzw. „NOT-AUS aktiv — …"; Zusatz, wenn BLACKOUT oder Grand Master 0 % den Laser dunkel halten |
| Sperrzonen-Abzeichen (`_SperrzonenAbzeichen`) | gelb, wenn es zu den gewählten Lasern etwas zu melden gibt; Klick öffnet den Planer |
| „Meldung ▾" / „Meldung ▴" | klappt die Sperrzonen-Meldung je Laser unter der Leiste auf/zu |
| „Sperrzonen planen…" | öffnet den Sperrzonen-Planer (nur Anzeige, schaltet nicht ab) |
| „■ LASER NOT-AUS" | Sofort-Stopp. Löst nur aus — gelöst wird allein mit dem Knopf oben rechts im Hauptfenster samt Rückfrage (LAS-36); bis dahin werden Werte gemerkt, der Laser bleibt dunkel |

**Profil mit Laser-Angaben — Bausteine** (`laser_tab_bausteine.py`):

| Baustein | Wirkung |
|---|---|
| „Betriebsart" (`BetriebsartUmschalter`) | Segmente Aus · Musik · Auto · Statische Muster · Dynamische Muster, je mit Unterzeile („Laser dunkel", „Gerät läuft selbst", „LightOS steuert alles", „LightOS steuert, Muster bewegt sich"; Profil-Betriebsarten ohne eigene Zeile: „LightOS steuert" / „Gerät läuft selbst"); bei Musik/Auto Hinweis „Gerät läuft selbst — Muster, Lage und Farbe wirken in dieser Betriebsart nicht." |
| „Vorschau & Position" (`LageFeld`, `LageAnzeige`) | Muster in Farbe, Größe und Lage; Ziehen verschiebt die Lage, Knopf „Mitte" stellt zurück |
| „Muster" (`MusterGalerie`, `MusterKachel`) | eine Kachel je Muster des Profils (Schemabild, kein Foto); „alle 0–255 ▸" klappt den Regler für Werte ohne Profileintrag auf |
| „Farbe" (`FarbFelder`) | ein Feld je Farbe der Farbtabelle, ebenfalls mit „alle 0–255 ▸" |
| Regler (`SprechRegler`) | richtig herum mit sprechenden Enden (z. B. „Größe", „Zeichentempo", „Mustertempo"), daneben der gesendete DMX-Wert |
| „Gemerkte Muster" | Laser-Paletten der Show als Kacheln |

**Profil ohne Laser-Angaben — bisherige Bedienung** (LAS-02):

| Bedienung | Wirkung |
|---|---|
| „Mustergruppe" (Gruppe A / Gruppe B / A + B) | bei Lasern mit doppelten Kanälen die Mustergruppe wählen |
| „Betriebsart" (Kacheln) | Shutter-Bereiche des Profils als Kacheln |
| Kanal-Zeile (`_ChannelRow`) | Slider/Spin setzt DMX-Wert; Range-Combo wählt ChannelRange |
| „Werksmuster (Gerät)" (`_PatternTile`, LAS-18b) | Werksfigur/Muster abrufen |
| „Weitere Kanäle" (`_ADVANCED_GROUP`) | Zusatz-Attribute eingeklappt |
| „Muster-Paletten" | aktuelle Laser-Werte als benanntes Muster speichern |

## Verknüpfungen

- **LaserOutputManager:** NOT-AUS-Zustand und Output über den Laser-Manager in
  AppState (`ensure_laser_output`); ausgelöst wird über
  `AppState.laser_notaus_ausloesen` (LAS-31).
- **Programmer:** liest die aktuelle Auswahl, bildet daraus das Kanal-Template.
- **Capability-Check:** `fixture_has_laser_capability(fx)` (laser_view.py:125) — der Tab erscheint nur, wenn die Auswahl Laser enthält.
- **Profilangaben:** `src/core/laser/profilangaben.py` (LAS-33).
- **Palette:** Muster nutzen `PaletteType.LASER`-Paletten.

Bedienung Schritt für Schritt: [Anleitung Laser](../../anleitung_laser/ANLEITUNG_LASER.md).

## Zugehörige Tests

- `tests/test_laser_capability.py` — Laser-Erkennung.
- `tests/test_laser_dmx_estop.py` — NOT-AUS-Pfad.
- `tests/test_las31_ein_weg_ausloesen.py` — der NOT-AUS-Knopf geht wie Kopfleiste und VC-Taste über `AppState.laser_notaus_ausloesen` (LAS-31).
- `tests/test_laser_pattern_picker.py` — Muster-Kacheln.
- `tests/test_las34_doku.py` — Laser-Anleitung nennt Sperrzonen-Knopf und „nur Anzeige".
- `tests/test_laser_figure.py`, `test_laser_snap_scene.py`, `test_laser_not_spider.py`.

## Quelle (file:line)

- `src/ui/views/laser_view.py:486` — Klasse `LaserView`
- `src/ui/views/laser_view.py:614` — Schalter „Meldung ▾"
- `src/ui/views/laser_view.py:624` — Knopf „Sperrzonen planen…"
- `src/ui/views/laser_view.py:789` — `_baue_bausteine` (LAS-34)
- `src/ui/views/laser_view.py:330` — `_ChannelRow` (Regler-Zeile)
- `src/ui/views/laser_view.py:425` — `_PatternTile` (Werksmuster)
- `src/ui/widgets/laser_tab_bausteine.py:213` — `BetriebsartUmschalter`
