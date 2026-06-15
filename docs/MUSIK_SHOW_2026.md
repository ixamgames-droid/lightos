# Musik-Show 2026 — Auto-Lichtshow zur Musik (BPM-synchron)

`shows/Musik_Show_2026.lshow` · Generator `tools/build_musik_show_2026.py` ·
Tests `tests/test_musik_show_2026.py`, `tests/test_music_show_director.py`,
`tests/test_cue_stack_beat_sync.py`.

Rig: 8× RGBW-PAR (ZQ01424, @1..57) + 2× Moving Head (ZQ02001, @65/@76) + Akai APC mini.

## Was sie kann

Drückst du im In-App-Player **▶** (Tab „Musik", oder der Play-Pad auf Bank 1), läuft
**automatisch eine Lichtshow mit** — und ihre Effekte **schalten im BPM-Takt weiter**.
Pause/Stop beendet sie wieder. Das übernimmt der `MusicShowDirector`
(`src/core/audio/music_show.py`), gesteuert über `state.music_autoshow`.

**BPM-Quelle** (in dieser Reihenfolge): VirtualDJ → OS2L (Menü „Ausgabe → OS2L-Server"),
sonst Tap-Tempo / Audio-Eingang, sonst die **Nominal-BPM des Tracks** als Fallback
(damit auch ohne VirtualDJ sofort etwas im Takt läuft).

## Auto-Show-Kopplung

Im Tab „Musik" gibt es den Schalter **„🎬 Lichtshow automatisch zur Musik starten"**.
Ist er an, startet ▶ die in der Show hinterlegten Funktionen
(`state.music_autoshow["function_ids"]`) — standardmäßig:

- **Drop (Beat)** — beat-getriggerter PAR-Chaser (`audio_triggered`), wechselt alle ½ Takte
  die Farbe/den Look → die Effekte „schalten durch" zur Musik.
- **MH Orbit** — kontinuierliche Moving-Head-Kreisbahn.

Der Schalter wird in der Show gespeichert (`music_autoshow.enabled`). Pro Show kann also
hinterlegt sein, ob und welche Auto-Show beim Play startet.

## Die 5 Banks (APC-SCENE = Bank = Playback-Seite)

| Bank | Inhalt |
|---|---|
| **1 Auto-Show** | Songanzeige + Transport (◄◄ ▶/❚❚ ►► · Tap · Musik-BPM). PAR-Sektionen **Warmup/Build/Drop/Chill** (beat-getriggert, lösen einander sauber ab) + MH-Formen **Orbit/Acht/Weit**. Looks zum Einfrieren, Gruppen/Flashes. Fader: Master/FX-Speed/FX-Master/PAR-Dim/MH-Dim. |
| **2 Standard** | 16 **anpassbare** Farb-Kacheln (Programmer) · 8 Standard-Matrix-Looks · Chases + Color-Chases · volle Fader (Speed/Master/Param/Dim). Die „einfache" Bank zum Selber-Schrauben. |
| **3 Meine Shows** | 4 Cuelisten an Executoren: **Aufwärmen** (Zeit), **Drop-Sequenz** (Beat-Sync, 1 Takt), **Farb-Reise** (Beat-Sync, 2 Takte), **MH-Fahrt** (Zeit). GO/Flash-Pads, Dimmer-Fader, Tempo-Drehrad. Beat-Sync-Listen laufen taktgenau zur Musik. |
| **4 MH-Stage** | XY-Pad zum freien Zielen (16-bit). **Orbit-Pads** richten die Bewegung auf eine Bühnen-Zone aus (Mitte/Links/Rechts/Publikum/Hoch). Relative Formen orbiten das aktuelle Ziel. Spiegeln/Gegenläufig/Neustart. |
| **5 Musik** | Songanzeige + große Transport-Reihe + Farb-Kacheln/Looks. Der Auto-Show-Schalter sitzt im Tab „Musik". |

## Wie der Takt-Sync technisch läuft

- **Chaser** mit `audio_triggered=True`: der `BPMManager` ruft pro Beat `trigger_next_step()`;
  der Chaser schaltet nach `beats_per_step` Beats eine Stufe weiter. (Die Auto-Show-Sektionen.)
- **Cuelisten** mit `beat_sync=True` (neu): der `BPMManager._emit_beat()` ruft `CueStack.on_beat()`;
  die aktive Liste schaltet nach `beats_per_cue` Beats eine Cue weiter. Der Zeit-`follow`-Timer
  ist dann deaktiviert (der Beat treibt). Default aus → Alt-Shows verhalten sich unverändert.
- **Layer-getrennt schalten:** Bank-Pads nutzen `edit_slot` (`par_show` / `mh_show`), damit ein
  neuer PAR-Effekt nur den vorigen **PAR**-Effekt ablöst und den MH-Layer weiterlaufen lässt
  (kein globales `stop_all`). Der Director setzt dieselben Slots für seine gestarteten Funktionen
  (`music_autoshow["slots"]`), damit die Pads die Auto-Show sauber übernehmen.

## Neu bauen

```
venv/Scripts/python.exe tools/build_musik_show_2026.py
```

Selbst-verifizierend (Patch, Playlist, Auto-Show-Kopplung, Beat-Sync-Listen, relative EFX,
keine Widget-Überlappung). Playlist wird aus `Desktop/Musik/BP Party` aufgelöst.
