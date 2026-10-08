// VIZ-84: Einstufung der Grafikkarte (Auto-Qualitaet) — rein, ohne WebGL.
//
// Bis VIZ-84 entschied MAX_TEXTURE_IMAGE_UNITS: <= 16 hiess Niedrig. Unter
// ANGLE/Direct3D 11 (Chromium unter Windows) meldet JEDE Grafikkarte 16 — eine
// RX 580 landete damit auf Niedrig (Pixeldichte 1,25, kein Antialiasing).
// Jetzt entscheidet der Renderer-Name aus WEBGL_debug_renderer_info; nur wenn
// er nichts Eindeutiges sagt, eine kurze Frame-Zeit-Messung (renderer.js),
// und erst wenn auch die nicht geht, die alte Texture-Unit-Regel.
//
// Vorrang (renderer.js#probeGpuTier): ?gputier= (manuelle Stufe aus den
// Einstellungen bzw. Test-Override) > Renderer-Name > Frame-Zeit > Texture-Units.
// Die Probe waehlt nie 'max' (VIZ-71) — das gibt es nur von Hand.
//
// Rein (keine Imports): Node-Tests laden das Modul direkt.
"use strict";

// Frame-Zeit-Rueckfall: Gesamtdauer der Mess-Draws (renderer.js#messeFuellrate)
// bis zu der eine GPU als 'high' gilt. Grob gewaehlt: diskrete Karten liegen
// weit darunter, Software-Renderer weit darueber; integrierte Grafik dazwischen
// wird ohnehin meist schon am Namen erkannt.
export const BENCH_HIGH_MS = 6;

// Reihenfolge zaehlt: Software zuerst (ein Software-Renderer kann einen
// Kartennamen im String tragen), dann Mobil, dann APU-Grafik (traegt "Radeon",
// ist aber integriert), dann diskret, dann Intel-Einstiegsgrafik.
const REGELN = [
  { re: /swiftshader|llvmpipe|softpipe|lavapipe|basic render/, tier: 'low',
    grund: 'Software-Renderer' },
  { re: /adreno|mali|powervr|videocore|apple a\d/, tier: 'low',
    grund: 'Mobil-Grafik' },
  { re: /apple m\d/, tier: 'high', grund: 'Apple M' },
  // Ryzen-APU ("Radeon(TM) Graphics", "RX Vega 8 Graphics", "Radeon 780M"):
  // weder sicher schnell noch sicher langsam -> messen.
  { re: /vega \d+ graphics|radeon\(tm\) graphics|radeon graphics|radeon\(tm\) \d{3}m|radeon \d{3}m/,
    tier: null, grund: 'APU-Grafik' },
  { re: /geforce|\brtx\b|\bgtx\b|quadro|titan|tesla|firepro|\bradeon\b.*\b(rx|pro|r[579]|hd \d|vii)\b|\brx \d{3,4}|\barc\b/,
    tier: 'high', grund: 'diskrete GPU' },
  { re: /intel.*\b(u?hd)\b.*graphics/, tier: 'low', grund: 'Intel HD/UHD' },
];

// Renderer-Name -> {tier: 'low'|'high'|null, grund}. tier null = der Name
// entscheidet nicht (unbekannt, maskiert, APU) -> Rueckfall messen.
export function classifyRenderer(chip) {
  const s = String(chip || '').toLowerCase();
  if (!s.trim()) return { tier: null, grund: 'Renderer-Name fehlt' };
  for (const r of REGELN) {
    if (r.re.test(s)) return { tier: r.tier, grund: r.grund };
  }
  return { tier: null, grund: 'Renderer-Name unbekannt' };
}

// Gesamte Entscheidung (ohne den Override, den renderer.js vorher prueft).
//   chip      Renderer-Name (oder '')
//   maxTex    MAX_TEXTURE_IMAGE_UNITS
//   messen()  Frame-Zeit in ms oder null (nur aufgerufen, wenn noetig)
export function decideTier({ chip, maxTex, messen }) {
  const k = classifyRenderer(chip);
  if (k.tier) return { tier: k.tier, grund: k.grund, benchMs: null };
  let ms = null;
  try { ms = messen ? messen() : null; } catch (e) { ms = null; }
  if (typeof ms === 'number' && isFinite(ms) && ms >= 0) {
    return { tier: ms <= BENCH_HIGH_MS ? 'high' : 'low',
             grund: k.grund + ', Frame-Zeit ' + ms.toFixed(1) + ' ms', benchMs: ms };
  }
  // Letzter Rueckfall: die alte Regel. Unter ANGLE/D3D11 ist maxTex immer 16 —
  // deshalb steht sie ganz hinten.
  return { tier: (maxTex > 16) ? 'high' : 'low',
           grund: k.grund + ', Texture-Units ' + maxTex, benchMs: null };
}
