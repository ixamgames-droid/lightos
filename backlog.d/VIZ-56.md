ID: VIZ-56
Prioritaet: P3
Status: teils
Status-Notiz: Teil 1 (Import) fertig: Datei -> „MVR-Datei importieren …“ liest .mvr samt eingebetteter GDTF (src/core/mvr/, ohne neue Abhaengigkeit, nichts wird entpackt, DTD/Entities/Zip-Slip/Zip-Bomben abgelehnt), ordnet ueber Hersteller+Modell+Kanalzahl zu, legt unbekannte Typen als Profil „neu aus GDTF“ an (Herkunft mvr/gdtf), meldet Adresskonflikte (ueberspringen/freie Adresse), setzt Positionen/Drehungen gemessen (mm/Z-oben -> m/Y-oben, Euler XYZ), ein Rueckgaengig-Schritt, alles oder nichts; Anleitung docs/anleitung_mvr; Tests test_viz56_mvr_import. Offen: Traversen/Fokuspunkte uebernehmen, (2) Export, (3) eigene Profile nach GDTF, Probe mit einer echten fremden .mvr.
