// VIZ-13 3c-1: 2D-Top-Down-Icons — symbolischer Grundriss-Plan.
// Davids Reframe (2026-07-04): die Icons BLEIBEN (kein Ortho-Rendering der
// 3D-Meshes — von oben zeigen alle emissiven Flaechen weg) und werden statt-
// dessen poliert: permanente helle Umriss-Linie pro Form (unbelichtete Icons
// waren dunkelgrau auf dunklem Boden praktisch unsichtbar), lesbare Typ-
// Glyphen inkl. par_bar/mover_bar (Paritaet zu den FM-6-Symbolen der 2D-Live-
// View) und EIN zentrales Tinting (tintTopDownIcon) statt vier Duplikat-
// Bloecken in fixtures.js.
import * as THREE from '../three/three.js';

// Fuell-Farbe unbelichteter Icons (vorher 0x3a3a4a auf 0x282828-Boden).
export const ICON_UNLIT_FILL = 0x4a4e5e;
export const ICON_UNLIT_OPACITY = 0.9;
// Bar-Gehaeuse hinter Einzel-Zellen (par_bar/mover_bar): fix dunkler als die
// Zellen, damit die Zellen auch unbelichtet als Einheiten lesbar sind.
const BAR_BODY_FILL = 0x33363f;
const OUTLINE_COLOR = 0xd0d4e0;
const GLYPH_COLOR = 0xe0e4f0;

function mkFill(geo, color, opacity) {
  const m = new THREE.Mesh(geo, new THREE.MeshBasicMaterial({
    color: (color == null) ? ICON_UNLIT_FILL : color,
    transparent: true,
    opacity: (opacity == null) ? ICON_UNLIT_OPACITY : opacity,
  }));
  m.rotation.x = -Math.PI / 2;
  return m;
}

// Permanenter Umriss aus derselben Geometrie: EdgesGeometry laesst bei
// flachen Formen (Circle/Plane) nur die Aussenkante uebrig.
function mkOutline(geo, color) {
  const seg = new THREE.LineSegments(
    new THREE.EdgesGeometry(geo),
    new THREE.LineBasicMaterial({
      color: (color == null) ? OUTLINE_COLOR : color,
      transparent: true, opacity: 0.95,
    })
  );
  seg.rotation.x = -Math.PI / 2;
  seg.position.y = 0.06;
  seg.userData.isIconOutline = true;
  return seg;
}

function mkLine(points, color) {
  const geo = new THREE.BufferGeometry().setFromPoints(points);
  // transparent:true zieht die Glyph-Linie in den Transparent-Pass — nur
  // dort greift renderOrder gegen den transparenten Body-Fill; opake Linien
  // wuerden VOR dem Fill gerendert und bei voller Intensitaet uebermalt.
  return new THREE.Line(geo, new THREE.LineBasicMaterial({
    color: (color == null) ? GLYPH_COLOR : color,
    transparent: true, opacity: 1.0,
  }));
}

// Richtungs-Pfeil (Vorne = -Z im Top-Down): Schaft + Spitze.
function addArrow(group, fromZ, toZ, tipW) {
  group.add(mkLine([
    new THREE.Vector3(0, 0.05, fromZ),
    new THREE.Vector3(0, 0.05, toZ),
  ]));
  group.add(mkLine([
    new THREE.Vector3(-tipW, 0.05, toZ + tipW * 1.3),
    new THREE.Vector3(0, 0.05, toZ),
    new THREE.Vector3(tipW, 0.05, toZ + tipW * 1.3),
  ]));
}

// N Einzel-Zellen (Kreise) quer ueber eine Bar verteilen; als
// userData.cells registriert -> tintTopDownIcon faerbt pro Kopf.
function addBarCells(group, n, barW) {
  const cells = [];
  const count = Math.max(2, n || 4);
  const step = (barW - 0.3) / (count - 1);
  const r = Math.min(0.16, (barW - 0.3) / (count * 2.2));
  for (let i = 0; i < count; i++) {
    const cell = mkFill(new THREE.CircleGeometry(r, 16));
    cell.position.set(-(barW - 0.3) / 2 + i * step, 0.055, 0);
    group.add(cell);
    cells.push(cell);
  }
  return cells;
}

