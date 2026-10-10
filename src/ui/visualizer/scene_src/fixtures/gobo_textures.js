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
//    VIZ-92: die "schwache Streuung" war am Boden weiter der volle runde
//    Lichtkreis neben dem Muster — `GOBO_LICHT` ist jetzt 0.

import * as THREE from '../three/three.js';
// Zirkulaer mit floor_pool.js (das GOBO_RAND holt) — unbedenklich, beide
// Konstanten werden nur in Funktionsruempfen gelesen, nie beim Modul-Laden.
import { POOL_MAX_RADIUS, poolFalloffTexture } from './floor_pool.js';
import { isLowSpec, renderer } from '../scene/renderer.js';   // VIZ-92
import { schattenRechteck } from '../scene/gobo_projektion.js';   // VIZ-102

const CACHE = new Map();
// VIZ-92: 128 px waren fuer einen Bodenfleck von mehreren Metern zu grob —
// das Zebra (Gobo 7) zeigte am Boden sichtbare Treppen und weiche Klumpen
// statt gerader Balkenkanten. 512 (Zweierpotenz: three baut Mipmaps, das
// Muster flimmert aus der Ferne nicht) bzw. 256 auf der Stufe Niedrig. Die
// Texturen sind je Stil fuer ALLE Geraete geteilt (CACHE), der Speicher
// waechst also mit der Zahl der Motive (7), nicht mit der Zahl der Geraete.
export const GROESSE = isLowSpec ? 256 : 512;
// VIZ-92: anisotrope Filterung — der Fleck liegt flach und wird fast immer
// schraeg angesehen; ohne sie verschwimmen die Kanten quer zur Blickrichtung.
// Niedrig bleibt bei 1 (Fuellrate).
const ANISO_DACH = isLowSpec ? 1 : 8;
function _anisotropie() {
  try {
    const n = renderer && renderer.capabilities
      && renderer.capabilities.getMaxAnisotropy && renderer.capabilities.getMaxAnisotropy();
    return Math.max(1, Math.min(ANISO_DACH, n || 1));
  } catch (e) { return 1; }
}
/** Gemeinsame Einstellungen jeder Gobo-Textur (Mipmaps sind three-Vorgabe
 *  fuer Zweierpotenzen: minFilter LinearMipmapLinear, generateMipmaps). */
function _texturGuete(tex) {
  tex.generateMipmaps = true;
  tex.anisotropy = _anisotropie();
  tex.needsUpdate = true;
  return tex;
}

// ── VIZ-83 B2: EINE Motiv-Beschreibung fuer Kegel UND Boden ────────────────
//
// Bis zum Review-Befund B2 gab es zwei getrennte Zeichnungen: die Bodenmotive
// lagen bei 0,5–0,66 des Fleck-Radius, die Teilstrahlen trafen den Boden aber
// am Kegelrand; der Winkel-Nullpunkt lag am Kegel auf +z, am Boden (nach der
// -90°-Drehung der Scheibe) auf +x, und der Drehsinn war gespiegelt. Die
// Teilstrahlen endeten neben dem Muster im Dunkeln.
//
// Jetzt beschreibt `MOTIVE` jedes Motiv EINMAL als Liste von Teilen
// `{u, b}`: `u` = Lage auf dem Umfang (0..1, dieselbe Koordinate wie das u der
// `ConeGeometry`, also Winkel theta = 2*pi*u mit x = sin, z = cos), `b` = Breite
// des Teilstrahls als Anteil des Umfangs. Daraus entstehen
//
// * die Kegel-Maske: je Teil ein heller Streifen (die Spirale mit Drall —
//   oben an der Linse um `drall` Umfang versetzt, am Boden genau bei `u`),
// * das Bodenmotiv: je Teil ein helles Element bei `GOBO_RAND` (Anteil des
//   Textur-Radius) unter dem Canvas-Winkel `a = pi/2 - 2*pi*u`. Mit dieser
//   Wahl liegt Teil `u` nach der Scheiben-Drehung `rotation.z = w` in Welt-
//   Richtung atan2(x, z) = 2*pi*u + w — genau dort, wo der um `w` gedrehte
//   Kegel (`rotation.y = w`) seinen Teilstrahl hat: gleicher Nullpunkt
//   (+z), gleicher Drehsinn.
//
// Dass der Kegelrand am Boden genau auf `GOBO_RAND` liegt, stellt
// `alignGoboFloor` sicher (aus der echten Welt-Matrix des Kegels: Zoom,
// Kegellaenge und Kopfstellung gehen damit von selbst ein).
// Muster ohne Teilstrahl (innere Punkte, Zebra-Balken) zeichnet `innen`.
//
// VIZ-102 (Nachbesserung): ein Gobo sitzt IM Strahl. Bis hierher lag der
// Kegelrand bei 0,62 des Motivs und die Bodenelemente sassen AUF dem Rand —
// ihre aeussere Haelfte (bis 0,84) lag ausserhalb des Kegels. In der Projektion
// war das Licht ohne Strahl: bei 18 Grad Kegel reichte das Motiv bis 24 Grad,
// die Teile landeten am Hallenboden Meter vor dem Kegelende. Jetzt ist
// GOBO_RAND der Rand des Kegels UND des Motivs: die Elemente sitzen INNEN am
// Rand (ihre Aussenkante beruehrt ihn — dort endet ihr Teilstrahl), und das
// Bild endet am Rand mit weicher Kante (GOBO_WEICH innen, GOBO_SAUM aussen) —
// wie das Abbild eines echten Gobos. Die Elemente sind im Verhaeltnis zum
// Kegel so gross wie zuvor. Flaches Muster und Projektion zeichnen dieselben
// Canvas-Motive, sie bleiben deckungsgleich.
export const GOBO_RAND = 0.88;
/** Weiche Bildkante (Anteil der Kachel): beginnt so weit innen vom Rand ... */
export const GOBO_WEICH = 0.04;
/** ... und ist so weit aussen ganz zu. */
export const GOBO_SAUM = 0.04;
// Das Bodenelement ist etwas breiter als sein Teilstrahl: der Strahl soll
// sicher IM Element enden, nicht auf dessen Kante.
const BODEN_UEBERMASS = 1.35;

