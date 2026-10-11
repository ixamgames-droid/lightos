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

// Frame-Zeit-Rueckfall: reine Fuell-Zeit von 6 Mess-Draws ohne den
// readPixels-Rueckweg (renderer.js#messeFuellrate), bis zu der eine GPU als 'high' gilt. Grob gewaehlt: diskrete Karten liegen
// weit darunter, Software-Renderer weit darueber; integrierte Grafik dazwischen
// wird ohnehin meist schon am Namen erkannt. Noch nicht an Windows-Werten
// geeicht (RX 580 / Ryzen-Grafik / Iris Xe) — gpuProbeInfo().benchMs zeigt
// den gemessenen Wert.
export const BENCH_HIGH_MS = 6;

// Reihenfolge zaehlt: Software zuerst (ein Software-Renderer kann einen
// Kartennamen im String tragen), dann Mobil, dann APU-Grafik (traegt "Radeon",
// ist aber integriert), dann diskret, dann Intel-Einstiegsgrafik.
const REGELN = [
  { re: /swiftshader|llvmpipe|softpipe|lavapipe|basic render|\bwarp\b/, tier: 'low',
    grund: 'Software-Renderer' },
  // VIZ-99: Adreno X1-85 (Snapdragon X Elite und X Plus mit 10 Kernen) ist am
  // Geraet gemessen und traegt Hoch — deshalb per Name, nicht per Messung.
  // Windows-ARM-PC (X1E-80-100, die schwaechste X1-85-Ausfuehrung), Netzbetrieb,
  // Mega Arena mit 32 Geraeten, 200-%-Bildschirm, Stufe Hoch: Leerlauf 60 fps,
  // unter Bewegung 51-57 fps bei minimiertem Hauptfenster (Niedrig: 59-60).
  // Mit sichtbarem Hauptfenster 35-47 fps (Niedrig: 37-60) — dort bremst die
  // 2D-Ansicht den gemeinsamen UI-Thread, nicht die Grafik.
  // Warum nicht messen: die Start-Messung lieferte auf DIESEM Chip bei sechs
  // Starts 6,6 / 7,2 / 7,2 / 7,8 / 7,8 / 9,0 ms — sie streut um ein Drittel
  // und liegt knapp ueber BENCH_HIGH_MS. Jede Grenze in dieser Gegend
  // liesse die Stufe von Start zu Start kippen; mit 6 ms war es immer Niedrig
  // (Pixeldichte 1,25 auf einem 200-%-Bildschirm, keine Kantenglaettung, keine
  // geglaettete Bewegung).
  { re: /adreno.*\bx1-85\b/, tier: 'high', grund: 'Snapdragon X (Adreno X1-85)' },
  // Die uebrige Adreno-X-Reihe (X1-45 im Snapdragon X Plus mit 8 Kernen, etwa
  // halb so schnell; X2-…) ist nicht gemessen: nicht pauschal Niedrig, sondern
  // die Frame-Zeit entscheiden lassen.
  { re: /adreno.*\bx\d\b/, tier: null, grund: 'Snapdragon X' },
  { re: /adreno|mali|powervr|videocore|apple a\d/, tier: 'low',
    grund: 'Mobil-Grafik' },
  { re: /apple m\d/, tier: 'high', grund: 'Apple M' },
  // Ryzen-APU ("Radeon(TM) Graphics", "RX Vega 8 Graphics", "Radeon 780M"):
  // weder sicher schnell noch sicher langsam -> messen.
  { re: /vega \d+ graphics|radeon\(tm\) graphics|radeon graphics|radeon\(tm\) \d{3}m|radeon \d{3}m/,
    tier: null, grund: 'APU-Grafik' },
  // Alte AMD-APU-Grafik (Kaveri/Carrizo: "AMD Radeon R5/R7 Graphics") und
  // NVIDIA-Einstiegskarten (GT 710/730/1030, MX150/250, 920MX) waeren sonst
  // ueber "radeon ... r[579]" bzw. "geforce" 'high'.
  { re: /radeon(\(tm\))? r[2-7](\(tm\))? graphics/, tier: 'low', grund: 'alte AMD-APU' },
  { re: /geforce(\(r\))? (gt \d{3,4}|mx\s?\d{3}|\d{3}mx)\b/, tier: 'low',
    grund: 'NVIDIA-Einstieg' },
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
