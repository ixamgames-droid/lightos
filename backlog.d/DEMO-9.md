ID: DEMO-9
Prioritaet: P3
Status: todo
Titel: Demo-Show „Showcase Club-Nacht“: „Laser Farbe gruen“ und 2D-Beschriftung „MH 9“ statt Gerätename

**Herkunft:** Sichtprüfung von main im Sandkasten (offscreen, Demo-Show „Showcase Club-Nacht“), 19.10.2026, Sitzung A.
**Befund:** (1) Funktionsnamen „Laser Farbe gruen“ (Schlüssel als Anzeigename, `tools/build_showcase_club.py` ~Z. 108/299), dieselbe Show enthält auch „Laser grün“. (2) Die 2D-Bühne beschriftet Moving Heads mit „MH 9“…„MH 12“ und die Leiste mit „PARBAR 13“, die Geräteliste nennt sie „Wash 1/2“, „Spot 1/2“, „LED-Leiste“ — prüfen, ob das am Demo-Bau (Bühnen-Label) oder an der Ansicht liegt.
**Fertig, wenn:** Anzeigenamen mit Umlaut; 2D-Beschriftung folgt dem Gerätenamen (oder die Abweichung ist begründet); Demo-Shows neu gebaut, `test_demo8_demoshows` grün.
