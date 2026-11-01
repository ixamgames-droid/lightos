ID: DOC-73
Prioritaet: P3
Status: teils
Status-Notiz: 2D-Teil geliefert — EFX-Bilder 05–08 (UI-78) neu, Modify-Bilder Dimmer-Matrix §5 (ENG-37/38/40), Überschneidungs-Hinweis (ENG-39), Prioritäten-Ansicht samt Spalte Verdeckt (ENG-35); offen: 3D-Bilder (1)–(3) und (5) am echten Bildschirm, Schichten-Schaubild der Prioritäten-Anleitung

**Herkunft:** Restliste aus DOC-74 (Bild-Reste der Einzel-Items, hier gesammelt) und Auftrag des Projektinhabers vom 29.10.2026: „alle neuen Anleitungen bebildert und mit GIFs“. Dieser Teil liefert alles, was offscreen aufzunehmen geht; 3D/WebGL bleibt offscreen schwarz.

**Bilder:** `docs/anleitung_buehnen_show/img_effekte/` 05_efx_neu, 06_efx_form, 07_efx_tempo, 08_efx_verhaeltnis (neu aufgenommen, Texte ganz lesbar). `docs/anleitung_dimmermatrix/img/` 03_modify_aus, 04_modify_an, 05_lampen_addieren, 06_lampen_abziehen_abdunkeln, 07_vc_taste_fader, 08_taste_an_aus.gif, 09_schrittweite, 10_zweierbloecke.gif, 11_modify_rgb, 12_farbe_lampen, 13_wirkt_auf, 14_chaser_modify; die drei Tasten mit +, −, ◐ verlinkt auf `anleitung_vc_widgets/img/06_modify_zeichen_tasten.png`. `docs/anleitung_prioritaeten/img/` 02_ansicht, 03_stufe_aendern.gif, 04_stufe_matrix, 05_stufe_szene, 06_eigene_zahl, 07_snap_haken, 08_blinder_gegen_lauflicht, 09_ueberschneidung, 10_verdeckt. Neue Szenendateien `tools/anleitungsbilder/szenen_dimmermatrix.py` und `szenen_prioritaeten.py`; die Lampenreihen sind Ausschnitte der 2D-Bühne mit dem Bild, das die Ausgabe senden würde (nichts wird gesendet), und jede Szene prüft die DMX-Werte gegen die Tabellen der Anleitung.

**Offen:** 3D-Bilder (1)–(3) und (5) am echten Bildschirm (`--bildschirm`), Schichten-Schaubild (Zeichnung) der Prioritäten-Anleitung. Ziehen per Maus zeigt das GIF über „▲ Stufe höher“.
