ID: LAS-43
Prioritaet: P3
Status: todo
Titel: Laser ohne Profilangaben: ein Regler bewegt mehrere Kanäle (EL-230: Betriebsart und Muster nicht getrennt stellbar)

**Herkunft:** großer Bedientest QA-96 (Befund QA96-13, am Quelltext bestätigt), 11./12.10.2026, Sitzung A; der Befund bekam keine eigene Zeile — nachgetragen am 20.10.2026.
**Befund:** Bei einem Laser ohne Profilangaben (Beispiel: EL-230RGB MK2 aus einem älteren Import) schreibt der Rückfall-Laser-Reiter je Attribut auf alle zugehörigen Kanäle (`src/ui/views/laser_view.py`). Der Regler „Mode“ ändert dadurch Kanal 1 und 2 zugleich; Betriebsart und Muster lassen sich nicht getrennt stellen. Für den EL-230 hohe, insgesamt mittlere Schwere.
**Fertig, wenn:** im Rückfall-Reiter eine Zeile je Kanal statt je Attribut; „Mode“ nie in einer zugeklappten Gruppe; „Mustergruppe“ nur, wenn das Gerät zwei Gruppen hat; Test mit einem Profil, dessen zwei Kanäle dasselbe Attribut tragen (rot ohne die Änderung). Gilt auch für den neuen Laser-Reiter (LAS-34), der den alten als Rückfall behält.
