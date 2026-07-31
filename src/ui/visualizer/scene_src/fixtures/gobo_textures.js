// VIZ-GOBO-3D (David-Wunsch 2026-07-16): Gobo-Muster im Bodenfleck.
//
// Der 3D-Viewer projizierte KEINE Gobos — `gobo`/`gobo_wheel` kam im gesamten
// Renderer nicht vor. Ein Gobo-Wechsel (etwa der MH-Gobo-Chaser der Demoshows)
// hatte damit null sichtbare Wirkung, obwohl das Rad im Programmer laeuft.
//
// WO das Muster landet: auf dem BODENFLECK. Das ist die Stelle, an der ein Gobo
// im echten Raum sichtbar wird — und der Fleck existiert bereits als Mesh
// (`createFloorSpot`), bekommt also nur eine Textur statt neuer Geometrie. Der
// Weg ueber `SpotLight.map` scheidet aus: three r128 kennt die Eigenschaft
// nicht (sie kam erst spaeter dazu).
//
// Die Muster werden PROGRAMMATISCH auf ein Canvas gezeichnet, in derselben
// Stil-Sprache wie die 2D-Kacheln im Programmer (`gobo_icons.py`) — helles
// Muster auf dunklem Grund. Keine Bilddateien: nichts nachzuladen, nichts zu
// versionieren, und der Stil-Name ist die einzige Kopplung zwischen Python und
// JS (Python erkennt ihn aus dem Range-Namen, JS zeichnet ihn).
//
// Gecacht pro Stil: die Texturen sind zustandslos, ein Fixture-Wechsel kostet
// damit nichts.

import * as THREE from '../three/three.js';

const CACHE = new Map();
const GROESSE = 128;

function zeichne(stil) {
  const c = document.createElement('canvas');
  c.width = c.height = GROESSE;
  const g = c.getContext('2d');
  const M = GROESSE / 2;
  // Grund: schwarz = kein Licht (additives Material -> schwarz ist unsichtbar).
  g.fillStyle = '#000';
  g.fillRect(0, 0, GROESSE, GROESSE);
  g.fillStyle = '#fff';
  g.strokeStyle = '#fff';
  g.lineWidth = GROESSE * 0.06;

  if (stil === 'ring_slits') {
    for (let i = 0; i < 8; i++) {
      const a0 = (i / 8) * Math.PI * 2, a1 = a0 + Math.PI / 10;
      g.beginPath(); g.arc(M, M, M * 0.62, a0, a1); g.stroke();
    }
  } else if (stil === 'ovals') {
    for (let i = 0; i < 5; i++) {
      const a = (i / 5) * Math.PI * 2;
      g.save(); g.translate(M + Math.cos(a) * M * 0.42, M + Math.sin(a) * M * 0.42);
      g.rotate(a); g.beginPath(); g.ellipse(0, 0, M * 0.24, M * 0.12, 0, 0, Math.PI * 2);
      g.fill(); g.restore();
    }
  } else if (stil === 'circle_of_circles') {
    for (let i = 0; i < 7; i++) {
      const a = (i / 7) * Math.PI * 2;
      g.beginPath();
      g.arc(M + Math.cos(a) * M * 0.5, M + Math.sin(a) * M * 0.5, M * 0.14, 0, Math.PI * 2);
      g.fill();
    }
  } else if (stil === 'tetris') {
    const s = GROESSE / 8;
    [[2,2],[3,2],[3,3],[4,3],[5,4],[5,5],[2,5],[4,1]].forEach(([x, y]) => {
      g.fillRect(x * s, y * s, s * 0.9, s * 0.9);
    });
  } else if (stil === 'dots') {
    for (let i = 0; i < 14; i++) {
      const a = (i / 14) * Math.PI * 2, r = (i % 2 ? 0.32 : 0.62) * M;
      g.beginPath(); g.arc(M + Math.cos(a) * r, M + Math.sin(a) * r, M * 0.07, 0, Math.PI * 2);
      g.fill();
    }
  } else if (stil === 'spiral') {
    g.beginPath();
    for (let t = 0; t < Math.PI * 6; t += 0.08) {
      const r = (t / (Math.PI * 6)) * M * 0.85;
      const x = M + Math.cos(t) * r, y = M + Math.sin(t) * r;
      if (t === 0) g.moveTo(x, y); else g.lineTo(x, y);
    }
    g.stroke();
  } else if (stil === 'zebra') {
    for (let i = 0; i < 5; i++) {
      g.fillRect(GROESSE * 0.1, (0.12 + i * 0.18) * GROESSE, GROESSE * 0.8, GROESSE * 0.08);
    }
  } else {
    return null;    // "open"/"" oder unbekannt -> kein Muster, voller Fleck
  }
  // Weiche Kante: ein Gobo hat einen runden Rand, kein Quadrat.
  g.globalCompositeOperation = 'destination-in';
  g.beginPath(); g.arc(M, M, M * 0.96, 0, Math.PI * 2); g.fill();
  return c;
}

/** THREE.CanvasTexture fuer einen Stil — oder null (= kein Muster). */
export function goboTexture(stil) {
  const key = String(stil || '');
  if (CACHE.has(key)) return CACHE.get(key);
  let tex = null;
  try {
    const c = zeichne(key);
    if (c) {
      tex = new THREE.CanvasTexture(c);
      tex.needsUpdate = true;
    }
  } catch (e) { tex = null; }
  CACHE.set(key, tex);
  return tex;
}

/** Bodenfleck eines Fixtures an das aktuelle Gobo angleichen. */
export function applyGobo(f, dmx) {
  if (!f || !dmx || dmx.gobo === undefined) return;   // Geraet ohne Gobo-Rad
  if (dmx.gobo === f.lastGobo) return;                // nichts geaendert
  f.lastGobo = dmx.gobo;
  const spot = f.floorSpot;
  if (!spot || !spot.material) return;
  spot.material.map = goboTexture(dmx.gobo);
  spot.material.needsUpdate = true;                   // Material-Neubau noetig
}
