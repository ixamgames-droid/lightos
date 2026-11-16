ID: STAB-42
Prioritaet: P2
Status: todo
Titel: Qt-Ereignisse waehrend des Abbaus: Python-Overrides greifen auf schon geleerte Attribute zu

**Herkunft:** UI-143 (Raum-Pad), Sitzung A, 16.11.2026. **Befund:** Wird ein Widget von Pythons Speicherbereinigung abgebaut, sind seine Python-Attribute schon geleert, wenn Qt beim Zerstoeren noch Ereignisse schickt (hideEvent, closeEvent, changeEvent, leaveEvent, focusOutEvent). Greift das Override dann auf `self.<attribut>` zu, entsteht AttributeError — und die Ausnahme landet in dem Code, der gerade laeuft, zum Beispiel im paintEvent eines anderen Widgets. Dessen Maler bleibt offen („QPaintDevice: Cannot destroy paint device that is being painted“), danach stuerzt der Prozess beim Aufraeumen nativ ab. Beim Raum-Pad belegt und dort behoben (UI-143); in `src/ui` gibt es 43 Overrides von hideEvent/closeEvent/changeEvent. Betroffen sind vor allem Widgets ohne Qt-Elternteil, die Python selbst abraeumt — also Tests (Verdacht: ein Teil der roten Segmente ohne FAILED-Zeile, QA-24) und einzelne Dialoge/Popouts.

**Zu tun:** die Overrides durchsehen (welche greifen ungeschuetzt auf Attribute zu), einen kleinen gemeinsamen Schutz bauen (nur im Abbau still, echte Fehler bleiben laut), anwenden, Waechtertest. **Fertig, wenn:** kein Override dieser Ereignisse in `src/ui` im Abbau-Zustand eine Ausnahme wirft (Test mit geleertem Objekt je Klasse, soweit offscreen baubar) und ein Waechter neue Stellen meldet.
