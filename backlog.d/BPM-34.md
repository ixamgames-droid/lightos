ID: BPM-34
Prioritaet: P3
Status: review
Titel: BPM-Anzeige: Taktzelle leuchtet nach Quelle „Aus" weiter gruen, obwohl der Takt 0 ist
Nach: BPM-33
Status-Notiz: Taktzellen und Beat-Punkt werden bei Takt 0 ueber den BPM-Signalpfad geloescht, verspaetete Beats verworfen, Test test_bpm34_taktzelle_aus.py

**Befund:** Seit BPM-33 setzt `SourceController.apply("off")` ueber `BPMManager.reset()` den Takt auf 0. Die Taktzellen der BPM-Anzeige (Sub-Tab „Erkennung", `src/ui/views/bpm_manager_view.py`) blieben aber auf dem letzten Schlag erleuchtet, weil sie nur in `_on_beat` umgefaerbt wurden.

**Umsetzung:** `_on_bpm` loescht bei Takt 0 alle Taktzellen, den Beat-Punkt und die Positionsanzeige (`_clear_beat_display`). Der Weg laeuft ueber das vorhandene Signal `reset()`/`turn_off()` -> BPM-Aenderung -> `_on_bpm`, ohne Polling. Zusaetzlich verwirft `_on_beat` bei Takt 0 verspaetete Beats, die der Timer-/Audio-Faden kurz vor `reset()` noch in die Ereignisschlange gelegt hatte (sonst leuchtete die Zelle sofort wieder auf). Beats eines externen Taktgebers (Audio-Detektor vor der ersten Erkennung, Beatgrid, jeweils in Auto) gelten weiter. Das VC-Widget „BPM" hat keine Taktzellen und ist nicht betroffen.

**Offen:** Die Bilder `docs/anleitung_bpm_manager/img/01_quelle_aus.png` und `02_quelle_aus_ablauf.gif` (PR #1178) zeigen noch die leuchtende Zelle und sollten nach dem Merge neu erzeugt werden.
