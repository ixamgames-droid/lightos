# laser_view (LaserView)

> Laser-Steuerseite (Programmer-Tab) für DMX-Laser: Regler-Zeilen je Kanal,
> Werksmuster-Kacheln, Arm/NOT-AUS (LAS-02).

## Zweck

Sicherheits-bewusste Steuer-UI für als Laser erkannte Fixtures. Arbeitet auf der
aktuellen Programmer-Auswahl: baut pro steuerbarem Kanal eine `_ChannelRow`
(Label + Slider + Spin + Range-ComboBox) und zeigt Werksmuster als
`_PatternTile`-Kacheln (Nutzer-Foto oder generierte Vorschau). Arm-Toggle und
NOT-AUS spiegeln den Laser-Safety-Zustand des Managers.

## Bedienung / Optionen

| Bedienung | Wirkung |
|---|---|
| Kanal-Zeile (`_ChannelRow`) | Slider/Spin setzt DMX-Wert; Range-Combo wählt ChannelRange |
| Muster-Kachel (`_PatternTile`, LAS-18b) | Werksfigur/Muster abrufen |
| Arm | Laser scharf/unscharf (Safety-Toggle, spiegelt Manager) |
| NOT-AUS | Sofort-Stopp + entwaffnen |
| Weitere Kanäle (`_ADVANCED_GROUP`) | Zusatz-Attribute (Zoom, Gobo, Rotation) eingeklappt |

## Verknüpfungen

- **LaserOutputManager:** Arm-/E-Stop-Zustand und Output über den Laser-Manager
  in AppState (`ensure_laser_output`); Arm-Button hält sich mit dem Manager sync.
- **Programmer:** liest die aktuelle Auswahl, bildet daraus das Kanal-Template.
- **Capability-Check:** `_is_laser(...)` delegiert an den Fixture-Capability-Check.
- **Palette:** Muster nutzen `PaletteType.LASER`-Paletten.

## Zugehörige Tests

- `tests/test_laser_capability.py` — Laser-Erkennung.
- `tests/test_laser_dmx_estop.py` — NOT-AUS-Pfad.
- `tests/test_laser_pattern_picker.py` — Muster-Kacheln.
- `tests/test_laser_figure.py`, `test_laser_snap_scene.py`, `test_laser_not_spider.py`.

## Quelle (file:line)

- `src/ui/views/laser_view.py:218` — Klasse `LaserView`
- `src/ui/views/laser_view.py:78` — `_ChannelRow` (Regler-Zeile)
- `src/ui/views/laser_view.py:157` — `_PatternTile` (Werksmuster)
- `src/ui/views/laser_view.py:59` — `_is_laser` (Capability)
