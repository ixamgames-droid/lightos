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
//
// ── VIZ-83: das Gobo FORMT den Strahl, statt nur Kreise dazuzulegen ─────────
//
// Bis VIZ-83 bekam nur der Bodenfleck das Muster. Der Kegel blieb VOLL, und der
// SpotLight leuchtete am Boden weiter den ganzen runden Fleck aus — im Bild
// stand also der normale Lichtkegel unveraendert da, und das Muster lag als
// zusaetzliche Lichtkreise obendrauf. Ein echtes Gobo ist eine Blende: es
// nimmt Licht WEG. Im Nebel zerfaellt der Strahl in Teilstrahlen
// ("Beam-Breakup"), am Boden ist zwischen den Motiv-Teilen wirklich Dunkel.
//
// Drei Eingriffe, alle ohne neue Geometrie und ohne Shader-Neubau:
//
// 1. **Kegel-Maske** (`beamGoboTexture`): der Kegel traegt ab dem Bau eine
//    `map`. "Offen" ist eine weisse Textur (Farbe * 1 = unveraendert), ein
//    Gobo eine Streifen-Textur ueber die UMFANGS-Koordinate u der
//    `ConeGeometry` — jeder helle Streifen ist ein Teilstrahl von der Linse
//    bis zum Boden, schwarz ist bei additivem Material unsichtbar. Weil die
//    `map` von Anfang an da ist, tauscht ein Gobo-Wechsel nur die Uniform
//    (kein `needsUpdate`, kein neues Programm — VIZ-69-Regel).
// 2. **Drehung** dreht den KEGEL um seine Achse (`beam.rotation.y`), nicht
//    die Textur — dieselbe Ueberlegung wie bei der Bodenscheibe: die Textur
//    ist je Stil fuer alle Geraete geteilt. Der Kegel ist rotationssymmetrisch,
//    sichtbar dreht sich damit genau das Muster.
// 3. **SpotLight gedrosselt** (`GOBO_LICHT`): r128 kennt kein `SpotLight.map`,
//    der runde Lichtkreis laesst sich also nicht maskieren. Mit Gobo traegt
//    deshalb der Bodenfleck (der das Muster hat) das Bild, und der SpotLight
//    leuchtet nur noch als schwache Streuung mit. Nur `intensity` aendert
//    sich, nie die Zahl der Lichter.

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

// ── VIZ-83: Teilstrahl-Masken fuer den Kegel ───────────────────────────────
// Breite = Umfang (u), Hoehe = Laenge (v, Oberkante = Spitze = Linse, s.
// fixtures.js#beamFalloffTexture). Nur die Spirale braucht die Hoehe.
const STRAHL_B = 256, STRAHL_H = 64;
const STRAHL_CACHE = new Map();

// Je Motiv: Lage (0..1 ueber den Umfang) und Breite der Teilstrahlen. Die
// Zahl folgt grob dem Motiv (14 Punkte -> 14 duenne Strahlen, 7 Kreise -> 7),
// unregelmaessige Motive bekommen unregelmaessige Strahlen.
function _gleichverteilt(n, breite) {
  const out = [];
  for (let i = 0; i < n; i++) out.push([i / n, breite]);
  return out;
}
const STRAHLEN = {
  ring_slits: _gleichverteilt(8, 0.035),
  ovals: _gleichverteilt(5, 0.09),
  circle_of_circles: _gleichverteilt(7, 0.06),
  tetris: [[0.03, 0.06], [0.16, 0.03], [0.24, 0.08], [0.41, 0.04],
           [0.55, 0.07], [0.63, 0.03], [0.78, 0.06], [0.90, 0.04]],
  dots: _gleichverteilt(14, 0.022),
  zebra: _gleichverteilt(10, 0.05),
};

function zeichneStrahl(stil) {
  const c = document.createElement('canvas');
  c.width = STRAHL_B; c.height = STRAHL_H;
  const g = c.getContext('2d');
  if (!stil) {                       // offen: weiss = Kegel unveraendert
    g.fillStyle = '#fff';
    g.fillRect(0, 0, STRAHL_B, STRAHL_H);
    return c;
  }
  g.fillStyle = '#000';
  g.fillRect(0, 0, STRAHL_B, STRAHL_H);
  g.fillStyle = '#fff';
  g.strokeStyle = '#fff';
  if (stil === 'spiral') {
    // Drei schraeg laufende Streifen: von der Linse zum Boden wandern sie um
    // einen halben Umfang weiter -> eine Wendel um die Strahlachse.
    g.lineWidth = STRAHL_B * 0.06;
    for (let i = 0; i < 3; i++) {
      for (const versatz of [-STRAHL_B, 0, STRAHL_B]) {   // Naht bei u=0/1
        const x0 = (i / 3) * STRAHL_B + versatz;
        g.beginPath(); g.moveTo(x0, 0); g.lineTo(x0 + STRAHL_B * 0.5, STRAHL_H);
        g.stroke();
      }
    }
    return c;
  }
  const liste = STRAHLEN[stil];
  if (!liste) return null;           // unbekannter Stil -> wie offen
  for (const [u, b] of liste) {
    const w = Math.max(1, b * STRAHL_B), x = u * STRAHL_B - w / 2;
    g.fillRect(x, 0, w, STRAHL_H);
    if (x < 0) g.fillRect(x + STRAHL_B, 0, w, STRAHL_H);           // Naht
    if (x + w > STRAHL_B) g.fillRect(x - STRAHL_B, 0, w, STRAHL_H);
  }
  return c;
}

