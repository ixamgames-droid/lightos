ID: ENG-41
Prioritaet: P3
Status: todo
Titel: Überschneidungs-Hinweis kennt die ausschließenden Tasten-Haken und den gemeinsamen Live-Edit-Slot nicht und zieht bei fremder Umbelegung nicht nach

**Herkunft:** Nachtrag zum Überschneidungs-Hinweis aus ENG-39, abgelegt am 14.10.2026.
**Befund:** Der gelbe Hinweis warnt, wenn zwei Funktionen dieselben Geräte bedienen und gleichzeitig laufen könnten; Exklusiv-Gruppen nimmt er davon aus. Drei weitere Regeln wirken ebenfalls ausschließend, gelten dort aber nicht als Exklusiv-Gruppe: der Tasten-Haken „Andere Funktionen stoppen (nur diese aktiv)“, der Tasten-Haken „Andere Effekte auf denselben Geräten stoppen“ und ein gemeinsamer Live-Edit-Slot. Der Hinweis erscheint in diesen Fällen, obwohl nie beide Funktionen laufen. Außerdem aktualisiert sich die Hinweiszeile nicht, wenn bei offenen Eigenschaften ein ANDERES Bedienelement umbelegt wird.
**Nachstellen:** Zwei Tasten mit Effekten auf denselben Geräten anlegen und an einer den Haken „Andere Effekte auf denselben Geräten stoppen“ setzen — die Eigenschaften zeigen weiter den gelben Hinweis. Dann die Eigenschaften der einen Taste offen lassen, die andere Taste auf eine Funktion ohne gemeinsame Geräte umbelegen — die Zeile bleibt stehen, bis der Dialog neu geöffnet wird.
**Fertig, wenn:** die drei Regeln im Hinweis berücksichtigt sind (kein Hinweis, wo das Ausschließen sicher greift) oder der Satz das Ausschließen ausdrücklich benennt, und die Hinweiszeile sich aktualisiert, sobald ein anderes Bedienelement umbelegt wird. Tests für jede der drei Regeln und für das Nachziehen.
