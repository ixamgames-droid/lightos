ID: LAS-46
Prioritaet: P3
Status: review
Titel: Laser-Reiter: Kopf der Spalte „Vorschau & Position“ links abgeschnitten
Status-Notiz: Hinweis steht jetzt unter der Ueberschrift und darf umbrechen; Test prueft Textbreite gegen Label-Breite bei Schrift x1/x1.25/x1.5

**Herkunft:** Sichtprobe Sitzung D, Windows 11 x64, 100/125/150 %, 29.10.2026: „VORSCHAU & POSITIO…“ und „zeigt den ersten von 2 Laser…“ abgeschnitten, Label 138 px breit, braucht 143–149 px.
**Ursache:** Ueberschrift und Hinweis teilten sich in der fest 280 px breiten Spalte eine Zeile; offscreen gemessen bekamen beide 138 px, brauchten 148 bzw. 152 px.
**Behoben:** `src/ui/views/laser_view.py` — Hinweis eigene Zeile unter der Ueberschrift, `setWordWrap(True)`. Spaltenbreite unveraendert.
**Tests:** neu `tests/test_las46_laser_spaltenkopf.py` (9 Faelle: drei Hinweistexte x Schrift 11/14/17 px); ohne Fix 8 von 9 rot.
