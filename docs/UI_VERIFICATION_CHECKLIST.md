# UI-Verifikationscheckliste

Aktiver maschineller Nachweis: `tests/test_ui_smoke_enumerated.py` inventarisiert
no-arg Views und die gesamte VC-Registry; gezielte Editorpfade liegen in den
jeweiligen `tests/test_*_editor.py`-Dateien. Reale UI-Abnahmen werden zusätzlich
im Backlog-/Changelog-Durchlauf dokumentiert.

## Views

| Bestand | Nachweis |
|---|---|
| Alle `src/ui/views/*.py`-Views | `tests/test_ui_smoke_enumerated.py` oder gezielter View-Test |
| Audio, Carousel, Collection, Effect Layer, Scene, Script | jeweilige `test_*_editor.py` |
| MIDI, Output | `test_midi_view.py`, `test_output_view.py` |
| Verbleibende Hauptviews | `tests/test_views.py` + enumerierender Smoke |

## Virtual Console

| Bestand | Nachweis |
|---|---|
| Alle 19 `WIDGET_REGISTRY`-Widgets | `tests/test_ui_smoke_enumerated.py`: Konstruktion und `to_dict()`/`apply_dict()` |
| Interaktionen/Bindungen | spezialisierte `tests/test_vc_*.py`-Dateien |

## Aktualisierungsregel

Ein neues View-Modul oder VC-Widget muss entweder vom enumerierenden Smoke erfasst
sein oder einen begründeten Skip mit eigenem Testpfad erhalten. QA-13 ergänzt darauf
die Tooltip-/Label-Prüfung.

## Tooltip-/Label-Coverage (QA-13)

Jeder no-arg `*View` wird headless gebaut und auf `QAbstractButton`s mit leerem
`text()` **und** leerem `toolTip()` geprüft. Report + Baseline:
[`UI_TOOLTIP_COVERAGE.md`](UI_TOOLTIP_COVERAGE.md), Gate:
`tests/test_tooltip_coverage.py` (rot bei NEUEN textlosen Buttons ohne Tooltip).
Report neu erzeugen: `python tools/audit_tooltip_coverage.py`.

<!-- BEGIN GENERATED: ui_verification_checklist -->
<!-- Auto-generiert von tools/ui_verification_checklist.py — NICHT von Hand editieren. -->

## Maschinen-Inventar (QA-12)

Erzeugt von `tools/ui_verification_checklist.py`, abgesichert durch
`tests/test_ui_verification_checklist.py`. Jede Zeile wird headless
(offscreen) gebaut; die Spalten unten sind der geprueft protokollierte
Ist-Zustand. Eine NEUE no-arg View oder ein NEUES `WIDGET_REGISTRY`-Widget
fehlt zunaechst hier und macht das Gate rot (Schutz gegen Doku-Drift).

Spalten: **headless** = ohne Argumente offscreen baubar · **Tooltip/Label** = mind. ein beschrifteter Text/Tooltip · **Aktion/Signal** = Button/`QAction`/Klassen-`Signal` vorhanden · **Regressionstest** = abdeckende Testdatei · **Doc** = Komponentenseite · **Verifikationspfad** = ausfuehrbarer `pytest`-Testname ODER `manuell`.

**Stand:** 24 no-arg Views (24 headless baubar), 19 VC-Widgets (19 headless baubar).

### Views (`src/ui/views/*.py`, no-arg `*View`)

