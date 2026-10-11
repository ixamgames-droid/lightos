// VIZ-71: Qualitaetsstufen des 3D-Viewers — EINE Tabelle fuer alles, was die
// Stufe im Renderer bedeutet. Die Stufe kommt aus der Page-URL (`?gputier=`,
// Geraete-Praeferenz `viz_quality_tier`) oder aus der GPU-Probe
// (renderer.js#probeGpuTier: `low`/`high`, `max` nur von Hand).
//
//   Stufe   Push   Pixeldichte   echte Lichter  Schatten           dynamische Aufloesung     Gobo
//   low     15 Hz  hoechstens 1,25   4          8 Spots, PCF       bei Kamerabewegung immer  Bodenmuster
//   high    30 Hz  hoechstens 2      8          8 Spots, PCFSoft   nur wenn Frames verpasst  projiziert
//   max     44 Hz  volle devicePixelRatio  16  16 Spots, PCFSoft  nie                       projiziert
//
// VIZ-72: `realLights` = Groesse des Spot-Pools (scene/spot_pool.js) — so viele
// echte SpotLights gibt es hoechstens, vergeben an die hellsten Strahlen. Alle
// uebrigen Strahlen zeigen Kegel und Bodenfleck, beleuchten die Umgebung aber
// nicht selbst. Schatten werfen hoechstens min(realLights, shadowCap) Lichter —
// auf Niedrig also 4.
//
// VIZ-96: `goboProjektion` — Pool-Lichter mit Schatten projizieren das Gobo
// echt (Muster auf Hindernissen, Schatten dahinter; scene/gobo_projektion.js).
// Auf Niedrig aus: dort bleibt es beim flachen Bodenmuster, und die
// beleuchteten Shader sind unveraendert.
//
// `pushHz` liest JS nicht selbst — den Takt setzt Python
// (src/ui/visualizer/quality_tiers.py, PUSH_HZ). Er steht hier, damit die
// Tabelle vollstaendig an einer Stelle lesbar ist;
// tests/test_viz71_qualitaetsstufen.py haelt beide gleich.
//
// Rein (keine Imports): Node-Tests laden das Modul direkt.
"use strict";

export const TIER_PROFILES = Object.freeze({
  low: Object.freeze({
    pushHz: 15, pixelRatioCap: 1.25, shadowCap: 8, realLights: 4, softShadows: false,
    dynamicResolution: 'always', goboProjektion: false,
  }),
  high: Object.freeze({
    pushHz: 30, pixelRatioCap: 2, shadowCap: 8, realLights: 8, softShadows: true,
    dynamicResolution: 'slow', goboProjektion: true,
  }),
  max: Object.freeze({
    // pixelRatioCap null = kein Deckel, volle devicePixelRatio.
    pushHz: 44, pixelRatioCap: null, shadowCap: 16, realLights: 16, softShadows: true,
    dynamicResolution: 'never', goboProjektion: true,
  }),
});

export const TIER_NAMES = Object.freeze(['low', 'high', 'max']);

export function tierProfile(tier) {
  return TIER_PROFILES[tier] || TIER_PROFILES.high;
}

// Deckel als Zahl (Infinity = keiner) — fuer Math.min.
export function pixelRatioCapFor(tier) {
  const cap = tierProfile(tier).pixelRatioCap;
  return (typeof cap === 'number' && cap > 0) ? cap : Infinity;
}
