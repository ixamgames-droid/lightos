ID: VIZ-93
Status: teils
Status-Notiz: Fix vorbereitet, wartet auf Sichtabnahme der Vorher/Nachher-Bilder durch den Projektinhaber

**Fix (vorbereitet, noch nicht abgenommen):** DMX-Farben im 3D als sRGB gelesen (`fixtures/lichtfarbe.js`, einmal beim Uebergang in Material-/Lichtfarben, auch die LAS-27-Palette fuer „bunt"); Kegel, Bodenfleck und Laser mit farbtonerhaltendem ACES (Linse/Pixel nur sRGB-Wandlung, normales ACES wegen Gobo-Hook am Prototyp); Weiss und Helligkeits-Masse (Schwellen, Ausbrennschutz, Pool-Rangfolge) unveraendert. Test `test_viz93_farbraum_scene`.
