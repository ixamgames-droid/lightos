ID: CDX-74
Prioritaet: P2
Status: review
Titel: Codex-Ernte: Bildschirmtastatur und Touch-Masse (Abbrechen stellt das textEdited-Modell nicht zurueck, lange Feldinhalte blasen die Tastatur ueber den Bildschirm, Snap-Editor-Tabellen im Touch-Modus unten abgeschnitten) und abgeschnittene Geraetenamen in der Buehnen-Liste

**Herkunft:** Neuheiten-Audit von Sitzung A am 15.11.2026 (Codex-Befunde zu PR 1276/1278, von einem zweiten Pruefer bestaetigt) plus Befund von Sitzung B am Windows-Touchscreen (15.11.2026).

**Befund 1 (Abbruch, textEdited):** `Bildschirmtastatur._abbrechen_intern` stellte den alten Text nur mit `setText()` her; das sendet kein `textEdited`. Wer sein Modell nur an `textEdited` haengt (Sperrzonen-Planer, Zonenname), behielt nach Abbruch oder Tipp daneben den abgebrochenen Text, waehrend das Feld den alten zeigte. **Behebung:** nach dem Zuruecksetzen wird `textEdited` mit dem alten Text gesendet (alle Abbruchpfade, auch `hideEvent`); ohne Aenderung wird nichts gesendet, „Fertig“ bleibt unveraendert.

**Befund 2 (langer Feldinhalt):** die Anzeige-Zeile der Tastatur war ein ungekuerztes QLabel; ein ~400 Zeichen langer Pfad machte die Tastatur rund 4000 px breit, Tasten und Fertig/Abbruch lagen ausserhalb des Bildschirms. **Behebung:** die Anzeige bestimmt die Breite nicht mehr mit (SizePolicy Ignored) und kuerzt links, damit das Ende (Cursor) sichtbar bleibt; neu bemessen bei jeder Groessenaenderung.

**Befund 3 (Snap-Editor im Touch-Modus):** die Typ-Tabellen sind auf Inhaltshoehe fuer 30-px-Zeilen fixiert; `_touch_masse` hebt die Zeilen beim Zeigen auf 44 px, die feste Hoehe blieb, untere Zeilen waren abgeschnitten (kein Bildlauf). **Behebung:** neue Hilfe `touch_keyboard.inhalt_hoehe_fixieren()` markiert solche Tabellen (`inhalt_hoehe`); `_touch_masse` bemisst sie nach dem Anheben neu. Der Snap-Editor nutzt die Hilfe; mit der Maus bleibt die Hoehe wie bisher.

**Befund 4 (Buehnen-Liste, Sitzung B):** links im Reiter „Bühne“ stand im Touch-Modus „[00…R 1“ statt „[001] PAR 1“. Ursache: die Leiste ist fest 190 px breit; Touch-Bildlaufleiste 24 px, 2 x 6 px Eintrags-Innenabstand, 2 x 20 px Einzug (Universe-Ordner + Geraet) und das Icon liessen dem Text ~74 px, mit breiterer Ersatzschrift (Windows ohne Roboto Condensed) zu wenig; die mittige Kuerzung (QOL-03) schnitt dabei die Geraetenummer an. **Behebung:** Einzug 12 statt 20 px, seitlicher Eintrags-Innenabstand 2 px (die Touch-Zeilenhoehe bleibt), und ein Delegat, der das `[NNN] `-Praefix nie kuerzt und nur den Namen mittig kuerzt (der unterscheidende Schwanz aus QOL-03 bleibt); andere Zeilen kuerzt Qt rechts. Textflaeche im Touch-Modus jetzt 98 px (vorher 74), mit der Maus 110 px; Tooltip mit Vollname wie bisher. Gilt auch fuer dieselbe Liste in der Gruppen-Ansicht (`FixtureGroupView`).

**Tests:** `tests/test_cdx74_tastatur_touch.py` (8, davon 4 ohne Fix rot), `tests/test_cdx74_buehne_liste.py` (4, ohne Fix 4 rot); `tests/test_fixture_list_tooltip.py` auf den Delegaten angepasst.
