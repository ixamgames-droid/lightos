# channel_groups_view (ChannelGroupsView)

> Channel-Groups im QLC+-Stil: benannte Kanal-Bündel mit einem gemeinsamen
> Master-Slider.

## Zweck

Fasst rohe DMX-Kanäle (nicht Fixtures) zu benannten Gruppen mit einem
gemeinsamen Slider zusammen. Ein `ChannelGroup` hält eine Kanalliste (Eingabe
z. B. `1,2,5-10`); der Master-Slider skaliert alle Kanäle der Gruppe gemeinsam.
Gruppen werden mit der Show gespeichert und beim Laden wieder angewandt.

## Bedienung / Optionen

| Bedienung | Wirkung |
|---|---|
| Gruppe anlegen | Name + Kanalliste (`1,2,5-10`-Syntax) |
| Master-Slider | Skaliert alle Kanäle der Gruppe gemeinsam |
| Kanal-Parser | `_parse_channels('1,2,5-10')` → Liste einzelner Kanäle |

## Verknüpfungen

- **OutputManager:** schreibt die skalierten Werte in den DMX-Merge.
- **Show-Persistenz:** `to_dict()` (`:241`) serialisiert alle Gruppen in die
  `.lshow`-Datei; `apply_dict` ersetzt/anwendet sie beim Laden und spiegelt sie
  in die UI.
- **Abgrenzung zu Fixture-Gruppen:** hier rohe Kanäle, nicht Fixture-Auswahl
  ([`fixture_group_view`](fixture_group_view.md)).

## Zugehörige Tests

- `tests/test_channel_groups_show.py` — Serialisierung + Wiederanwenden beim Laden.

## Quelle (file:line)

- `src/ui/views/channel_groups_view.py:77` — Klasse `ChannelGroupsView`
- `src/ui/views/channel_groups_view.py:20` — `ChannelGroup` (Datenmodell)
- `src/ui/views/channel_groups_view.py:45` — `_parse_channels` (Bereichs-Parser)
- `src/ui/views/channel_groups_view.py:241` — `to_dict` (Show-Serialisierung)