function _ring(n, b, form, versatz = 0) {
  const out = [];
  for (let i = 0; i < n; i++) out.push({ u: (i / n + versatz) % 1, b, form });
  return out;
}

// Zebra: die Teilstrahlen sind die Stellen, an denen die Balken den Kegelrand
// kreuzen — abgeleitet, nicht zusaetzlich erfunden.
const ZEBRA_BALKEN = [-0.5, -0.25, 0, 0.25, 0.5];   // Mitte, Anteil von M (y nach unten)
const ZEBRA_HALB = 0.075;
// VIZ-92: die Balken enden knapp ausserhalb des Kegelrands (GOBO_RAND), rund
// wie die Blende — vorher liefen sie bis 0,8 des Scheibenradius und standen
// als Streifen neben dem Fleck. Das Uebermass laesst jeden Teilstrahl sicher
// IM Balken enden (wie BODEN_UEBERMASS fuer die anderen Motive).
export const ZEBRA_RAND = GOBO_RAND;   // VIZ-102: die Balken fuellen den Kegel bis zum Rand
function _zebraTeile() {
  const out = [];
  for (const y of ZEBRA_BALKEN) {
    const s = y / GOBO_RAND;
    if (Math.abs(s) >= 1) continue;
    for (const a of [Math.asin(s), Math.PI - Math.asin(s)]) {
      // Canvas-Winkel a -> u (Umkehrung von a = pi/2 - 2*pi*u)
      const u = ((((Math.PI / 2 - a) / (2 * Math.PI)) % 1) + 1) % 1;
      const halb = ZEBRA_HALB / (GOBO_RAND * Math.abs(Math.cos(a)));   // rad
      out.push({ u, b: Math.min(0.05, (2 * halb / (2 * Math.PI)) / BODEN_UEBERMASS),
                 form: '' });
    }
  }
  return out;
}

