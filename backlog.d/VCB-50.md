ID: VCB-50
Prioritaet: P3
Status: todo
Titel: VC-Schieberegler im Modus „Playback (Executor)“ und feste Fernbedienung zeigen einen Pegel von aussen nicht an

**Herkunft:** WEB-16 (Sitzung A, 17.11.2026). Die Executor-Leiste zieht einen Fader-Pegel von aussen (Web, OSC, MIDI) jetzt nach. Zwei andere Anzeigen desselben Werts tun das noch nicht: (1) der VC-Schieberegler im Modus „Playback (Executor)“ (`src/ui/virtualconsole/vc_slider.py`) — dort haengen Invert/Bereich, Soft-Takeover und der MIDI-Motor am Griff, ein Nachziehen braucht deshalb eine eigene Loesung ohne Echo an den Motor; (2) die feste Fernbedienung im Browser zeigt den echten Stand der Fader nur beim Oeffnen der Seite.

**Erledigt, wenn:** beide Anzeigen einem Pegel von aussen folgen, ohne Rueckschreiben in die Engine, ohne Echo an MIDI/Web und ohne den Regler waehrend des Ziehens zu ueberschreiben; Test dazu.