| Modul | Klasse | headless | Tooltip/Label | Aktion/Signal | Regressionstest | Doc | Verifikationspfad |
|---|---|:--:|:--:|:--:|---|---|---|
| `audio_input_view.py` | `AudioInputView` | ja | ja | ja | `tests/test_audio_input_view.py` | `docs/components/views/audio_input_view.md` | `test_every_no_arg_view_builds` |
| `bpm_generator_view.py` | `BpmGeneratorView` | ja | ja | ja | `tests/test_ui_smoke_enumerated.py` | `docs/components/views/bpm_generator_view.md` | `test_every_no_arg_view_builds` |
| `bpm_manager_view.py` | `BpmManagerView` | ja | ja | ja | `tests/test_ui_smoke_enumerated.py` | `docs/components/views/bpm_manager_view.md` | `test_every_no_arg_view_builds` |
| `channel_groups_view.py` | `ChannelGroupsView` | ja | ja | ja | `tests/test_ui_smoke_enumerated.py` | `docs/components/views/channel_groups_view.md` | `test_every_no_arg_view_builds` |
| `curve_library_view.py` | `CurveLibraryView` | ja | ja | ja | `tests/test_curve_library_view.py` | `docs/components/views/curve_library_view.md` | `test_every_no_arg_view_builds` |
| `dmx_monitor_view.py` | `DmxMonitorView` | ja | ja | ja | `tests/test_ui_smoke_enumerated.py` | `docs/components/views/dmx_monitor_view.md` | `test_every_no_arg_view_builds` |
| `efx_view.py` | `EfxView` | ja | ja | ja | `tests/test_ui_smoke_enumerated.py` | `docs/components/views/efx_view.md` | `test_every_no_arg_view_builds` |
| `fixture_group_view.py` | `FixtureGroupView` | ja | ja | ja | `tests/test_ui_smoke_enumerated.py` | `docs/components/views/fixture_group_view.md` | `test_every_no_arg_view_builds` |
| `function_manager_view.py` | `FunctionManagerView` | ja | ja | ja | `tests/test_ui_smoke_enumerated.py` | `docs/components/views/function_manager_view.md` | `test_every_no_arg_view_builds` |
| `laser_view.py` | `LaserView` | ja | ja | ja | `tests/test_laser_view.py` | `docs/components/views/laser_view.md` | `test_every_no_arg_view_builds` |
| `live_view.py` | `LiveView` | ja | ja | ja | `tests/test_ui_smoke_enumerated.py` | `docs/components/views/live_view.md` | `test_every_no_arg_view_builds` |
| `midi_view.py` | `MidiView` | ja | ja | ja | `tests/test_midi_view.py` | `docs/components/views/midi_view.md` | `test_every_no_arg_view_builds` |
| `music_view.py` | `MusicView` | ja | ja | ja | `tests/test_ui_smoke_enumerated.py` | `docs/components/views/music_view.md` | `test_every_no_arg_view_builds` |
| `output_view.py` | `OutputView` | ja | ja | ja | `tests/test_output_view.py` | `docs/components/views/output_view.md` | `test_every_no_arg_view_builds` |
| `palette_view.py` | `PaletteView` | ja | ja | ja | `tests/test_ui_smoke_enumerated.py` | `docs/components/views/palette_view.md` | `test_every_no_arg_view_builds` |
| `patch_view.py` | `PatchView` | ja | ja | ja | `tests/test_ui_smoke_enumerated.py` | `docs/components/views/patch_view.md` | `test_every_no_arg_view_builds` |
| `playback_view.py` | `PlaybackView` | ja | ja | ja | `tests/test_ui_smoke_enumerated.py` | `docs/components/views/playback_view.md` | `test_every_no_arg_view_builds` |
| `preset_browser_view.py` | `PresetBrowserView` | ja | ja | ja | `tests/test_ui_smoke_enumerated.py` | `docs/components/views/preset_browser_view.md` | `test_every_no_arg_view_builds` |
| `programmer_view.py` | `ProgrammerView` | ja | ja | ja | `tests/test_ui_smoke_enumerated.py` | `docs/components/views/programmer_view.md` | `test_every_no_arg_view_builds` |
| `rgb_matrix_view.py` | `RgbMatrixView` | ja | ja | ja | `tests/test_ui_smoke_enumerated.py` | `docs/components/views/rgb_matrix_view.md` | `test_every_no_arg_view_builds` |
| `show_manager_view.py` | `ShowManagerView` | ja | ja | ja | `tests/test_ui_smoke_enumerated.py` | `docs/components/views/show_manager_view.md` | `test_every_no_arg_view_builds` |
| `simple_desk.py` | `SimpleDeskView` | ja | ja | ja | `tests/test_ui_smoke_enumerated.py` | — | `test_every_no_arg_view_builds` |
| `snapshots_view.py` | `SnapshotsView` | ja | ja | ja | `tests/test_ui_smoke_enumerated.py` | `docs/components/views/snapshots_view.md` | `test_every_no_arg_view_builds` |
| `virtual_console_view.py` | `VirtualConsoleView` | ja | ja | ja | `tests/test_ui_smoke_enumerated.py` | `docs/components/views/virtual_console_view.md` | `test_every_no_arg_view_builds` |

### Virtual Console (`WIDGET_REGISTRY`)

