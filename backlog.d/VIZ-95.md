ID: VIZ-95
Prioritaet: P2
Status: todo
Nach: VIZ-94
Titel: 3D: echte Lasermuster statt vier grober Formen (Kreis, Stern, Strich … aus den Profil-Bereichen)

**Herkunft:** Wunsch des Projektinhabers, 08.10.2026 abends; von Sitzung A auf der Tafel belegt (Zweig `feature/viz95-lasermuster-3d`, ohne Commits), aber nie als Backlog-Zeile angelegt — nachgetragen beim Abgleich verlorener IDs am 20.10.2026.
**Befund:** `src/ui/visualizer/scene_src/fixtures/laser.js` kennt nur vier grobe Formen (`LASER_FORMEN`: Fächer, Einzelstrahl, Strahlenkranz, Fläche), grob abgeleitet aus Musterbank/Musterauswahl (VIZ-79, PR #944). Was der echte Laser zeigt (z. B. die am Gerät gemessenen Muster des EL-400RGB MK2, Profil-Notizen FM-68), sieht man im 3D nicht.
**Ziel:** echte Vektorformen (Kreis, mehrere Kreise, Strich, gepunkteter Kreis, Dreieck, Quadrat, Stern, pulsierender Kreis …) als Strahlenfächer/-kegel bzw. Projektion an Wand und Nebel, gesteuert aus den Profil-Bereichsnamen der Musterauswahl (Profilangaben LAS-33) plus Farbe, Größe (Richtung aus dem Profil, beim EL-400 ist 0 = groß), X/Y und Dynamik (wachsen, drehen, scannen). Leistung: Rig einmal je Gerät, Updates ohne Neuanlage. Zusammen mit LAS-27 (EL-400 steht bei Default links und strahlt weiß). Empfehlung aus der VIZ-96-Planung (09.10.): geometrisch bleiben (Linien/Strahlenkegel); Muster an der Wand erst, wenn verlangt, über einen eigenen projektiven Kanal.
**Fertig, wenn:** ein EL-400 mit „Statische Muster“ im 3D für mindestens die gemessenen Grundmuster die richtige Form in Farbe, Größe und Lage zeigt; unbekannte Muster fallen sichtbar auf eine neutrale Form zurück; Szenen-Test mit Vorher/Nachher-Bild; keine Bildraten-Einbuße auf Stufe Niedrig.