const MOTIVE = {
  'ring_slits': { teile: _ring(8, 0.04, 'bogen') },
  'ovals': { teile: _ring(5, 0.045, 'oval') },
  'circle_of_circles': { teile: _ring(7, 0.055, 'punkt') },
  'tetris': {
    teile: [[0.03, 0.05], [0.16, 0.03], [0.24, 0.06], [0.41, 0.035],
            [0.55, 0.055], [0.65, 0.03], [0.78, 0.05], [0.90, 0.035]]
      .map(([u, b]) => ({ u, b, form: 'block' })),
    innen(g, M) {                               // ein T-Stein in der Mitte
      const s = M * 0.16;
      [[-1, -1], [0, -1], [1, -1], [0, 0]].forEach(([x, y]) =>
        g.fillRect(M + (x - 0.5) * s, M + (y + 0.0) * s, s * 0.9, s * 0.9));
    },
  },
  'dots': {
    teile: _ring(14, 0.026, 'punkt'),
    innen(g, M) {                               // innerer Ring ohne Teilstrahl
      for (let i = 0; i < 7; i++) {
        const a = (i / 7 + 1 / 14) * Math.PI * 2;
        g.beginPath();
        g.arc(M + Math.cos(a) * M * 0.3, M + Math.sin(a) * M * 0.3, M * 0.07, 0, Math.PI * 2);
        g.fill();
      }
    },
  },
  // Drei Arme, die von der Mitte zum Rand laufen — jeder endet genau dort,
  // wo die Wendel des Kegels am Boden ankommt.
  'spiral': { teile: _ring(3, 0.025, 'arm', 0.5), drall: 0.5 },
  'zebra': {
    teile: _zebraTeile(),
    innen(g, M) {
      g.save();
      g.beginPath(); g.arc(M, M, M * ZEBRA_RAND, 0, Math.PI * 2); g.clip();
      for (const y of ZEBRA_BALKEN) {
        g.fillRect(0, M + (y - ZEBRA_HALB) * M, 2 * M, 2 * ZEBRA_HALB * M);   // VIZ-102: bis zum Kegelrand
      }
      g.restore();
    },
  },
};

/** VIZ-96: alle Motive in fester Reihenfolge (= Kachel-Nummern des Atlas in
 *  scene/gobo_projektion.js). */
export const GOBO_STILE = Object.freeze(Object.keys(MOTIVE));

/** Canvas-Winkel (y nach unten) des Teils `u` im Bodenmotiv. */
function bodenWinkel(u) { return Math.PI / 2 - 2 * Math.PI * u; }

function zeichne(stil) {
  const motiv = MOTIVE[stil];
  if (!motiv) return null;    // "open"/"" oder unbekannt -> kein Muster, voller Fleck
  const c = document.createElement('canvas');
  c.width = c.height = GROESSE;
  const g = c.getContext('2d');
  const M = GROESSE / 2;
  // Grund: schwarz = kein Licht (additives Material -> schwarz ist unsichtbar).
  g.fillStyle = '#000';
  g.fillRect(0, 0, GROESSE, GROESSE);
  g.fillStyle = '#fff';
  g.strokeStyle = '#fff';
  g.lineCap = 'round';
  const rr = M * GOBO_RAND;
  for (const { u, b, form } of motiv.teile) {
    const a = bodenWinkel(u);
    // halbe Bogenlaenge des Teils am Rand, mit Uebermass
    const hw = Math.PI * b * rr * BODEN_UEBERMASS;
    // VIZ-102: jedes Element sitzt um seine halbe radiale Ausdehnung INNEN vom
    // Kegelrand — seine Aussenkante liegt auf dem Rand, nichts ragt hinaus.
    const innen = form === 'punkt' ? Math.max(hw, M * 0.05)
      : form === 'oval' ? M * 0.24
        : form === 'block' ? Math.max(2 * hw, M * 0.1) / 2 : 0;
    // (0,75: die Aussenkante laeuft in die weiche Bildkante hinein.)
    const re = rr - 0.75 * innen;
    const x = M + Math.cos(a) * re, y = M + Math.sin(a) * re;
    if (form === 'punkt') {
      g.beginPath(); g.arc(x, y, Math.max(hw, M * 0.05), 0, Math.PI * 2); g.fill();
    } else if (form === 'bogen') {
      const span = Math.PI * b * BODEN_UEBERMASS;
      g.lineWidth = GROESSE * 0.06;
      g.beginPath(); g.arc(M, M, rr - GROESSE * 0.022, a - span, a + span); g.stroke();
    } else if (form === 'oval') {
      g.save(); g.translate(x, y); g.rotate(a);
      g.beginPath(); g.ellipse(0, 0, M * 0.24, Math.max(hw, M * 0.1), 0, 0, Math.PI * 2);
      g.fill(); g.restore();
    } else if (form === 'block') {
      const s = Math.max(2 * hw, M * 0.1);
      g.save(); g.translate(x, y); g.rotate(a);
      g.fillRect(-s / 2, -s / 2, s, s); g.restore();
    } else if (form === 'arm') {
      // Polarkurve von der Mitte (t = 0) zum Rand (t = 1); der Winkel holt
      // eine Dreivierteldrehung auf und endet genau bei `a`.
      g.lineWidth = Math.max(2 * hw, GROESSE * 0.04);
      g.beginPath();
      for (let t = 0; t <= 1.0001; t += 0.02) {
        const w = a + (1 - t) * Math.PI * 1.5, r = rr * t;
        const px = M + Math.cos(w) * r, py = M + Math.sin(w) * r;
        if (t === 0) g.moveTo(px, py); else g.lineTo(px, py);
      }
      g.stroke();
    }
  }
  if (motiv.innen) motiv.innen(g, M);
  // Runder Bildrand mit weicher Kante AM Kegelrand (VIZ-102): ausserhalb des
  // Strahls liegt nichts mehr.
  const kante = g.createRadialGradient(M, M, M * (GOBO_RAND - GOBO_WEICH),
                                       M, M, M * (GOBO_RAND + GOBO_SAUM));
  kante.addColorStop(0, 'rgba(255,255,255,1)');
  kante.addColorStop(1, 'rgba(255,255,255,0)');
  g.globalCompositeOperation = 'destination-in';
  g.fillStyle = kante;
  g.fillRect(0, 0, GROESSE, GROESSE);
  return c;
}

