ID: STAB-35
Prioritaet: P1
Status: review
Titel: Harter Absturz beim Wechseln zwischen Shows (am Demo-Menü aufgefallen) -- dieselbe Ursache wie STAB-36

**Herkunft:** Bedientest QA-96 (Befund QA96-01): Datei -> Demo-Show öffnen, drei Demos nacheinander -- beim dritten Laden `free(): invalid pointer`, an wechselnder Stelle (Patch-Tabelle, Gruppenliste, Geräteliste, 3D-Patchliste). Ohne Bildschirm nachgestellt: 6 von 6 Läufen abgestürzt (Demo-Shows des Bedientests), ebenso 6 von 6 mit den mitgelieferten Shows, jeweils beim dritten bis fünften Laden. **Ursache:** dieselbe wie STAB-36 -- jedes Show-Laden baut die Paletten-Seiten zweimal neu und hinterließ dabei tote Layout-Einträge in PySide; die Listen, an denen es knallte, sind nur die Stellen, an denen ein neues Objekt auf einer alten Adresse abgeräumt wurde. **Beleg:** allein mit dem Fix an den Paletten-Seiten 0 von 6 statt 6 von 6; nach dem fertigen Fix 0 von 30 Läufen. **Fix und Tests:** im Zweig von STAB-36 (`fix/stab36-absturz-auswahlwechsel`), kein eigener Code; `tests/test_stab36_layout_eintraege.py::test_show_wechsel_in_schleife_stuerzt_nicht_ab` fährt die Show-Wechsel als Schleife im Kindprozess.