/** VIZ-83: Kegel-Maske fuer einen Stil. "" / "open" / unbekannt liefern die
 *  WEISSE Textur (voller Kegel) — nie null, solange ein Canvas da ist: die
 *  `map` bleibt damit dauerhaft am Material und ein Gobo-Wechsel baut keinen
 *  Shader neu. */
export function beamGoboTexture(stil) {
  let key = String(stil || '');
  if (key === 'open' || (key && !STRAHLEN[key] && key !== 'spiral')) key = '';
  if (STRAHL_CACHE.has(key)) return STRAHL_CACHE.get(key);
  let tex = null;
  try {
    const c = zeichneStrahl(key);
    if (c) {
      tex = new THREE.CanvasTexture(c);
      tex.needsUpdate = true;
    }
  } catch (e) { tex = null; }
  STRAHL_CACHE.set(key, tex);
  return tex;
}

/** VIZ-83: frisch gebauten Kegel mit der offenen Maske ausstatten (einmal beim
 *  Bau — danach wird nur noch die Textur getauscht). */
export function applyBeamGoboBase(cone) {
  if (!cone || !cone.material) return;
  const tex = beamGoboTexture('');
  if (!tex) return;
  cone.material.map = tex;
  cone.material.needsUpdate = true;
}

// VIZ-83: mit Gobo leuchtet der (unmaskierbare) SpotLight nur noch mit diesem
// Anteil; Kegel und Bodenfleck werden etwas angehoben, weil die Blende den
// groessten Teil ihrer Flaeche dunkel macht und die Teilstrahlen sonst neben
// dem alten Vollkegel blass wirkten.
export const GOBO_LICHT = 0.3;
export const GOBO_STRAHL = 1.8;
export const GOBO_FLECK = 1.5;

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

/** Bodenfleck eines Fixtures an das aktuelle Gobo angleichen.
 *
 *  `gobo`: Muster-Stil ("" = offen). `gobo_rotation` (VIZ-80): DMX 0..255 als
 *  WINKEL des Musters, eine volle Umdrehung — wie `prism_rotation` in prism.js
 *  eine Position, keine Geschwindigkeit (die eingebauten Profile haben fuer den
 *  Kanal keine Ranges; ob ein Wert "Index" oder "Dreh-Tempo" heisst, sagt erst
 *  ein Range-Name — eine fortlaufende Eigendrehung waere hier erfunden).
 *  Gedreht wird die SCHEIBE um ihre eigene Normale, nicht die Textur: die
 *  Textur ist je Stil fuer ALLE Geraete geteilt (CACHE oben), ein
 *  `tex.rotation` drehte jedes Geraet mit demselben Gobo mit.
 *
 *  `null` (VIZ-80, s. fixtures.js#OPTIK_FELDER) = das Profil hat den Kanal
 *  nicht (mehr): Muster bzw. Drehung zurueck auf Grundstellung.
 */
export function applyGobo(f, dmx) {
  if (!f || !dmx) return;
  const spot = f.floorSpot;
  if (dmx.gobo_rotation !== undefined && dmx.gobo_rotation !== f.lastGoboRot) {
    f.lastGoboRot = (dmx.gobo_rotation === null) ? undefined : dmx.gobo_rotation;
    const v = f.lastGoboRot;
    const winkel = (typeof v === 'number' && isFinite(v))
      ? (Math.max(0, Math.min(255, v)) / 255) * 2 * Math.PI : 0;
    if (spot) spot.rotation.z = winkel;
    // VIZ-83: der Kegel dreht mit — seine Teilstrahlen sind dasselbe Muster.
    // Prisma-Kegel ziehen in prism.js#syncPrismToBeam nach.
    if (f.beam) f.beam.rotation.y = winkel;
  }
  if (dmx.gobo === undefined) return;                 // Geraet ohne Gobo-Rad
  if (dmx.gobo === f.lastGobo) return;                // nichts geaendert
  f.lastGobo = (dmx.gobo === null) ? undefined : dmx.gobo;
  // VIZ-83: Kegel-Maske tauschen — nur die Uniform, die `map` ist seit dem Bau
  // da (applyBeamGoboBase). Fehlt sie (kein Canvas), bleibt der Kegel voll.
  const strahl = beamGoboTexture(f.lastGobo);
  if (f.beam && f.beam.material && f.beam.material.map && strahl) {
    f.beam.material.map = strahl;
  }
  // Ein echtes Muster blendet ab; "offen"/unbekannt laesst alles wie bisher.
  f.goboAktiv = !!goboTexture(f.lastGobo);
  if (!spot || !spot.material) return;
  const tex = goboTexture(f.lastGobo);
  if (spot.material.map === tex) return;              // z. B. "" -> null bleibt null
  // needsUpdate nur, wenn Textur KOMMT oder GEHT: das aendert das Shader-
  // Programm (USE_MAP). Ein Wechsel zwischen zwei Mustern tauscht nur die
  // Uniform — kein Neubau, kein Ruckler im Gobo-Chaser.
  const programmWechsel = !spot.material.map !== !tex;
  spot.material.map = tex;
  if (programmWechsel) spot.material.needsUpdate = true;
}