// ── VIZ-83: Teilstrahl-Masken fuer den Kegel ───────────────────────────────
// Breite = Umfang (u), Hoehe = Laenge (v, Oberkante = Spitze = Linse,
// Unterkante = Kegelbasis = Bodenende, s. fixtures.js#beamFalloffTexture).
// VIZ-92: Breite wie das Bodenmotiv (schmale Zebra-Teilstrahlen waren bei 256
// nur wenige Texel breit und flimmerten beim Drehen).
const STRAHL_B = GROESSE, STRAHL_H = 64;
const STRAHL_CACHE = new Map();

function zeichneStrahl(stil) {
  const c = document.createElement('canvas');
  c.width = STRAHL_B; c.height = STRAHL_H;
  const g = c.getContext('2d');
  if (!stil) {                       // offen: weiss = Kegel unveraendert
    g.fillStyle = '#fff';
    g.fillRect(0, 0, STRAHL_B, STRAHL_H);
    return c;
  }
  const motiv = MOTIVE[stil];
  if (!motiv) return null;           // unbekannter Stil -> wie offen
  g.fillStyle = '#000';
  g.fillRect(0, 0, STRAHL_B, STRAHL_H);
  g.fillStyle = '#fff';
  const drall = motiv.drall || 0;
  for (const { u, b } of motiv.teile) {
    // Viereck von der Linse (oben, um `drall` versetzt) zum Boden (unten,
    // genau bei u). Ohne Drall ein gerader Streifen, mit Drall eine Wendel.
    const w = Math.max(1, b * STRAHL_B) / 2;
    const xu = u * STRAHL_B, xo = (u - drall) * STRAHL_B;
    for (const versatz of [-STRAHL_B, 0, STRAHL_B]) {   // Naht bei u = 0/1
      g.beginPath();
      g.moveTo(xo - w + versatz, 0); g.lineTo(xo + w + versatz, 0);
      g.lineTo(xu + w + versatz, STRAHL_H); g.lineTo(xu - w + versatz, STRAHL_H);
      g.closePath(); g.fill();
    }
  }
  return c;
}

/** VIZ-83: Kegel-Maske fuer einen Stil. "" / "open" / unbekannt liefern die
 *  WEISSE Textur (voller Kegel) — nie null, solange ein Canvas da ist: die
 *  `map` bleibt damit dauerhaft am Material und ein Gobo-Wechsel baut keinen
 *  Shader neu. */
