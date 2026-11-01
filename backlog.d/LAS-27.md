ID: LAS-27
Prioritaet: P3
Status: teils
Status-Notiz: Befund trifft auf main nicht mehr zu: seit VIZ-95 (#1186) liest _laser_payload die LAS-33-Profilangaben des EL-400RGB MK2 — Messung bei DMX alle 0: x=0.0, y=0.0 (Mitte), sx=sy=1.0 (gross); laser_color 0 ist laut Profil „bunt“ (mehrfarbig) und kommt als bunt=True, gemessene Farben (12 rot, 120 gruen …) als farbe=[r,g,b]

**Rest (nicht Teil dieses Befunds):** `laser_color` 0-1 heisst laut Profil „bunt“ (mehrfarbig); der Payload meldet `bunt: true`, `scene_src/fixtures/laser.js` wertet das aber nicht aus und zeichnet die Strahlen dann in der allgemeinen Geraetefarbe (weiss). Mehrfarbige Strahlen waeren ein eigener VIZ-Punkt. Laser-Profile OHNE LAS-33-Angaben laufen weiter ueber den Grobweg (erster Bereich = statisch, 0 = links).
