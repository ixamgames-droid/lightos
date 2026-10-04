// VIZ-71: Qualitaetsstufen des 3D-Viewers — EINE Tabelle fuer alles, was die
// Stufe im Renderer bedeutet. Die Stufe kommt aus der Page-URL (`?gputier=`,
// Geraete-Praeferenz `viz_quality_tier`) oder aus der GPU-Probe
// (renderer.js#probeGpuTier: `low`/`high`, `max` nur von Hand).
//
//   Stufe   Push   Pixeldichte   Schatten           dynamische Aufloesung
//   low     15 Hz  hoechstens 1,25   8 Spots, PCF       bei Kamerabewegung immer
//   high    30 Hz  hoechstens 2      8 Spots, PCFSoft   nur wenn Frame > 18 ms
//   max     44 Hz  volle devicePixelRatio  16 Spots, PCFSoft  nie
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
    pushHz: 15, pixelRatioCap: 1.25, shadowCap: 8, softShadows: false,
    dynamicResolution: 'always',
  }),
  high: Object.freeze({
    pushHz: 30, pixelRatioCap: 2, shadowCap: 8, softShadows: true,
    dynamicResolution: 'slow',
  }),
  max: Object.freeze({
    // pixelRatioCap null = kein Deckel, volle devicePixelRatio.
    pushHz: 44, pixelRatioCap: null, shadowCap: 16, softShadows: true,
    dynamicResolution: 'never',
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