export function beamGoboTexture(stil) {
  let key = String(stil || '');
  if (key === 'open' || (key && !MOTIVE[key])) key = '';
  if (STRAHL_CACHE.has(key)) return STRAHL_CACHE.get(key);
  let tex = null;
  try {
    const c = zeichneStrahl(key);
    if (c) tex = _texturGuete(new THREE.CanvasTexture(c));
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
// VIZ-92: 0 statt 0,3. Auch 30 % zeichneten am Boden noch die VOLLE runde
// Lichtflaeche des Strahlers neben das Muster (Gobo-Demo, Punkte/Tetris) —
// r128 kann den SpotLight nicht maskieren, jeder Rest ist ein Kreis. Mit Gobo
// traegt deshalb allein das Muster (Kegel-Teilstrahlen + Bodenmuster) das
// Licht. Das Geraet gibt damit auch sein Pool-Licht ab (spot_pool.js zaehlt
// Intensitaet 0 als dunkel) — ein anderer Strahl bekommt es.
export const GOBO_LICHT = 0;
export const GOBO_STRAHL = 1.8;
export const GOBO_FLECK = 1.5;

/** THREE.CanvasTexture fuer einen Stil — oder null (= kein Muster). */
export function goboTexture(stil) {
  const key = String(stil || '');
  if (CACHE.has(key)) return CACHE.get(key);
  let tex = null;
  try {
    const c = zeichne(key);
    if (c) tex = _texturGuete(new THREE.CanvasTexture(c));
  } catch (e) { tex = null; }
  CACHE.set(key, tex);
  return tex;
}

// Wiederverwendete Rechenobjekte (44-Hz-Pfad, keine Allokation je Frame).
const _A = new THREE.Vector3(), _P = new THREE.Vector3();
const _EX = new THREE.Vector3(), _EY = new THREE.Vector3(), _C = new THREE.Vector3();
const _EZ = new THREE.Vector3(0, 1, 0);
const RAND_PROBEN = 16;
// Codex-P2: Grenzen der affinen Bodenmatrix. Bei fast waagerechtem Kopf
// treffen die Randstrahlen den Boden unter sehr flachem Winkel, weit weg —
// die Kleinste-Quadrate-Ellipse wird dann riesig bzw. entartet. Reichweite wie
// in builders.js#applyFloorAim (Bodentreffer nur bis 100 m), Halbachse wie der
// normale Bodenfleck (floor_pool.js#POOL_MAX_RADIUS). Darueber hinaus faellt
// die Scheibe auf den normalen TRS-Bodenfleck zurueck (geklemmte Groesse).
const GOBO_MAX_WEITE = 100;
// Kleinste/groesste Halbachse: darunter ist die Abbildung praktisch ein Strich.
const GOBO_MIN_SEITENVERH = 1e-3;

/** Scheibe zurueck auf die normale TRS-Matrix (kein Gobo / kein Treffer). */
function _scheibeFrei(disc) {
  if (disc && disc.matrixAutoUpdate === false) disc.matrixAutoUpdate = true;
}

/** VIZ-83 B2: Bodenmuster auf die Teilstrahlen des Kegels ausrichten.
 *
 *  Rechnet aus der Welt-Matrix des Kegels, wo sein Basisrand auf der
 *  getroffenen Flaeche (Hoehe `flaecheY`) ankommt: fuer `RAND_PROBEN` Stellen
 *  `u` die Mantellinie Spitze -> Randpunkt (lokal x = R*sin, z = R*cos) bis auf
 *  die Flaeche verlaengert. Senkrecht ist das ein Kreis, geneigt eine
 *  gestreckte, verschobene Ellipse.
 *
 *  Die Scheibe bekommt dann die affine Abbildung, die den Motiv-Kreis bei
 *  `GOBO_RAND` (Canvas-Winkel `pi/2 - 2*pi*u`, d. h. Scheiben-lokal
 *  (sin 2*pi*u, -cos 2*pi*u) * GOBO_RAND * Radius) im Mittel der kleinsten
 *  Quadrate auf diese Randpunkte legt — damit endet jeder Teilstrahl auf
 *  seinem Bodenelement, auch bei Gobo-Drehung (der Kegel ist dann schon um
 *  `rotation.y` gedreht) und bei schraeg stehendem Kopf. Eine TRS-Matrix
 *  reicht dafuer nicht: die Streckrichtung (Neigung) und der Musterwinkel
 *  (Gobo-Drehung) sind unabhaengig, die Abbildung braucht also eine Scherung.
 *  Deshalb `matrixAutoUpdate = false`, solange ein Gobo projiziert wird.
 *
 *  Die TRS-Felder bleiben trotzdem sinnvoll belegt (Position = Auftreffpunkt
 *  aus applyFloorAim, `rotation.z` = Gobo-Winkel plus Pan/Tilt-Abweichung von
 *  Teil `u = 0`, auf ±pi gefaltet — ein senkrecht haengender Kopf behaelt also
 *  genau den Gobo-Winkel). Rueckgabe: mittlerer Kegelrand-Abstand in Metern
 *  (fuer syncPoolSize) oder `null`, wenn nichts auszurichten ist.
 */
export function alignGoboFloor(f, hitX, flaecheY, hitZ, zielScheibe = null) {
  // VIZ-102: `zielScheibe` = die zweite Scheibe auf der Flaeche unter einer
  // Kante (goboKanteAbgleichen) — dieselbe Rechnung fuer eine andere Hoehe.
  const beam = f && f.beam, disc = zielScheibe || (f && f.floorSpot);
  if (!disc) return null;
  if (!f.goboAktiv || !beam || !beam.geometry || typeof hitX !== 'number') {
    _scheibeFrei(disc);
    return null;
  }
  const p = beam.geometry.parameters || {};
  const R = p.radius, h = p.height;
  const Rd = (disc.geometry && disc.geometry.parameters
              && disc.geometry.parameters.radius) || 1;
  if (!(R > 0) || !(h > 0)) { _scheibeFrei(disc); return null; }
  beam.updateWorldMatrix(true, false);
  beam.localToWorld(_A.set(0, h / 2, 0));        // Spitze (an der Linse)
  const q = GOBO_RAND * Rd;
  _C.set(0, 0, 0); _EX.set(0, 0, 0); _EY.set(0, 0, 0);
  let psi0 = 0;
  for (let i = 0; i < RAND_PROBEN; i++) {
    const u = i / RAND_PROBEN, th = 2 * Math.PI * u;
    beam.localToWorld(_P.set(R * Math.sin(th), -h / 2, R * Math.cos(th)));
    const dy = _P.y - _A.y;
    if (!(dy < -1e-6)) { _scheibeFrei(disc); return null; }   // zeigt nicht nach unten
    const t = (flaecheY - _A.y) / dy;
    if (!(t > 0) || !isFinite(t)) { _scheibeFrei(disc); return null; }
    _P.sub(_A).multiplyScalar(t);
    // Zu flacher Randstrahl: trifft jenseits der Reichweite (Codex-P2).
    if (!(_P.length() <= GOBO_MAX_WEITE)) { _scheibeFrei(disc); return null; }
    _P.add(_A);                                  // Endpunkt auf der Flaeche
    if (i === 0) psi0 = Math.atan2(_P.x - hitX, _P.z - hitZ);
    // Kleinste Quadrate fuer P = C + EX*lx + EY*ly mit (lx, ly) auf dem
    // gleichmaessig abgetasteten Kreis: C = Mittel, EX/EY = 2/(N q^2) * Sum P*l.
    const lx = Math.sin(th) * q, ly = -Math.cos(th) * q;
    _C.add(_P);
    _EX.addScaledVector(_P, lx);
    _EY.addScaledVector(_P, ly);
  }
  _C.multiplyScalar(1 / RAND_PROBEN);
  const k = 2 / (RAND_PROBEN * q * q);
  _EX.multiplyScalar(k); _EY.multiplyScalar(k);
  _EX.y = 0; _EY.y = 0;                            // flach auf der Flaeche
  _C.y = flaecheY;
  // Codex-P2: Halbachsen der xz-Abbildung (Singulaerwerte der 2x2-Matrix
  // [EX.x EY.x; EX.z EY.z]) pruefen — zu gross oder entartet -> TRS-Fleck.
  const s1 = _EX.lengthSq() + _EY.lengthSq();
  const det = _EX.x * _EY.z - _EY.x * _EX.z;
  const smax = Math.sqrt(s1 / 2 + Math.sqrt(Math.max(0, s1 * s1 / 4 - det * det)));
  if (!isFinite(smax) || !isFinite(det) || !isFinite(_C.x) || !isFinite(_C.z)
      || smax * Rd > POOL_MAX_RADIUS
      || Math.abs(det) < GOBO_MIN_SEITENVERH * smax * smax) {
    _scheibeFrei(disc);
    return null;
  }
  const basis = (typeof f.lastGoboRot === 'number' && isFinite(f.lastGoboRot))
    ? (Math.max(0, Math.min(255, f.lastGoboRot)) / 255) * 2 * Math.PI : 0;
  let d = (psi0 - basis) % (2 * Math.PI);
  if (d > Math.PI) d -= 2 * Math.PI;
  if (d <= -Math.PI) d += 2 * Math.PI;
  if (!zielScheibe) disc.rotation.z = basis + d;
  disc.matrixAutoUpdate = false;
  disc.matrix.makeBasis(_EX, _EY, _EZ).setPosition(_C);
  disc.matrixWorldNeedsUpdate = true;
  return Math.sqrt((_EX.lengthSq() + _EY.lengthSq()) / 2) * q;
}

// ── VIZ-102: nichts schwebt ueber einer Kante ───────────────────────────────
//
// Die flache Scheibe liegt in der EBENE der getroffenen Oberseite (Podest,
// Buehnenplatte). Trifft der Strahl nahe der Kante, ragte sie darueber hinaus
// und hing in der Luft — bei Motiven mit vielen Einzelteilen (Tetris) standen
// Vierecke frei vor der Buehne. Jetzt:
//
//   * die Scheibe wird an den Kanten der Oberseite beschnitten (vier
//     Clipping-Ebenen am Material — sie sind ab dem Bau da und stehen sonst
//     weit draussen, die Zahl der Ebenen und damit das Programm aendert sich
//     nie: VIZ-69);
//   * mit Gobo liegt der Rest als ZWEITE Scheibe auf der Flaeche darunter
//     (Hallenboden), aus derselben Kegel-Rechnung (alignGoboFloor) — und der
//     Schatten der Oberseite ist dort ausgespart (clipIntersection ueber das
//     vom Licht aus gestreckte Rechteck). Die zweite Scheibe entsteht erst,
//     wenn sie gebraucht wird; ihr Material ist fuer alle Geraete gleich
//     gebaut (ein Programm).
//
// Gilt auf allen Stufen — es ist das Rueckfall-Muster der Geraete ohne
// projizierendes Licht und auf Niedrig das einzige.
export const KANTE_ANZAHL = 4;
const KANTE_FREI = 1e6;
const _unterAktiv = new Set();     // Geraete, deren zweite Scheibe gerade liegt

/** Vier Clipping-Ebenen in Grundstellung (schneiden nichts). */
export function neueKantenEbenen() {
  const out = [];
  for (let i = 0; i < KANTE_ANZAHL; i++) out.push(new THREE.Plane(new THREE.Vector3(0, 1, 0), KANTE_FREI));
  return out;
}

function _ebenenFrei(ebenen) {
  if (!ebenen) return;
  for (const e of ebenen) { e.normal.set(0, 1, 0); e.constant = KANTE_FREI; }
}

// Ebenen auf die vier Seiten des Rechtecks; `innen` = Normalen zeigen nach
// innen (behalten wird das Innere), sonst nach aussen.
function _ebenenAufRechteck(ebenen, r, innen) {
  const v = innen ? -1 : 1;
  const mx = r.cx * r.c - r.cz * r.s;      // Mitte in lokalen Achsen
  const mz = r.cx * r.s + r.cz * r.c;
  ebenen[0].normal.set(v * r.c, 0, -v * r.s);   ebenen[0].constant = -v * (mx + r.hx);
  ebenen[1].normal.set(-v * r.c, 0, v * r.s);   ebenen[1].constant = v * (mx - r.hx);
  ebenen[2].normal.set(v * r.s, 0, v * r.c);    ebenen[2].constant = -v * (mz + r.hz);
  ebenen[3].normal.set(-v * r.s, 0, -v * r.c);  ebenen[3].constant = v * (mz - r.hz);
}

function _unterScheibe(f) {
  if (f.floorSpot2) return f.floorSpot2;
  const main = f.floorSpot;
  const mat = new THREE.MeshBasicMaterial({
    color: main.material.color, transparent: true, opacity: main.material.opacity,
    side: THREE.DoubleSide, depthWrite: false, blending: THREE.AdditiveBlending,
    map: main.material.map || null,
    clippingPlanes: neueKantenEbenen(), clipIntersection: true,
  });
  const disc = new THREE.Mesh(main.geometry, mat);
  disc.matrixAutoUpdate = false;
  disc.visible = false;
  disc.userData.goboUnterScheibe = true;
  if (main.parent) main.parent.add(disc);
  f.floorSpot2 = disc;
  return disc;
}

function _unterAus(f) {
  if (f.floorSpot2) f.floorSpot2.visible = false;
  f._goboUnten = false;
  _unterAktiv.delete(f);
}

/** Scheibe(n) eines Geraets an der Kante der getroffenen Oberseite ausrichten.
 *
 *  @param kante   Oberseite (gobo_projektion.js: {cx, cz, hx, hz, c, s, y})
 *                 oder null = keine Kante (Boden, Wand, kein Treffer)
 *  @param unten   true = das Muster ragt ueber die Kante (Rest nach unten)
 *  @param yUnten  Hoehe der Flaeche darunter
 *  @returns true, wenn die zweite Scheibe liegt
 */
export function goboKanteAbgleichen(f, kante, unten, yUnten, hitX, hitZ, anteil = 1) {
  const main = f && f.floorSpot;
  if (!main || !main.material) return false;
  const ebenen = main.material.clippingPlanes;
  if (!kante || !ebenen || ebenen.length !== KANTE_ANZAHL) {
    _ebenenFrei(ebenen);
    _unterAus(f);
    return false;
  }
  _ebenenAufRechteck(ebenen, kante, true);
  // Zweite Scheibe nur mit Gobo (affine Kegel-Rechnung) — der weiche Fleck
  // eines offenen Strahls wird nur beschnitten.
  if (!unten || !f.goboAktiv || main.matrixAutoUpdate !== false || !f.beam
      || !(typeof yUnten === 'number') || !(yUnten < kante.y)) {
    _unterAus(f);
    return false;
  }
  const disc = _unterScheibe(f);
  if (alignGoboFloor(f, hitX, yUnten + 0.01, hitZ, disc) === null) { _unterAus(f); return false; }
  const p = f.beam.geometry.parameters;
  f.beam.localToWorld(_A.set(0, p.height / 2, 0));
  const schatten = schattenRechteck(kante, _A.x, _A.y, _A.z, yUnten);
  if (schatten) _ebenenAufRechteck(disc.material.clippingPlanes, schatten, false);
  else _ebenenAufRechteck(disc.material.clippingPlanes, kante, false);
  // Helligkeit unten: mit dem Ueberhang einblenden (so wie der Kegel waechst
  // und die Projektion mit der Kegel-Reichweite ausblendet) und mit dem
  // Abstandsquadrat schwaecher als auf der Oberseite — nie heller als oben.
  const hoch = (_A.y - kante.y) / Math.max(1e-3, _A.y - yUnten);
  f._goboUntenDeck = Math.max(0, Math.min(1, anteil)) * Math.max(0, Math.min(1, hoch * hoch));
  f._goboUnten = true;
  _unterAktiv.add(f);
  _unterAngleichen(f);
  return true;
}

function _unterAngleichen(f) {
  const main = f.floorSpot, disc = f.floorSpot2;
  if (!main || !disc || !main.parent) { _unterAktiv.delete(f); if (disc) disc.visible = false; return; }
  const a = main.material, b = disc.material;
  b.color = a.color;
  b.opacity = a.opacity * (typeof f._goboUntenDeck === 'number' ? f._goboUntenDeck : 1);
  if (b.map !== a.map && a.map) b.map = a.map;     // nur die Uniform (Gobo-Wechsel)
  disc.layers.mask = main.layers.mask;
  disc.visible = main.visible && !!a.map && !!f.goboAktiv;
}

/** Vor jedem Bild (scene/spot_pool.js#syncSpotPool): die zweiten Scheiben
 *  folgen Farbe, Deckkraft, Ebenen-Maske und Sichtbarkeit der ersten. */
export function syncGoboUnterScheiben() {
  if (!_unterAktiv.size) return;
  for (const f of _unterAktiv) _unterAngleichen(f);
}

/** Geraet entfernt (fixtures.js#removeFixture). */
export function entferneGoboUnterScheibe(f) {
  _unterAktiv.delete(f);
  const disc = f && f.floorSpot2;
  if (!disc) return;
  if (disc.parent) disc.parent.remove(disc);
  if (disc.material) disc.material.dispose();   // Geometrie gehoert der ersten Scheibe
  f.floorSpot2 = null;
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
 *  `tex.rotation` drehte jedes Geraet mit demselben Gobo mit. Den genauen
 *  Sitz unter den Teilstrahlen (Pan/Tilt, Neigung, Kegelrand) setzt danach
 *  `alignGoboFloor` aus applyFloorAim (VIZ-83 B2).
 *
 *  `null` (VIZ-80, s. fixtures.js#OPTIK_FELDER) = das Profil hat den Kanal
 *  nicht (mehr): Muster bzw. Drehung zurueck auf Grundstellung.
 */
/** Gobo-Winkel (rad) aus dem DMX-Wert der Drehung; ohne Wert 0. */
export function goboWinkel(v) {
  return (typeof v === 'number' && isFinite(v))
    ? (Math.max(0, Math.min(255, v)) / 255) * 2 * Math.PI : 0;
}

export function applyGobo(f, dmx) {
  if (!f || !dmx) return;
  const spot = f.floorSpot;
  if (dmx.gobo_rotation !== undefined && dmx.gobo_rotation !== f.lastGoboRot) {
    f.lastGoboRot = (dmx.gobo_rotation === null) ? undefined : dmx.gobo_rotation;
    const winkel = goboWinkel(f.lastGoboRot);
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
  if (programmWechsel) {
    // VIZ-92: mit Gobo KEIN weicher Pool-Rand (alphaMap). Der Verlauf dunkelte
    // die Motiv-Teile am Kegelrand auf gut die Haelfte ab, waehrend der Kern
    // voll leuchtete — die Blende hat selbst einen runden Rand (zeichne()).
    // Getauscht nur hier, im selben Programmwechsel wie die map: kein
    // zusaetzlicher Shader-Neubau.
    spot.material.alphaMap = tex ? null : poolFalloffTexture();
    spot.material.needsUpdate = true;
  }
}
