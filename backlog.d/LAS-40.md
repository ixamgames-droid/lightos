ID: LAS-40
Prioritaet: P2
Status: todo
Titel: Rückfrage „LASER NOT-AUS lösen?“ nimmt die Knopftexte vom System statt fester deutscher Beschriftungen

**Herkunft:** Nachtrag zu UI-92, abgelegt am 14.10.2026.
**Befund:** Die Rückfrage „LASER NOT-AUS lösen?“ (`src/ui/laser_notaus.py`, `QMessageBox.warning`) übernimmt die Beschriftungen „Ja“ und „Abbrechen“ vom Betriebssystem. UI-92 hat feste deutsche Knopftexte nur für die Fragen des Hauptfensters eingeführt. Je nach System und Sprache heißen die Knöpfe hier also anders als in der Anleitung, und ein bloßes „Ja“ sagt an einer sicherheitsrelevanten Stelle nicht, was es auslöst.
**Nachstellen:** LASER NOT-AUS auslösen und danach lösen wollen — die Rückfrage zeigt die Knopftexte des Systems; auf einem System mit anderer Sprache oder anderem Desktop weichen sie von der Anleitung ab.
**Fertig, wenn:** die Rückfrage feste, eindeutige Knopftexte trägt (z. B. „NOT-AUS lösen“ und „Abbrechen“), die Vorgabe „Abbrechen“ ist (Eingabetaste und Escape lösen nicht), die Anleitung Laser dieselben Wörter nennt und ein Test Beschriftungen und Vorgabe prüft.
