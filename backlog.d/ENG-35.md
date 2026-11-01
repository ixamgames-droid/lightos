ID: ENG-35
Prioritaet: P2
Status: done
Status-Notiz: Befund trifft auf main nicht mehr zu: Schritt 3 (Ueberschneidungs-Hinweis) ist als ENG-39 geliefert (PR #1123, src/core/engine/ueberschneidung.py), Schritt 5 (Laeufer ueber Untergrund) als ENG-42 (PR #1128, Haken „Dunkle Lampen durchlassen“ im Matrix-Editor); beide done, Anleitung Prioritaeten Abschnitt 7/8 beschreibt beides bereits. Schritte 1, 2, 4 geliefert. Rest liegt in eigenen Items: Bilder -> DOC-73, Restpunkte des Hinweises -> ENG-41, Farbe/Konsolen-Parameter beim Durchlassen -> ENG-42-Notiz.

**Schritt 4 (aus der alten Statusspalte, damit nichts verloren geht):** Spalte „Verdeckt“ im Reiter Prioritaeten (PR #1124): live „verdeckt von X auf n Geraeten“, X = Effekt/Cueliste/Programmer/Snap, Modify verdeckt nie; Protokoll nur bei sichtbarem Reiter, einmal je Takt und Universum eingehaengt, Aufwand waechst nicht mit Funktionen x Universen; Buehnen-Show 80 Geraete/3 Universen: Looks +1,0…+3,3 % Frame-Zeit, Funktionstakt allein 16 Univ./100 Fkt. +0,85 ms, 32/200 +1,6 ms (Budget 22,7 ms), aus unveraendert; Tests `tests/test_eng35_wer_gewinnt.py`, `tests/test_eng35_wer_gewinnt_ansicht.py`.