// FM-13: rows*cols kleine Quadrate als Raster (near-square aus n) — als
// userData.cells registriert -> tintTopDownIcon faerbt pro Pixel (heads[i],
// Zeilen-Haupt, deckungsgleich mit buildMatrixPanel/updateMatrixPanelDmx).
function addGridCells(group, n, size) {
  const count = Math.max(1, Math.min(256, Math.floor(n || 16)));
  const cols = Math.ceil(Math.sqrt(count));
  const rows = Math.ceil(count / cols);
  const cells = [];
  const inner = size - 0.18;
  const gw = inner / cols, gh = inner / rows;
  const cw = gw * 0.82, ch = gh * 0.82;
  const x0 = -inner / 2 + gw / 2;
  const z0 = -inner / 2 + gh / 2;
  for (let i = 0; i < count; i++) {
    const r = Math.floor(i / cols), c = i % cols;
    const cell = mkFill(new THREE.PlaneGeometry(cw, ch));
    cell.position.set(x0 + c * gw, 0.055, z0 + r * gh);
    group.add(cell);
    cells.push(cell);
  }
  return cells;
}

export function buildTopDownIcon(type, nHeads) {
  const group = new THREE.Group();
  let body, ring, cells = null;
  // Bar-artige Typen brauchen einen groesseren Selektionsring (die 1.6 m
  // breite Form wuerde den 0.72er-Ring sonst komplett ueberdecken).
  let ringRadii = [0.62, 0.72];

  if (type === 'moving_head') {
    body = mkFill(new THREE.CircleGeometry(0.6, 24));
    group.add(body);
    group.add(mkOutline(new THREE.CircleGeometry(0.6, 24)));
    addArrow(group, 0, -0.7, 0.15);
  } else if (type === 'par') {
    body = mkFill(new THREE.CircleGeometry(0.55, 24));
    group.add(body);
    group.add(mkOutline(new THREE.CircleGeometry(0.55, 24)));
    // Linsen-Ring: unterscheidet den PAR vom nackten Default-Kreis.
    group.add(mkOutline(new THREE.CircleGeometry(0.3, 20)));
  } else if (type === 'led_bar') {
    body = mkFill(new THREE.PlaneGeometry(1.6, 0.4));
    group.add(body);
    group.add(mkOutline(new THREE.PlaneGeometry(1.6, 0.4)));
    ringRadii = [0.92, 1.02];
  } else if (type === 'par_bar') {
    // FM-6-Paritaet: Gehaeuse-Balken mit N einzeln faerbbaren PAR-Zellen.
    body = mkFill(new THREE.PlaneGeometry(1.6, 0.5), BAR_BODY_FILL);
    group.add(body);
    group.add(mkOutline(new THREE.PlaneGeometry(1.6, 0.5)));
    cells = addBarCells(group, nHeads, 1.6);
    ringRadii = [0.92, 1.02];
  } else if (type === 'mover_bar') {
    // Wie par_bar, plus Richtungs-Pfeil (bewegte Koepfe).
    body = mkFill(new THREE.PlaneGeometry(1.6, 0.5), BAR_BODY_FILL);
    group.add(body);
    group.add(mkOutline(new THREE.PlaneGeometry(1.6, 0.5)));
    cells = addBarCells(group, nHeads, 1.6);
    addArrow(group, -0.25, -0.65, 0.12);
    ringRadii = [0.92, 1.02];
  } else if (type === 'matrix') {
    // FM-13: Pixel-Panel — quadratisches Gehaeuse + rows*cols Einzel-Pixel-Zellen
    // (Raster-Schema; jede Zelle ist ein Kopf -> tintTopDownIcon faerbt per-Pixel).
    const S = 1.3;
    body = mkFill(new THREE.PlaneGeometry(S, S), BAR_BODY_FILL);
    group.add(body);
    group.add(mkOutline(new THREE.PlaneGeometry(S, S)));
    cells = addGridCells(group, nHeads, S);
    ringRadii = [0.98, 1.08];
  } else if (type === 'spider') {
    // zwei kurze parallele Bars (Top-Down); jede Bar ist eine Zelle ->
    // tintTopDownIcon spiegelt die Farbe pro Kopf/Bar.
    const mkSpiderBar = (zoff) => {
      const m = mkFill(new THREE.PlaneGeometry(1.3, 0.16));
      m.position.z = zoff;
      return m;
    };
    body = mkSpiderBar(-0.22);
    const bar2 = mkSpiderBar(0.22);
    group.add(body);
    group.add(bar2);
    const o1 = mkOutline(new THREE.PlaneGeometry(1.3, 0.16));
    o1.position.z = -0.22;
    const o2 = mkOutline(new THREE.PlaneGeometry(1.3, 0.16));
    o2.position.z = 0.22;
    group.add(o1);
    group.add(o2);
    cells = [body, bar2];
    ringRadii = [0.82, 0.92];
  } else if (type === 'strobe') {
    body = mkFill(new THREE.PlaneGeometry(0.8, 0.8));
    group.add(body);
    group.add(mkOutline(new THREE.PlaneGeometry(0.8, 0.8)));
    // X cross
    const xpts = [
      new THREE.Vector3(-0.35, 0.05, -0.35), new THREE.Vector3(0.35, 0.05, 0.35),
      new THREE.Vector3(-0.35, 0.05, 0.35), new THREE.Vector3(0.35, 0.05, -0.35),
    ];
    const xGeo = new THREE.BufferGeometry().setFromPoints(xpts);
    group.add(new THREE.LineSegments(xGeo, new THREE.LineBasicMaterial({
      color: GLYPH_COLOR, transparent: true, opacity: 1.0,
    })));
  } else if (type === 'scanner') {
    // Quadrat + diagonale Spiegel-Linie + Strahl-Pfeil
    body = mkFill(new THREE.PlaneGeometry(0.8, 0.8));
    group.add(body);
    group.add(mkOutline(new THREE.PlaneGeometry(0.8, 0.8)));
    group.add(mkLine([
      new THREE.Vector3(-0.28, 0.05, -0.28),
      new THREE.Vector3(0.28, 0.05, 0.28),
    ], 0x88ccff));
    addArrow(group, 0, -0.55, 0.12);
  } else if (type === 'smoke') {
    body = mkFill(new THREE.PlaneGeometry(0.9, 0.55));
    group.add(body);
    group.add(mkOutline(new THREE.PlaneGeometry(0.9, 0.55)));
    // Drei kleine Kreise als Nebel-Ausstoss
    [{ x: -0.22, z: -0.32 }, { x: 0, z: -0.38 }, { x: 0.22, z: -0.32 }].forEach(p => {
      const puff = mkFill(new THREE.CircleGeometry(0.08, 12), 0x9a9aa4, 0.7);
      puff.position.set(p.x, 0.04, p.z);
      group.add(puff);
    });
  } else if (type === 'hazer') {
    body = mkFill(new THREE.PlaneGeometry(1.0, 0.55));
    group.add(body);
    group.add(mkOutline(new THREE.PlaneGeometry(1.0, 0.55)));
    // Zwei Wellen-Linien
    [-0.12, 0.12].forEach(xOff => {
      group.add(mkLine([
        new THREE.Vector3(-0.38, 0.05, xOff),
        new THREE.Vector3(-0.19, 0.05, xOff - 0.08),
        new THREE.Vector3(0, 0.05, xOff),
        new THREE.Vector3(0.19, 0.05, xOff - 0.08),
        new THREE.Vector3(0.38, 0.05, xOff),
      ], 0xb8b8c0));
    });
  } else if (type === 'laser') {
    body = mkFill(new THREE.PlaneGeometry(0.4, 0.3));
    group.add(body);
    group.add(mkOutline(new THREE.PlaneGeometry(0.4, 0.3)));
    // Faecher aus 5 Strahl-Linien nach vorne (-Z)
    const fanAngles = [-0.4, -0.2, 0, 0.2, 0.4];
    fanAngles.forEach(a => {
      const len = 0.75;
      group.add(mkLine([
        new THREE.Vector3(0, 0.05, -0.15),
        new THREE.Vector3(Math.sin(a) * len, 0.05, -0.15 - Math.cos(a) * len),
      ], 0x44ff44));
    });
  } else if (type === 'other') {
    // FLA-4: bewusst neutrales Geraete-Symbol statt PAR-/Default-Kreis.
    // Das Fragezeichen bleibt als feste Glyph-Farbe lesbar, waehrend nur das
    // Gehaeuse wie bei allen Single-Head-Typen dem Live-DMX folgt.
    body = mkFill(new THREE.PlaneGeometry(0.82, 0.68));
    group.add(body);
    group.add(mkOutline(new THREE.PlaneGeometry(0.82, 0.68)));
    group.add(mkLine([
      new THREE.Vector3(-0.16, 0.05, -0.12),
      new THREE.Vector3(-0.08, 0.05, -0.21),
      new THREE.Vector3(0.09, 0.05, -0.21),
      new THREE.Vector3(0.17, 0.05, -0.12),
      new THREE.Vector3(0.17, 0.05, -0.02),
      new THREE.Vector3(0.00, 0.05, 0.12),
      new THREE.Vector3(0.00, 0.05, 0.20),
    ]));
    group.add(mkLine([
      new THREE.Vector3(0.00, 0.05, 0.27),
      new THREE.Vector3(0.00, 0.05, 0.29),
    ]));
  } else {
    body = mkFill(new THREE.CircleGeometry(0.45, 16));
    group.add(body);
    group.add(mkOutline(new THREE.CircleGeometry(0.45, 16)));
  }

  // Selektionsring (von tools.js#updateOutlines ueber opacity geschaltet)
  ring = new THREE.Mesh(
    new THREE.RingGeometry(ringRadii[0], ringRadii[1], 24),
    new THREE.MeshBasicMaterial({ color: 0x88aaff, transparent: true, opacity: 0.0, side: THREE.DoubleSide })
  );
  ring.rotation.x = -Math.PI / 2;
  ring.position.y = 0.03;
  // Vom Raycast ausnehmen: der Ring ist unselektiert unsichtbar (opacity 0),
  // bliebe aber pickbar — Klicks auf leere Flaeche neben dem Icon (bzw. bei
  // 1-m-Grid-Abstand auf den NACHBARN) wuerden sonst dieses Fixture treffen.
  ring.raycast = function () {};
  group.add(ring);
  group.userData.body = body;
  group.userData.ring = ring;
  if (cells) group.userData.cells = cells;
  // Force-pickable via tag
  body.userData.isTopDownIcon = true;
  body.userData.isFixtureMesh = true;
  // 2D-OCCLUSION-FIX: Fixture-Icons IMMER ueber (translucenten) Buehnen-
  // Objekten zeichnen, damit Strahler in der Top-Down-Ansicht nie unter einer
  // Plattform/einem Boden verschwinden (depthTest aus + hohe renderOrder).
  // Seit 3c-1 fuer ALLE Icon-Teile (auch Umrisse/Glyphen/Zellen) — vorher
  // wurden die Glyph-Linien von den 2D-Fills der Buehnenobjekte uebermalt.
  group.traverse(o => {
    if (o === group) return;
    o.renderOrder = (o === body || o === ring) ? 3 : 4;
    if (o.material) o.material.depthTest = false;
  });
  return group;
}

