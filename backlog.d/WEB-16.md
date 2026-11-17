ID: WEB-16
Prioritaet: P2
Status: todo
Titel: Executor-Fader aus der Web-Fernbedienung wird in der Executor-Leiste nicht nachgezogen

Live-Durchlauf QA-LIVE (17.11.2026): POST /api/executor/1/fader mit level 0,5 setzt die Engine auf 0,5 (/api/status meldet 0,5), der Fader von Executor 1 in Playback → Executor-Leiste bleibt aber sichtbar auf 100 % stehen (auch Sekunden spaeter). Ursache laut Code: die Leiste setzt den Regler nur beim Aufbau/Konfigurieren/REFRESH_ALL (playback_view _sync_fader_for_function), nicht bei einer Aenderung von aussen. Folge: Pult zeigt einen falschen Pegel; die naechste Beruehrung des Reglers springt. Erledigt, wenn ein Fader-Wert aus Web/OSC/MIDI ohne Rueckkopplung im Regler erscheint (ohne den Wert waehrend des Ziehens zu ueberschreiben) und ein Test das belegt. Pruefen, ob VC-Cuelisten-Fader dasselbe Verhalten zeigen.
