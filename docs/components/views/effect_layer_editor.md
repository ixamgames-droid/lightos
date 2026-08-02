# effect_layer_editor (EffectLayerEditor)

> Editor eines `LayeredEffect`: eine Liste von Layern (gestapelte Effekte)
> bearbeiten.

## Zweck

Bearbeitet einen geschichteten Effekt — mehrere Effekt-Layer, die übereinander
gemischt werden. Der Editor pflegt die Layer-Liste (hinzufügen/entfernen/
umordnen, Parameter je Layer) und kann in ein großes, scrollbares Fenster
ausgekoppelt werden.

## Bedienung / Optionen

| Bedienung | Wirkung |
|---|---|
| Layer-Liste | Layer hinzufügen/entfernen/umordnen |
| Layer-Parameter | Einzel-Layer konfigurieren — **es werden nur die Felder gezeigt, die der gewählte Layer-Typ wirklich auswertet** (seit 2026-08-02: ein Begrenzer bot vorher Amplitude und Frequenz an, die er nie liest). Die Zuordnung liegt in `core.engine.effect_layers.used_fields`, direkt neben `process`. |
| Auskoppeln | Editor in großes Fenster verschieben / zurückholen |

## Verknüpfungen

- **LayeredEffect-Funktion:** editiert das `LayeredEffect`-Objekt
  (FunctionManager-Gruppe „LayeredEffect").
- **FunctionManager:** eingebettet über
  [`function_manager_view`](function_manager_view.md).

## Zugehörige Tests

- `tests/test_effect_layer_editor.py` — Layer-Liste + Parameter.

## Quelle (file:line)

- `src/ui/views/effect_layer_editor.py:15` — Klasse `EffectLayerEditor`
- `src/ui/views/effect_layer_editor.py:201` — Auskoppeln in großes Fenster