| Registry-Typ | Modul | headless | Tooltip/Label | Aktion/Signal | Regressionstest | Doc | Verifikationspfad |
|---|---|:--:|:--:|:--:|---|---|---|
| `VCBpmDisplay` | `vc_bpm_display.py` | ja | nein | ja | `tests/test_ui_smoke_enumerated.py` | `docs/components/vc/vc_bpm_display.md` | `test_every_virtual_console_widget_roundtrips` |
| `VCBusSelector` | `vc_bus_selector.py` | ja | nein | ja | `tests/test_ui_smoke_enumerated.py` | `docs/components/vc/vc_bus_selector.md` | `test_every_virtual_console_widget_roundtrips` |
| `VCButton` | `vc_button.py` | ja | nein | ja | `tests/test_ui_smoke_enumerated.py` | `docs/components/vc/vc_button.md` | `test_every_virtual_console_widget_roundtrips` |
| `VCColor` | `vc_color.py` | ja | nein | ja | `tests/test_ui_smoke_enumerated.py` | `docs/components/vc/vc_color.md` | `test_every_virtual_console_widget_roundtrips` |
| `VCColorList` | `vc_color_list.py` | ja | nein | ja | `tests/test_vc_color_list.py` | `docs/components/vc/vc_color_list.md` | `test_every_virtual_console_widget_roundtrips` |
| `VCCueList` | `vc_cuelist.py` | ja | ja | ja | `tests/test_ui_smoke_enumerated.py` | `docs/components/vc/vc_cuelist.md` | `test_every_virtual_console_widget_roundtrips` |
| `VCEffectColors` | `vc_effect_colors.py` | ja | nein | ja | `tests/test_vc_effect_colors.py` | `docs/components/vc/vc_effect_colors.md` | `test_every_virtual_console_widget_roundtrips` |
| `VCEffectDisplay` | `vc_effect_display.py` | ja | nein | ja | `tests/test_vc_effect_display.py` | `docs/components/vc/vc_effect_display.md` | `test_every_virtual_console_widget_roundtrips` |
| `VCEffectEditor` | `vc_effect_editor.py` | ja | ja | ja | `tests/test_vc_effect_editor.py` | — | `test_every_virtual_console_widget_roundtrips` |
| `VCEncoder` | `vc_encoder.py` | ja | nein | ja | `tests/test_vc_encoder.py` | `docs/components/vc/vc_encoder.md` | `test_every_virtual_console_widget_roundtrips` |
| `VCFrame` | `vc_frame.py` | ja | nein | ja | `tests/test_ui_smoke_enumerated.py` | — | `test_every_virtual_console_widget_roundtrips` |
| `VCLabel` | `vc_label.py` | ja | nein | ja | `tests/test_ui_smoke_enumerated.py` | `docs/components/vc/vc_label.md` | `test_every_virtual_console_widget_roundtrips` |
| `VCMultiLiveEditor` | `vc_multi_live_editor.py` | ja | ja | ja | `tests/test_vc_multi_live_editor.py` | — | `test_every_virtual_console_widget_roundtrips` |
| `VCSlider` | `vc_slider.py` | ja | nein | ja | `tests/test_ui_smoke_enumerated.py` | `docs/components/vc/vc_slider.md` | `test_every_virtual_console_widget_roundtrips` |
| `VCSongInfo` | `vc_song_info.py` | ja | nein | ja | `tests/test_vc_song_info.py` | `docs/components/vc/vc_song_info.md` | `test_every_virtual_console_widget_roundtrips` |
| `VCSpeedDial` | `vc_speedial.py` | ja | nein | ja | `tests/test_ui_smoke_enumerated.py` | `docs/components/vc/vc_speedial.md` | `test_every_virtual_console_widget_roundtrips` |
| `VCStepper` | `vc_stepper.py` | ja | nein | ja | `tests/test_vc_stepper.py` | `docs/components/vc/vc_stepper.md` | `test_every_virtual_console_widget_roundtrips` |
| `VCTempoBusController` | `vc_tempo_bus_controller.py` | ja | nein | ja | `tests/test_vc_tempo_bus_controller.py` | `docs/components/vc/vc_tempo_bus_controller.md` | `test_every_virtual_console_widget_roundtrips` |
| `VCXYPad` | `vc_xypad.py` | ja | nein | ja | `tests/test_ui_smoke_enumerated.py` | `docs/components/vc/vc_xypad.md` | `test_every_virtual_console_widget_roundtrips` |

<!-- END GENERATED: ui_verification_checklist -->
