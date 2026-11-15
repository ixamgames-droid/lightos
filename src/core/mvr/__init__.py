"""VIZ-56: MVR (*My Virtual Rig*) — Austausch mit anderen Lichtprogrammen.

Teil 1 ist der Import, ohne Qt:

* :mod:`.sicher` — fremde ZIP- und XML-Dateien mit Grenzen lesen (nie auf die
  Platte entpacken, keine DTD/Entities, Groessen- und Verhaeltnisgrenzen).
* :mod:`.lesen` — ``.mvr`` und eingebettete ``.gdtf`` -> Dataclasses.
* :mod:`.achsen` — MVR-Matrix (mm, Z oben) <-> LightOS-Position (m, Y oben)
  und Drehung (Grad, Euler XYZ wie Three.js), hin und zurueck.
* :mod:`.gdtf_profil` — ein unbekannter GDTF-Typ als Profil-Payload fuer die
  Bibliothek (Attribute auf die LightOS-Namen abgebildet).
* :mod:`.importieren` — Plan (Zuordnung, Adressen, Konflikte) und Anwenden
  als EIN Rueckgaengig-Schritt, alles oder nichts.
"""
