// VIZ-MH-OPTICS (David-Wunsch 2026-07-16): der 3D-Strahl folgt Zoom und Iris.
//
// Vorher war der Lichtkegel ein FESTER Winkel: die Optik-Attribute waren im
// Programmer laengst steuerbar, kamen aber nie im 3D an (`zoom`/`iris` tauchten
// im Renderer nirgends auf). Ein Zoom-Zug hatte damit null Wirkung — man sah im
// Visualizer etwas anderes als am echten Gerät.
//
// UMGESETZT WIRD ES ALS SKALIERUNG, NICHT ALS NEUE GEOMETRIE: `beam.scale` auf
// X/Z aendert den Kegel-RADIUS und laesst die Laenge, ist also genau eine
// Winkel-Aenderung — und kostet im 44-Hz-Pfad nichts (kein Geometrie-Neubau,
// keine Allokation).
//
// ★ EHRLICH ZUR KONVENTION: DMX sagt nicht, in welche Richtung ein Zoom-Kanal
// laeuft. Der verbreitete Fall ist "0 = eng, 255 = weit" (so auch die
// eingebauten MH-Profile), und genau den nimmt diese Abbildung an. Bei einem
// Geraet mit umgekehrter Kanal-Laufrichtung sieht der Kegel im 3D dann falsch
// herum aus — sichtbar, aber folgenlos: an der DMX-AUSGABE aendert das nichts.
// Eine Umkehr-Angabe pro Profil waere die saubere Loesung und ist als eigener
// Punkt notiert, statt sie hier zu raten.

const ZOOM_ENG = 0.45;    // Faktor auf den Grundwinkel bei DMX 0
const ZOOM_WEIT = 1.90;   // ... bei DMX 255
const IRIS_ZU = 0.30;     // Iris ganz geschlossen laesst 30 % des Kegels

/** DMX 0..255 -> Skalierungsfaktor des Kegel-Radius. */
export function opticsScale(zoom, iris) {
  let k = 1.0;
  if (typeof zoom === 'number' && isFinite(zoom)) {
    const z = Math.max(0, Math.min(255, zoom)) / 255;
    k *= ZOOM_ENG + (ZOOM_WEIT - ZOOM_ENG) * z;
  }
  if (typeof iris === 'number' && isFinite(iris)) {
    // Iris-Konvention wie beim Zoom: 0 = offen, 255 = zu.
    const i = Math.max(0, Math.min(255, iris)) / 255;
    k *= 1.0 - (1.0 - IRIS_ZU) * i;
  }
  return k;
}

/** Kegel + SpotLight eines Fixtures an Zoom/Iris angleichen. */
export function applyOptics(f, dmx) {
  if (!f || !dmx) return;
  if (dmx.zoom === undefined && dmx.iris === undefined) return;   // Geraet ohne Optik
  // Letzten Stand merken: der Service schickt DIFFERENTIELL, ein Batch ohne
  // zoom heisst "unveraendert" und darf den Kegel nicht zurueckspringen lassen.
  if (dmx.zoom !== undefined) f.lastZoom = dmx.zoom;
  if (dmx.iris !== undefined) f.lastIris = dmx.iris;
  const k = opticsScale(f.lastZoom, f.lastIris);
  if (f.beam) f.beam.scale.set(k, 1, k);
  if (f.spot && f.baseSpotAngle) {
    // Der SpotLight traegt die Ausleuchtung — ohne ihn wuerde nur der sichtbare
    // Kegel schmaler, der Bodenfleck aber gleich gross bleiben.
    f.spot.angle = Math.min(Math.PI / 2 - 0.01, f.baseSpotAngle * k);
  }
}
