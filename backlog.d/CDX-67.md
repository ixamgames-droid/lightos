ID: CDX-67
Prioritaet: P3
Status: review
Titel: Codex-Befund zu #1247 — gemischte Modify-Vorschau zeigt Amber/UV nicht

**Herkunft:** Codex zu #1247 (ENG-37), `src/core/engine/rgb_matrix.py` (`zellen_ablesen`). Die gemischte Vorschau eines Farb-Modify las fuer die Anzeigefarbe nur Rot/Gruen/Blau/Weiss; eine RGBA-Lampe, an der der Modify nur Amber faehrt (DMX 0/0/0/255), kam als Schwarz heraus, UV ebenso. **Behoben:** die Anzeigefarbe kommt jetzt aus `color_utils.visual_rgb`, derselben Regel wie 3D und 2D-Plan (Weiss auf alle drei, Amber und UV als eigene Emitter additiv); RGB/RGBW bleiben byte-gleich. Test: `tests/test_cdx67_modify_vorschau_amber_uv.py` (ohne Fix rot).
