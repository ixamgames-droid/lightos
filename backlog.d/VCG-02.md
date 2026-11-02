ID: VCG-02
Prioritaet: P3
Status: review
Status-Notiz: Gebaut als Momentaufnahme: Knopf „Aus 3D-Ansicht aufnehmen“ im Grafik-Dialog der VC-Taste nimmt das aktuelle Bild der offenen 3D-Ansicht auf (window.__lightos.momentaufnahme: ein Frame rendern + readPixels im selben JS-Durchlauf, da ohne preserveDrawingBuffer), schneidet die Mitte im Seitenverhältnis der Taste zu, verkleinert auf max. 256 px, legt das PNG über vc_assets ab (reist in der .lshow mit) und setzt es als Tastenbild; ohne 3D-Fenster deutsche Meldung. Keine neue Abhängigkeit. Tests: tests/test_vcg02_tastenbild_aus_3d.py (Zuschnitt, Dialog, Meldung, Speichern/Laden) und tests/test_vcg02_momentaufnahme_scene.py (echte Szene). Anleitung: docs/anleitung_vc_widgets/01_button.md (+ .en).
