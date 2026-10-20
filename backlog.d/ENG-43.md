ID: ENG-43
Prioritaet: P2
Status: todo
Titel: Modify für Bewegung (Pan/Tilt) als Versatz -- die laufende Position um n Grad verschieben

**Herkunft:** ENG-37 „Bewegung und weitere Kanäle“; Entscheidung des Projektinhabers vom 19.10.2026: Modify für Bewegung als VERSATZ -- *Addieren*/*Abziehen* verschieben die laufende Position um n Grad (kein Abdunkeln).
**Befund:** Modify gibt es nur für Dimmer (ENG-37) und Farbe (ENG-38/40). Ein Bewegungs-Effekt überschreibt die Position der Geräte; eine Welle oder ein Nicken über eine laufende Bewegung oder eine gesetzte Position zu legen, geht nicht.
**Fertig, wenn:** ein Bewegungs-Effekt (EFX bzw. Bewegung im Matrix-Editor) als Modify-Effekt laufen kann und im späten Rechengang (`modify.py`, `AppState._render_frame` 4a²b) einen Versatz in Grad auf Pan/Tilt des fertigen Bildes rechnet -- je Gerät über dessen Schwenk-/Neigebereich in DMX umgerechnet, einschließlich 16-Bit-Fine-Kanälen (Grob- und Fein-Kanal gemeinsam, kein Sprung am Übertrag); gekappt an den Gerätegrenzen (kein Umschlag von 540° auf 0°); Laser- und Zielsicherheit beachtet (Sperrzonen und NOT-AUS liegen danach und werden nie umgangen, ein Versatz darf keinen Laser in eine gesperrte Zone schieben, ohne dass der Sperrzonen-Schutz greift; Test dafür); Editorfeld (Haken „Modify-Effekt“, Betriebsart Addieren/Abziehen, Versatz in Grad) und Konsolen-Parameter (Modify-Stärke skaliert den Versatz). Dimmer und Farbe bleiben unberührt; Alt-Shows byte-gleich; Anleitung (Dimmer-Matrix Abschnitt 5 bzw. Bewegungs-Anleitung) und Zeichen auf der Taste (ENG-37-B) passend.