// Zentrales Icon-Tinting (ersetzt die vier Duplikat-Bloecke in fixtures.js).
// `primary` ist eine THREE.Color ODER ein {r,g,b}-Objekt mit 0-255-Werten;
// `heads` (optional) sind die Multi-Kopf-Summenfarben aus dem dmxBatch —
// Icons mit userData.cells (par_bar/mover_bar/spider) faerben pro Kopf.
export function tintTopDownIcon(icon, primary, intNorm, heads) {
  if (!icon || !icon.userData) return;
  const lit = intNorm > 0.05;
  const cells = icon.userData.cells;
  if (cells && cells.length) {
    for (let i = 0; i < cells.length; i++) {
      const mat = cells[i].material;
      if (!mat) continue;
      const h = (heads && heads[i]) || (i === 0 ? primary : null);
      if (lit && h) {
        _setMatColor(mat, h);
        mat.opacity = Math.min(1.0, 0.5 + intNorm * 0.5);
      } else {
        mat.color.setHex(ICON_UNLIT_FILL);
        mat.opacity = ICON_UNLIT_OPACITY;
      }
    }
    return;
  }
  const body = icon.userData.body;
  if (!body || !body.material) return;
  if (lit && primary) {
    _setMatColor(body.material, primary);
    body.material.opacity = Math.min(1.0, 0.5 + intNorm * 0.5);
  } else {
    body.material.color.setHex(ICON_UNLIT_FILL);
    body.material.opacity = ICON_UNLIT_OPACITY;
  }
}

function _setMatColor(mat, c) {
  if (c.isColor) mat.color.copy(c);
  else mat.color.setRGB((c.r || 0) / 255, (c.g || 0) / 255, (c.b || 0) / 255);
}
