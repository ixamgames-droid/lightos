# Engine — Funktionstypen (`FunctionType`)

Diese Referenz beschreibt **jeden** Wert des `FunctionType`-Enums als eigene
Funktions-Klasse: Zweck/Verhalten, Parameter (Dataclass-Felder + `set_param`-Keys),
Render-Beitrag, Serialisierung, gekoppelte Module, Tests und Code-Quelle.

Das Enum ist definiert in `src/core/engine/function.py:13`. Die abstrakte Basis
`Function` (`src/core/engine/function.py:61`) liefert Lifecycle
(`start`/`stop`/`release`), die Ein-/Ausblend-Hüllkurve (`env_factor`) und die
gemeinsame `to_dict`-Basis (`id`, `name`, `type`, `intensity`, `speed`, `folder`,
`priority`, `env_*`, `tempo_*`, `align_on_start`). Der zentrale Renderer ruft
pro Frame (44 Hz) `FunctionManager.tick` (`src/core/engine/function_manager.py:374`),
das je Funktion `write()` aufruft und `intensity`/`env_factor` als Multiplikator
über alle geschriebenen Kanäle anwendet. Deserialisiert wird typ-abhängig in
`FunctionManager.from_dict` (`src/core/engine/function_manager.py:490`).

## Typen im Überblick

| Typ (`FunctionType`) | Doc | Klasse | Quelle |
|---|---|---|---|
| `Scene` | [scene.md](scene.md) | `Scene` | `src/core/engine/scene.py:20` |
| `Chaser` | [chaser.md](chaser.md) | `Chaser` | `src/core/engine/chaser.py:29` |
| `Sequence` | [sequence.md](sequence.md) | `Sequence` | `src/core/engine/sequence.py:34` |
| `Collection` | [collection.md](collection.md) | `Collection` | `src/core/engine/collection.py:11` |
| `Show` | [show.md](show.md) | `Show` | `src/core/engine/show_engine.py:48` |
| `EFX` | [efx.md](efx.md) | `EfxInstance` | `src/core/engine/efx.py:97` |
| `RGBMatrix` | [rgbmatrix.md](rgbmatrix.md) | `RgbMatrixInstance` | `src/core/engine/rgb_matrix.py:411` |
| `Audio` | [audio.md](audio.md) | `AudioFunction` | `src/core/engine/audio_func.py:12` |
| `Script` | [script.md](script.md) | `ScriptFunction` | `src/core/engine/script_func.py:22` |
| `MappedChannelChange` | [mappedchannelchange.md](mappedchannelchange.md) | `MappedChannelChange` | `src/core/engine/mapped_channel.py:171` |

## Wissenswerte Sonderfälle

- **`Script` teilt den `function_type`.** `ScriptFunction.function_type` ist aus
  Speicher-Kompatibilität `FunctionType.Scene`; die Klasse taggt in `to_dict`
  jedoch `"type": "Script"` und wird in `from_dict` über genau diesen String
  dispatcht. Der Enum-Wert `Script` existiert also, wird aber nicht über das
  Klassen-Attribut, sondern über den serialisierten Typ-String erreicht.
- **`EFX` teilt seinen Typ-Tag mit zwei weiteren Effektklassen.**
  `LayeredEffect` und `Carousel` serialisieren ebenfalls als `"EFX"`. Der
  Loader unterscheidet anhand der Keys (`motion`/`speed_hz` → `EfxInstance`,
  `layers` → `LayeredEffect`, `pattern` → `Carousel`). Diese Doc behandelt den
  Pan/Tilt-`EfxInstance` (der eigentliche `FunctionType.EFX`-Bewegungseffekt).
- **Speed-Namensfalle.** Bei `EFX` und `RGBMatrix` ist der eigene
  Animations-`set_param`-Key `"speed"`, der jedoch auf `speed_hz` (EFX) bzw.
  `matrix_speed` (Matrix) mappt — **nicht** auf den generischen
  `Function.speed`-Master. Serialisiert werden die Felder als `speed_hz` /
  `matrix_speed`.
