// VIZ-13 Schritt 3a-4: Custom stage object builders + CRUD
// (ehem. stage_scene.html:431-810, 869-935). Reines Verschieben.
import * as THREE from '../three/three.js';
import { scene } from '../scene/renderer.js';
import { disposeObj } from '../scene/grid_floor.js';
import { geteilteGeometrie, platziere, rohr, verschmelzen } from '../scene/geteilte_geometrie.js';
import { fixtures, stageObjects, view } from '../state.js';
import { raycaster, mouse } from '../interaction/picking.js';
import { requestRender } from '../scene/render_loop.js';  // VIZ-13 3c-2
import { updateEmptyState } from '../empty_state.js';

// stageObjIdCounter bleibt hier (kein geteilter Modul-State laut Design-
// Dokument "Kern-Gotcha" - nur von createStageObject genutzt).
let stageObjIdCounter = 1;

// VIZ-66: Vierpunkt-Traverse als EIGENE Geometrie (vorher ein mitgeliefertes
// OBJ aus QLC+). Vorbild ist die verbreitete 290-mm-Klasse (F34-artig):
// vier Gurtrohre Ø 50 mm, Diagonalen Ø ~20 mm, Feldteilung ~0,5 m, an beiden
// Enden ein Rahmen. Gebaut wird direkt in den Zielmassen — kein Strecken eines
// Modells, also auch keine verzerrten Rohre (die Falle aus VIZ-TRUSS-GEOMETRY).
//
// Laengsachse ist `achse` ('x' = horizontal, 'y' = senkrecht). Die
// Bounding-Box entspricht exakt `size`: Gurte sitzen um ihren Radius nach innen
// versetzt, die Streben liegen dazwischen. Gleiche Masse teilen sich EINE
// Geometrie (Cache-Schluessel auf mm gerundet).
const _mm = (v) => Math.round(Math.max(Number(v) || 0, 0.01) * 1000) / 1000;

function trussGeometrie(size, achse) {
  const laenge = _mm(achse === 'y' ? size.y : size.x);
  const quer = _mm(achse === 'y' ? size.x : size.y);   // vor dem Drehen: lokal Y
  const tiefe = _mm(size.z);
  return geteilteGeometrie(`truss|${achse}|${laenge}|${quer}|${tiefe}`, () => {
    const rG = Math.min(0.025, quer / 6, tiefe / 6);    // Gurtrohr
    const rS = rG * 0.38;                               // Strebe
    const hy = quer / 2 - rG;
    const hz = tiefe / 2 - rG;
    const x0 = -laenge / 2;
    const felder = Math.max(1, Math.round(laenge / 0.5));
    // Knoten um den Gurtradius nach innen: sonst ragt das Strebenende ueber
    // das Traversenende hinaus und die Bounding-Box waere groesser als `size`.
    const innen = laenge - 2 * rG;
    const schritt = innen / felder;
    const teile = [];
    // 4 Gurte, je mit Deckeln (sichtbare Rohrenden).
    const gurte = [[hy, hz], [hy, -hz], [-hy, -hz], [-hy, hz]];
    // 12 Segmente (Vielfaches von 4): die Polygon-Ecken liegen genau auf den
    // Aussenkanten, die Bounding-Box trifft `size` also exakt.
    for (const [y, z] of gurte) teile.push(rohr([x0, y, z], [x0 + laenge, y, z], rG, 12, false));
    // Je Seitenflaeche: Zickzack-Diagonalen + Endsprossen. Die Flaechen sind die
    // vier Paare benachbarter Gurte (oben, vorn, unten, hinten).
    for (let k = 0; k < 4; k++) {
      const A = gurte[k], B = gurte[(k + 1) % 4];
      for (let i = 0; i < felder; i++) {
        const xa = x0 + rG + i * schritt, xb = xa + schritt;
        const [von, nach] = (i % 2 === 0) ? [A, B] : [B, A];
        teile.push(rohr([xa, von[0], von[1]], [xb, nach[0], nach[1]], rS, 6, true));
      }
      for (const x of [x0 + rG, x0 + laenge - rG]) {
        teile.push(rohr([x, A[0], A[1]], [x, B[0], B[1]], rS, 6, true));
      }
    }
    const geo = verschmelzen(teile);
    if (achse === 'y') geo.rotateZ(Math.PI / 2);        // X -> Y (lokal Y -> -X)
    return geo;
  });
}

function buildTruss(size, color, achse) {
  const group = new THREE.Group();
  const mesh = new THREE.Mesh(
    trussGeometrie(size, achse),
    new THREE.MeshStandardMaterial({ color: color, metalness: 0.7, roughness: 0.4 })
  );
  mesh.castShadow = true;
  mesh.receiveShadow = true;
  mesh.userData.trussGeometrie = true;
  mesh.userData.laengsAchse = achse;
  group.add(mesh);
  group.userData.isTrussGroup = true;
  group.userData.color = color;
  group.userData.size = { x: size.x, y: size.y, z: size.z };
  return group;
}


// ── VIZ-68: Objekt-Bibliothek (Event-Moebel) ────────────────────────────────
// Wie VIZ-66 komplett im Code gebaut, keine Modelldateien. Jede Form fuellt
// ihre Bounding-Box EXAKT (`size` = Breite x Hoehe x Tiefe, Mittelpunkt im
// Ursprung) und skaliert mit ihr — das Groesse-Aendern baut neu (Group-Pfad in
// updateStageObjectProps). Je Objekt hoechstens ZWEI Meshes: Korpus in der
// Objektfarbe, Gestell als Metall mit `userData.eigeneFarbe` (eine
// Farbaenderung faerbt nur den Korpus). Gleiche Masse teilen sich die
// Geometrie (geteilteGeometrie, Schluessel auf mm gerundet) — dreissig
// Biertische kosten EINE Form.

const _metall = () => new THREE.MeshStandardMaterial({ color: 0x8a8f96, metalness: 0.75, roughness: 0.35 });

/** Quader w x h x d mit Mittelpunkt (x, y, z) — Baustein der Moebel. */
function _quader(w, h, d, x, y, z) {
  return new THREE.BoxGeometry(Math.max(w, 0.005), Math.max(h, 0.005), Math.max(d, 0.005))
    .translate(x, y, z);
}

/** Zylinder (Achse Y), elliptisch auf rx/rz gestreckt, Mittelpunkt y. */
function _scheibe(rx, rz, h, y, segmente) {
  const g = new THREE.CylinderGeometry(1, 1, Math.max(h, 0.005), segmente || 32);
  return platziere(g, [0, y, 0], null, [Math.max(rx, 0.005), 1, Math.max(rz, 0.005)]);
}

function _moebel(typ, size, color, teileKorpus, teileGestell) {
  const sx = _mm(size.x), sy = _mm(size.y), sz = _mm(size.z);
  const key = typ + '|' + sx + '|' + sy + '|' + sz;
  const korpus = geteilteGeometrie(key + '|k', () => verschmelzen(teileKorpus(sx, sy, sz)));
  const group = new THREE.Group();
  const mk = new THREE.Mesh(korpus, new THREE.MeshStandardMaterial({ color: color, roughness: 0.8, metalness: 0.05 }));
  mk.castShadow = true; mk.receiveShadow = true;
  group.add(mk);
  if (teileGestell) {
    const gestell = geteilteGeometrie(key + '|g', () => verschmelzen(teileGestell(sx, sy, sz)));
    const mg = new THREE.Mesh(gestell, _metall());
    mg.userData.eigeneFarbe = true;
    mg.castShadow = true;
    group.add(mg);
  }
  group.userData.color = color;
  group.userData.size = { x: size.x, y: size.y, z: size.z };
  group.userData.moebel = typ;
  return group;
}

// Biertischgarnitur: Tisch in der Mitte, zwei Baenke laengs davor/dahinter.
function buildBiertischgarnitur(size, color) {
  return _moebel('beer_table', size, color,
    (L, H, D) => {
      const t = Math.min(0.035, H * 0.05);                  // Plattenstaerke
      const tisch = D * 0.38, bank = D * 0.19, hb = H * 0.62;
      return [
        _quader(L, t, tisch, 0, H / 2 - t / 2, 0),
        _quader(L, t, bank, 0, -H / 2 + hb - t / 2, D / 2 - bank / 2),
        _quader(L, t, bank, 0, -H / 2 + hb - t / 2, -(D / 2 - bank / 2)),
      ];
    },
    (L, H, D) => {
      const t = Math.min(0.035, H * 0.05);
      const tisch = D * 0.38, bank = D * 0.19, hb = H * 0.62, s = 0.03;
      const rand = Math.min(0.25, L * 0.12);
      const teile = [];
      for (const x of [-(L / 2 - rand), L / 2 - rand]) {
        for (const z of [-tisch * 0.32, tisch * 0.32]) {          // Tischbeine
          teile.push(_quader(s, H - t, s, x, -t / 2, z));
        }
        for (const z of [D / 2 - bank / 2, -(D / 2 - bank / 2)]) {  // Bankbeine
          teile.push(_quader(s, hb - t, s, x, -H / 2 + (hb - t) / 2, z));
        }
      }
      return teile;
    });
}

// Stehtisch: runde (bzw. elliptische) Platte, Saeule, Fussteller.
function buildStehtisch(size, color) {
  return _moebel('high_table', size, color,
    (W, H, D) => {
      const t = Math.min(0.03, H * 0.05);
      return [_scheibe(W / 2, D / 2, t, H / 2 - t / 2)];
    },
    (W, H, D) => {
      const t = Math.min(0.03, H * 0.05), fuss = Math.min(0.02, H * 0.03);
      const r = Math.min(W, D) * 0.06;
      return [
        _scheibe(r, r, H - t - fuss, -H / 2 + fuss + (H - t - fuss) / 2, 16),
        _scheibe(W * 0.32, D * 0.32, fuss, -H / 2 + fuss / 2, 32),
      ];
    });
}

// Bar / Theke: Korpus mit ueberstehender Platte (Gaesteseite +Z), Fussreling.
function buildBar(size, color) {
  return _moebel('bar_counter', size, color,
    (L, H, D) => {
      const t = Math.min(0.05, H * 0.06);
      const korpusTiefe = D * 0.78;
      return [
        _quader(L, t, D, 0, H / 2 - t / 2, 0),
        _quader(L, H - t, korpusTiefe, 0, -t / 2, -(D - korpusTiefe) / 2),
      ];
    },
    (L, H, D) => {
      const r = Math.min(0.025, D * 0.04);
      const z = D / 2 - r - 0.0001, y = -H / 2 + Math.min(0.22, H * 0.2);
      const x0 = -L / 2 + 0.06, x1 = L / 2 - 0.06;
      return [rohr([x0, y, z], [x1, y, z], r, 12, false)];
    });
}

// Podest mit Treppe: Podest hinten (-Z), Treppe mittig zur Vorderseite (+Z).
function buildPodestTreppe(size, color) {
  return _moebel('riser_stairs', size, color,
    (W, H, D) => {
      const n = Math.max(1, Math.round(H / 0.2) - 1);       // Stufen unter der Podestkante
      const tritt = Math.min(0.3, (D * 0.5) / n);
      const tt = n * tritt;
      const breite = Math.min(1.2, W * 0.6);
      const teile = [_quader(W, H, D - tt, 0, 0, -tt / 2)];
      for (let k = 1; k <= n; k++) {
        const h = H * k / (n + 1);
        // k = 1 vorderste/niedrigste Stufe; jede Stufe reicht bis zum Boden.
        teile.push(_quader(breite, h, tritt, 0, -H / 2 + h / 2, D / 2 - tt + (n - k + 0.5) * tritt));
      }
      return teile;
    },
    null);
}

// Mischpult-Tisch (FOH): Tisch mit flachem, nach vorn geneigt gedachtem
// Pult-Aufsatz (als Stufe angenaehert), Metallbeine.
function buildMischpultTisch(size, color) {
  return _moebel('foh_desk', size, color,
    (L, H, D) => {
      const t = Math.min(0.04, H * 0.05);
      const tischH = H * 0.82;                       // Tischkante
      const pult = H - tischH;                       // Pult-Aufsatz
      return [
        _quader(L, t, D, 0, -H / 2 + tischH - t / 2, 0),
        _quader(L * 0.86, pult, D * 0.62, 0, -H / 2 + tischH + pult / 2, -D * 0.12),
      ];
    },
    (L, H, D) => {
      const t = Math.min(0.04, H * 0.05), tischH = H * 0.82, s = 0.04;
      const teile = [];
      for (const x of [-(L / 2 - s / 2), L / 2 - s / 2]) {
        for (const z of [-(D / 2 - s / 2), D / 2 - s / 2]) {
          teile.push(_quader(s, tischH - t, s, x, -H / 2 + (tischH - t) / 2, z));
        }
      }
      return teile;
    });
}

export const STAGE_BLUEPRINTS = {
  floor: {
    label: 'Boden / Floor',
    defaultSize: { x: 14, y: 0.1, z: 10 },
    defaultColor: '#1c1c1c',
    build: (size, color) => {
      const m = new THREE.Mesh(
        new THREE.BoxGeometry(size.x, size.y, size.z),
        new THREE.MeshStandardMaterial({ color: color, roughness: 0.95, metalness: 0.0 })
      );
      m.receiveShadow = true;
      return m;
    },
  },
  platform: {
    label: 'Stage Platform',
    defaultSize: { x: 6, y: 0.4, z: 4 },
    defaultColor: '#332520',
    build: (size, color) => new THREE.Mesh(
      new THREE.BoxGeometry(size.x, size.y, size.z),
      new THREE.MeshStandardMaterial({ color: color, roughness: 0.9 })
    ),
  },
  truss_h: {
    label: 'Truss horizontal',
    defaultSize: { x: 4, y: 0.3, z: 0.3 },
    defaultColor: '#999999',
    build: (size, color) => buildTruss(size, color, 'x'),
  },
  truss_v: {
    label: 'Truss vertical',
    defaultSize: { x: 0.3, y: 4, z: 0.3 },
    defaultColor: '#999999',
    build: (size, color) => buildTruss(size, color, 'y'),
  },
  wall: {
    label: 'Wall / Backdrop',
    defaultSize: { x: 10, y: 6, z: 0.2 },
    defaultColor: '#222230',
    build: (size, color) => new THREE.Mesh(
      new THREE.BoxGeometry(size.x, size.y, size.z),
      new THREE.MeshStandardMaterial({ color: color, roughness: 1.0, side: THREE.DoubleSide })
    ),
  },
  led_wall: {
    label: 'LED Wall',
    defaultSize: { x: 8, y: 4.5, z: 0.15 },
    defaultColor: '#080820',
    build: (size, color) => new THREE.Mesh(
      new THREE.BoxGeometry(size.x, size.y, size.z),
      new THREE.MeshBasicMaterial({ color: color })
    ),
  },
  speaker: {
    label: 'Speaker Stack',
    defaultSize: { x: 1.4, y: 4.5, z: 1.4 },
    defaultColor: '#111111',
    build: (size, color) => new THREE.Mesh(
      new THREE.BoxGeometry(size.x, size.y, size.z),
      new THREE.MeshStandardMaterial({ color: color, roughness: 0.9 })
    ),
  },
  audience: {
    label: 'Audience Area',
    defaultSize: { x: 12, y: 0.05, z: 8 },
    defaultColor: '#0c0c10',
    build: (size, color) => new THREE.Mesh(
      new THREE.BoxGeometry(size.x, size.y, size.z),
      new THREE.MeshStandardMaterial({ color: color, roughness: 1.0 })
    ),
  },
  // VIZ-68: Objekt-Bibliothek
  beer_table: {
    label: 'Biertischgarnitur',
    defaultSize: { x: 2.2, y: 0.76, z: 1.3 },
    defaultColor: '#4a3624',
    build: (size, color) => buildBiertischgarnitur(size, color),
  },
  high_table: {
    label: 'Stehtisch',
    defaultSize: { x: 0.8, y: 1.1, z: 0.8 },
    defaultColor: '#d8d2c4',
    build: (size, color) => buildStehtisch(size, color),
  },
  bar_counter: {
    label: 'Bar / Theke',
    defaultSize: { x: 3.0, y: 1.1, z: 0.8 },
    defaultColor: '#3a2a20',
    build: (size, color) => buildBar(size, color),
  },
  riser_stairs: {
    label: 'Podest mit Treppe',
    defaultSize: { x: 2.0, y: 0.6, z: 2.8 },
    defaultColor: '#332520',
    build: (size, color) => buildPodestTreppe(size, color),
  },
  foh_desk: {
    label: 'Mischpult-Tisch',
    defaultSize: { x: 1.8, y: 0.9, z: 0.9 },
    defaultColor: '#222226',
    build: (size, color) => buildMischpultTisch(size, color),
  },
  dj_booth: {
    label: 'DJ Booth',
    defaultSize: { x: 2.4, y: 1.2, z: 1.0 },
    defaultColor: '#1a1a25',
    build: (size, color) => new THREE.Mesh(
      new THREE.BoxGeometry(size.x, size.y, size.z),
      new THREE.MeshStandardMaterial({ color: color, roughness: 0.7, metalness: 0.3 })
    ),
  },
};

export function createStageObject(type, position, size, color, rotation, providedId, name) {
  const bp = STAGE_BLUEPRINTS[type];
  if (!bp) return null;
  const sz = size || { ...bp.defaultSize };
  const cl = color || bp.defaultColor;
  const mesh = bp.build(sz, cl);
  mesh.castShadow = true;
  mesh.receiveShadow = true;
  if (position) mesh.position.set(
    (position.x != null) ? position.x : 0,
    (position.y != null) ? position.y : (sz.y / 2),
    (position.z != null) ? position.z : 0
  );
  else mesh.position.set(0, sz.y / 2, 0);
  mesh.rotation.y = rotation || 0;
  // ID-FIX: Python-seitige IDs respektieren (sonst stimmen select/update nicht ueberein)
  let id = (providedId && typeof providedId === 'string') ? providedId : ('stage-' + (stageObjIdCounter++));
  // Falls Kollision (sehr unwahrscheinlich): Suffix dranhaengen
  if (stageObjects[id]) id = id + '_' + (stageObjIdCounter++);
  mesh.userData.stageId = id;
  mesh.userData.isStageObject = true;
  mesh.userData.stageType = type;
  _userRemovedIds.delete(id);   // bewusstes Neu-Anlegen hebt den Lösch-Tombstone auf
  scene.add(mesh);
  stageObjects[id] = {
    mesh,
    data: {
      id, type,
      position: { x: mesh.position.x, y: mesh.position.y, z: mesh.position.z },
      size: { ...sz },
      rotation: mesh.rotation.y,
      color: cl,
      name: name || '',
    }
  };
  // Falls aktuell 2D-Ansicht: frisch erzeugtes Objekt sofort 2D-stylen.
  applyStageObject2DStyle(id, view.mode === '2D');
  notifyStageListChanged();
  updateEmptyState();   // VIZ-14: erstes Buehnenobjekt da -> Hinweis weg
  requestRender();  // 3c-2 Dirty-Quelle 4 (Stage-CRUD: Objekt hinzugefuegt)
  return id;
}

// Update existing stage object in-place (geometry, color, position, rotation)
// Returns true if updated, false if not found
export function updateStageObjectProps(id, props) {
  const so = stageObjects[id];
  if (!so) return false;
  const data = so.data;

  // Size: replace geometry (Mesh) or rebuild scale (Group with loaded model / truss)
  // VIZ-87: nur bei echter Aenderung. Jedes Laden schickt jedes Element noch
  // zweimal als addStageData hinterher (push_stage_definition + Reassert nach
  // 1,2 s) — bei unveraenderter Groesse baute das bisher jede Truss, LED-Wand
  // und Treppe neu, also die halbe Buehne dreimal je Stufenwechsel.
  const groesseNeu = props.size && (
    (props.size.x != null && Math.abs(props.size.x - data.size.x) > 1e-9)
    || (props.size.y != null && Math.abs(props.size.y - data.size.y) > 1e-9)
    || (props.size.z != null && Math.abs(props.size.z - data.size.z) > 1e-9));
  if (groesseNeu) {
    const sz = props.size;
    if (sz.x != null) data.size.x = sz.x;
    if (sz.y != null) data.size.y = sz.y;
    if (sz.z != null) data.size.z = sz.z;
    if (so.mesh.isMesh && so.mesh.geometry) {
      so.mesh.geometry.dispose();
      so.mesh.geometry = new THREE.BoxGeometry(data.size.x, data.size.y, data.size.z);
    } else if (so.mesh.isGroup) {
      // Rebuild the group entirely (cheap - Traversen-Geometrie kommt aus dem Cache)
      const type = data.type;
      const bp = STAGE_BLUEPRINTS[type];
      if (bp) {
        const newGroup = bp.build({ x: data.size.x, y: data.size.y, z: data.size.z }, data.color);
        newGroup.position.copy(so.mesh.position);
        newGroup.rotation.copy(so.mesh.rotation);
        newGroup.userData.stageId = data.id;
        newGroup.userData.isStageObject = true;
        newGroup.userData.stageType = type;
        scene.remove(so.mesh);
        so.mesh.traverse(disposeObj);
        scene.add(newGroup);
        so.mesh = newGroup;
        // Auswahl-BoxHelper zeigte noch auf das alte (entfernte/disposte) Mesh ->
        // INLINE fuer newGroup neu aufbauen, sonst friert der gelbe Auswahlrahmen
        // auf der alten Geometrie ein. (Bewusst NICHT updateOutlines() — das wuerde
        // pro Rasterschritt Selektions-Signale an Python feuern + den Banner-DOM neu
        // bauen.) Sichtbarkeit des alten Helpers uebernehmen (selektiert vs. nicht).
        if (so._helper) {
          const wasVisible = so._helper.visible;
          scene.remove(so._helper);
          if (so._helper.geometry) so._helper.geometry.dispose();
          if (so._helper.material) so._helper.material.dispose();
          so._helper = new THREE.BoxHelper(so.mesh, 0xffd700);
          if (so._helper.material) {
            so._helper.material.depthTest = false;
            so._helper.material.transparent = true;
            so._helper.material.opacity = 1.0;
          }
          so._helper.visible = wasVisible;
          scene.add(so._helper);
          so._helper.update();
        }
      }
    }
  }

  // Color: update material (works on Mesh or recursively on Group)
  // VIZ-87: gleiche Farbe = nichts zu tun (s. Groesse).
  if (props.color && String(props.color).toLowerCase() !== String(data.color || '').toLowerCase()) {
    data.color = props.color;
    const col = new THREE.Color(props.color);
    if (so.mesh.isMesh && so.mesh.material) {
      so.mesh.material.color = col;
    } else if (so.mesh.isGroup) {
      so.mesh.traverse(c => {
        // VIZ-68: Gestell/Metall behaelt seine Farbe.
        if (c.isMesh && c.material && c.material.color && !c.userData.eigeneFarbe) {
          c.material.color = col.clone();
        }
      });
      so.mesh.userData.color = props.color;
    }
  }

  // Position
  if (props.position) {
    const p = props.position;
    if (p.x != null) { data.position.x = p.x; so.mesh.position.x = p.x; }
    if (p.y != null) { data.position.y = p.y; so.mesh.position.y = p.y; }
    if (p.z != null) { data.position.z = p.z; so.mesh.position.z = p.z; }
  }

  // Rotation
  if (props.rotation != null) {
    data.rotation = props.rotation;
    so.mesh.rotation.y = props.rotation;
  }

  // Name
  if (props.name != null) data.name = props.name;

  // 2D-View Top-Color update
  updateStageObject2D(id);
  requestRender();  // 3c-2 Dirty-Quelle 4 (Stage-CRUD: Groesse/Farbe/Transform)
  return true;
}

// In 2D-View: render stage objects with distinct top-down colors per type
export const STAGE_2D_COLORS = {
  floor:     { fill: 0x2a2a2a, edge: 0x6a6a6a, label: 'BODEN' },
  platform:  { fill: 0x6b4a3a, edge: 0xc7906a, label: 'PLATFORM' },
  truss_h:   { fill: 0x999999, edge: 0xcccccc, label: 'TRUSS H' },
  truss_v:   { fill: 0x999999, edge: 0xcccccc, label: 'TRUSS V' },
  wall:      { fill: 0x3a3a55, edge: 0x6a6a8a, label: 'WALL' },
  led_wall:  { fill: 0x202060, edge: 0x4080ff, label: 'LED' },
  speaker:   { fill: 0x1a1a1a, edge: 0xff8800, label: 'SPK' },
  audience:  { fill: 0x4a3a2a, edge: 0xb89060, label: 'AUDIENCE' },
  dj_booth:  { fill: 0x2a2a4a, edge: 0x60a0ff, label: 'DJ' },
  beer_table:   { fill: 0x5a4430, edge: 0xc89a60, label: 'BIERTISCH' },
  high_table:   { fill: 0x5a5650, edge: 0xd8d2c4, label: 'STEHTISCH' },
  bar_counter:  { fill: 0x3a2a20, edge: 0xb07040, label: 'BAR' },
  riser_stairs: { fill: 0x6b4a3a, edge: 0xc7906a, label: 'PODEST' },
  foh_desk:     { fill: 0x26262c, edge: 0x9090a0, label: 'FOH' },
};

export function updateStageObject2D(id) {
  // Buehnen-Objekt an den aktuellen View-Modus anpassen (siehe 2D-Style unten).
  applyStageObject2DStyle(id, view.mode === '2D');
}

// ── 2D-OCCLUSION-FIX ─────────────────────────────────────────────────────────
// Im 2D-Top-Down rendern wir User-Buehnenobjekte (Boden/Plattform/Truss/…) NICHT
// mehr als solide Boxen — sonst verdecken sie die flachen Fixture-Icons. Statt-
// dessen: halbtransparent + depthWrite aus, so dass die Grundflaeche als dezenter
// Umriss sichtbar bleibt, die Strahler darunter aber durchscheinen. Im 3D wird
// der Originalzustand des Materials wiederhergestellt.
export function _setMeshMat2D(m, is2D) {
  if (!m || !m.isMesh || !m.material) return;
  const mats = Array.isArray(m.material) ? m.material : [m.material];
  for (const mat of mats) {
    if (!mat) continue;
    if (mat.userData.__orig2d === undefined) {
      mat.userData.__orig2d = {
        transparent: mat.transparent,
        opacity: mat.opacity,
        depthWrite: mat.depthWrite,
      };
    }
    if (is2D) {
      mat.transparent = true;
      mat.opacity = 0.22;
      mat.depthWrite = false;
    } else {
      const o = mat.userData.__orig2d;
      mat.transparent = o.transparent;
      mat.opacity = o.opacity;
      mat.depthWrite = o.depthWrite;
    }
    mat.needsUpdate = true;
  }
  m.renderOrder = is2D ? 1 : 0;
}

export function applyStageObject2DStyle(id, is2D) {
  const so = stageObjects[id];
  if (!so || !so.mesh) return;
  if (so.mesh.isMesh) _setMeshMat2D(so.mesh, is2D);
  else so.mesh.traverse(c => { if (c.isMesh) _setMeshMat2D(c, is2D); });
  _syncFootprintOutline(so, is2D);
  requestRender();  // 3c-2: Material-Styles/Footprint-Umriss geaendert
}

// 3c-1: Grundriss-Umriss — im 2D-Plan bekommt jedes Buehnenobjekt eine klare
// Aussenkante in seiner Typ-Farbe (STAGE_2D_COLORS.edge, vorher ungenutzt).
// Der 0.22-Opacity-Fill allein war auf dem dunklen Boden kaum lesbar. Als
// Kind von so.mesh folgt der Umriss Position/Rotation live; bei Groessen-/
// Group-Rebuilds wird er hier idempotent neu erzeugt (applyStageObject2DStyle
// laeuft nach jedem createStageObject/updateStageObjectProps/Modus-Wechsel).
function _syncFootprintOutline(so, is2D) {
  if (so._outline2d) {
    if (so._outline2d.parent) so._outline2d.parent.remove(so._outline2d);
    if (so._outline2d.geometry) so._outline2d.geometry.dispose();
    if (so._outline2d.material) so._outline2d.material.dispose();
    so._outline2d = null;
  }
  if (!is2D) return;
  const sz = (so.data && so.data.size) || {};
  const hx = (sz.x || 1) / 2, hz = (sz.z || 1) / 2;
  const y = (sz.y || 0) / 2 + 0.02;   // knapp ueber der Oberkante (depthTest ist eh aus)
  const pts = [
    new THREE.Vector3(-hx, y, -hz), new THREE.Vector3(hx, y, -hz),
    new THREE.Vector3(hx, y, hz), new THREE.Vector3(-hx, y, hz),
  ];
  const colors = STAGE_2D_COLORS[so.data && so.data.type];
  const line = new THREE.LineLoop(
    new THREE.BufferGeometry().setFromPoints(pts),
    new THREE.LineBasicMaterial({
      color: (colors && colors.edge) || 0x8a8fa0,
      transparent: true, opacity: 0.95, depthTest: false,
    })
  );
  line.renderOrder = 2;   // ueber den 2D-Fills (1), unter den Fixture-Icons (3)
  line.userData.isFootprintOutline = true;
  // Vom Raycast ausnehmen: pickStageObject/findDockTarget/Zielen laufen
  // rekursiv ueber so.mesh, und three.js raycastet Lines mit ~1 m Threshold —
  // der Umriss wuerde Picking/Docking sonst unpraezise machen.
  line.raycast = function () {};
  so.mesh.add(line);
  so._outline2d = line;
}

export function removeStageObject(id) {
  const so = stageObjects[id];
  if (!so) return;
  // BoxHelper + Label entfernen
  if (so._helper) {
    scene.remove(so._helper);
    if (so._helper.geometry) so._helper.geometry.dispose();
    if (so._helper.material) so._helper.material.dispose();
    so._helper = null;
  }
  if (so._label) {
    scene.remove(so._label);
    if (so._label.material && so._label.material.map) so._label.material.map.dispose();
    if (so._label.material) so._label.material.dispose();
    so._label = null;
  }
  // 3c-1: Grundriss-Umriss mit-disposen (disposeObj traversiert nicht)
  _syncFootprintOutline(so, false);
  scene.remove(so.mesh);
  // VIZ-66: traversieren, sonst bliebe das Material des Traversen-Kinds
  // liegen (geteilte Geometrie ueberspringt disposeObj selbst).
  so.mesh.traverse(disposeObj);
  delete stageObjects[id];
  updateEmptyState();   // VIZ-14
  if (view.selectedStageId === id) {
    view.selectedStageId = null;
    clearResizeHandles();
  }
  if (dockHighlightRef.get() === id) dockHighlightRef.set(null);
  // Ein finaler, expliziter Delete ist etwas anderes als die vielen
  // remove-Aufrufe innerhalb von loadStageJson(). Nur ersterer darf Python
  // aus seinem autoritativen Bühnenmodell entfernen.
  if (!_isLoadingStage) {
    _userRemovedIds.add(id);
    const bridge = bridgeRef.get();
    if (bridge && bridge.stageObjectDeleted) {
      try { bridge.stageObjectDeleted(id); } catch (e) {}
    }
  }
  // Angedockte Strahler loesen (bleiben an letzter Position)
  for (const fid in fixtures) {
    const f = fixtures[fid];
    if (f && f.dockedTo === id) {
      f.dockedTo = null;
      const bridge = bridgeRef.get();
      if (bridge && bridge.fixtureDockChanged) {
        try { bridge.fixtureDockChanged(String(fid), ''); } catch (e) {}
      }
    }
  }
  updateOutlinesRef.get()();
  notifyStageListChanged();
  requestRender();  // 3c-2 Dirty-Quelle 4 (Stage-CRUD: Objekt entfernt)
}

export function clearStageObjects() {
  // Snapshot der IDs - sonst mutieren wir waehrend Iteration
  const ids = Object.keys(stageObjects).slice();
  for (const id of ids) removeStageObject(id);
  // Defensiv: Falls etwas haengt
  for (const id in stageObjects) delete stageObjects[id];
  updateEmptyState();   // VIZ-14
  clearResizeHandles();
  clearStageLabels();
}

// ============================================================================
// Resize-Handles (4 gelbe Wuerfel an den Box-Ecken, 2D-Editmodus)
// ============================================================================
export let resizeHandles = [];          // Array von Mesh-Handles (in scene)
export let resizeModeEnabled = false;   // Toggle: nur wenn aktiv erscheinen Resize-Handles

export function setResizeModeEnabled(on) {
  resizeModeEnabled = !!on;
  updateResizeHandles();
}

export function clearResizeHandles() {
  if (resizeHandles.length) requestRender();  // 3c-2: Handles verschwinden
  for (const h of resizeHandles) {
    scene.remove(h);
    if (h.geometry) h.geometry.dispose();
    if (h.material) h.material.dispose();
  }
  resizeHandles.length = 0;
}

export function updateResizeHandles() {
  clearResizeHandles();
  // Resize-Handles nur wenn explizit aktiviert (Toggle "Groesse anpassen")
  if (!resizeModeEnabled) return;
  if (view.editMode !== 'stage' || !view.selectedStageId) return;
  const so = stageObjects[view.selectedStageId];
  if (!so) return;
  const pos = so.mesh.position;
  const halfX = so.data.size.x / 2;
  const halfZ = so.data.size.z / 2;
  const handleY = pos.y + so.data.size.y / 2 + 0.4;
  const handleSize = (view.mode === '2D') ? 0.7 : 0.45;
  const corners = [
    {name: 'nw', x: pos.x - halfX, z: pos.z - halfZ},
    {name: 'ne', x: pos.x + halfX, z: pos.z - halfZ},
    {name: 'sw', x: pos.x - halfX, z: pos.z + halfZ},
    {name: 'se', x: pos.x + halfX, z: pos.z + halfZ},
  ];
  for (const c of corners) {
    const geo = new THREE.BoxGeometry(handleSize, handleSize, handleSize);
    const mat = new THREE.MeshBasicMaterial({color: 0xffd700, transparent: true, opacity: 0.95});
    const m = new THREE.Mesh(geo, mat);
    m.position.set(c.x, handleY, c.z);
    m.userData = {isResizeHandle: true, corner: c.name, stageId: view.selectedStageId};
    scene.add(m);
    resizeHandles.push(m);
  }
  requestRender();  // 3c-2: Handles neu aufgebaut
}

export function pickResizeHandle() {
  raycaster.setFromCamera(mouse, view.activeCam);
  const hits = raycaster.intersectObjects(resizeHandles, false);
  if (hits.length > 0) return hits[0].object;
  return null;
}

// ============================================================================
// 3D-Text-Labels (Sprite mit Canvas-Texture) ueber jedem Stage-Element
// ============================================================================
export function makeLabelSprite(text, color) {
  const canvas = document.createElement('canvas');
  canvas.width = 256;
  canvas.height = 64;
  const ctx = canvas.getContext('2d');
  ctx.clearRect(0, 0, 256, 64);
  // Hintergrund halbtransparent
  ctx.fillStyle = 'rgba(20, 20, 30, 0.78)';
  ctx.fillRect(0, 0, 256, 64);
  ctx.strokeStyle = color || '#ffd700';
  ctx.lineWidth = 3;
  ctx.strokeRect(2, 2, 252, 60);
  ctx.fillStyle = color || '#ffd700';
  ctx.font = 'bold 30px Segoe UI, Tahoma, sans-serif';
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  ctx.fillText(String(text).toUpperCase(), 128, 32);
  const tex = new THREE.CanvasTexture(canvas);
  tex.needsUpdate = true;
  const mat = new THREE.SpriteMaterial({map: tex, transparent: true, depthTest: false});
  const sprite = new THREE.Sprite(mat);
  sprite.scale.set(3.0, 0.75, 1);
  return sprite;
}

export function clearStageLabels() {
  for (const id in stageObjects) {
    const so = stageObjects[id];
    if (so._label) {
      scene.remove(so._label);
      if (so._label.material && so._label.material.map) so._label.material.map.dispose();
      if (so._label.material) so._label.material.dispose();
      so._label = null;
    }
  }
}

export function ensureLabel(id) {
  const so = stageObjects[id];
  if (!so) return;
  const typeLabel = (STAGE_2D_COLORS[so.data.type] && STAGE_2D_COLORS[so.data.type].label) || so.data.type;
  const text = so.data.name ? (so.data.name + ' [' + typeLabel + ']') : typeLabel;
  if (so._label) {
    // Update vorhandenes Label
    scene.remove(so._label);
    if (so._label.material && so._label.material.map) so._label.material.map.dispose();
    if (so._label.material) so._label.material.dispose();
  }
  so._label = makeLabelSprite(text, '#ffd700');
  scene.add(so._label);
}

export function updateStageLabelPositions() {
  for (const id in stageObjects) {
    const so = stageObjects[id];
    if (!so._label) continue;
    so._label.position.set(
      so.mesh.position.x,
      so.mesh.position.y + so.data.size.y / 2 + 1.2,
      so.mesh.position.z
    );
  }
}

export function getStageJson() {
  return {
    name: 'CustomStage',
    objects: Object.values(stageObjects).map(s => ({
      id: s.data.id,
      type: s.data.type,
      name: s.data.name || '',
      position: { ...s.data.position },
      size: { ...s.data.size },
      rotation: s.data.rotation,
      color: s.data.color,
    })),
    fixtures: Object.entries(fixtures).map(([fid, f]) => ({
      fid: Number(fid),
      x: f.group.position.x,
      y: f.group.position.y,
      z: f.group.position.z,
      // Rotationen hier in Radiant (interner JS-Roundtrip, kein Bridge-Grad).
      rotationX: f.group.rotation.x,
      rotationY: f.group.rotation.y,
      rotationZ: f.group.rotation.z,
    })),
  };
}

// FLICKER-FIX: Während eines kompletten Stage-Loads dürfen die
// einzelnen create/remove-Operationen NICHT jeweils zurück an Python
// melden – das löst sonst N×Tree-Rebuilds aus.
let _isLoadingStage = false;

// Tombstones expliziter Löschungen seit dem letzten Bulk-Load: der
// Repair-Loop (loadStageJson-finally) darf ein gerade erst gelöschtes
// Element NICHT aus seinen veralteten expectedObjects reanimieren.
// Ein erfolgreiches Neu-Anlegen derselben ID (Undo/Redo, Python-Reassert)
// hebt den Tombstone wieder auf (createStageObject).
const _userRemovedIds = new Set();

/**
 * A3D-12: Traegt dieses Element einen Loesch-Tombstone?
 *
 * Exportiert, damit der INKREMENTELLE Add-Kanal (`jsAddStageObjectData` in
 * bridge.js) ihn respektieren kann. Der Repair-Loop in `loadStageJson` tat das
 * schon immer, der Inkremental-Kanal nicht — ein verspaetet zugestelltes
 * `addStageData` reanimierte damit ein gerade geloeschtes Objekt UND hob per
 * `createStageObject` seinen Tombstone auf.
 *
 * Bewusst als Praedikat statt als Export des Sets: ein exportiertes Set liesse
 * sich von aussen mutieren, und die Tombstone-Lebensdauer ist hier drin geregelt
 * (gesetzt in `removeStageObject`, geleert in `loadStageJson`, aufgehoben von
 * `createStageObject`).
 */
export function isUserRemoved(id) {
  return _userRemovedIds.has(id);
}

// Review-Fix (Stage-Echo-Race): Sequenz-Token aus der zuletzt per
// loadStageJson() empfangenen Buehnen-Definition ("_reloadToken", von
// push_stage_definition() vergeben). JEDES notifyStageListChanged()-Echo
// traegt diesen Token zurueck an Python, damit ein spaet eintreffendes Echo
// aus einem inzwischen ueberholten Reload dort als STALE erkannt und dessen
// destruktiver Loesch-Abgleich uebersprungen werden kann.
let _currentStageReloadToken = null;

// VIZ-87: steht genau diese Buehne schon in der Szene? Verglichen wird mit
// dem, was die Objekte JETZT tragen (`so.data`, gleiches Format wie
// StageElement.to_js_dict) — nicht mit dem letzten Load: Aenderungen seither
// (Ziehen im 3D, Python-Inkremente) zaehlen als Unterschied.
function _gleich(a, b) {
  if (typeof a === 'number' || typeof b === 'number') {
    return Math.abs(Number(a) - Number(b)) < 1e-6;
  }
  return (a == null ? '' : String(a)) === (b == null ? '' : String(b));
}
function stageStimmtUeberein(objekte) {
  if (!Array.isArray(objekte)) return false;
  for (const o of objekte) {
    const so = o && o.id && stageObjects[o.id];
    if (!so) return false;
    const d = so.data;
    const p = o.position || {}, z = o.size || {};
    if (d.type !== o.type) return false;
    if (!_gleich(d.position.x, p.x) || !_gleich(d.position.y, p.y)
        || !_gleich(d.position.z, p.z)) return false;
    if (!_gleich(d.size.x, z.x) || !_gleich(d.size.y, z.y)
        || !_gleich(d.size.z, z.z)) return false;
    if (!_gleich(d.rotation || 0, o.rotation || 0)) return false;
    if (!_gleich(String(d.color || '').toLowerCase(), String(o.color || '').toLowerCase())) return false;
    if (!_gleich(d.name || '', o.name || '')) return false;
  }
  return true;
}

export function loadStageJson(json) {
  const incoming = typeof json === 'string' ? JSON.parse(json) : json;
  const incomingToken = incoming && incoming._reloadToken;
  // Die QtWebChannel-Signale werden zusätzlich über pollControl zugestellt.
  // Sobald die direkte Zustellung doch greift, erreicht derselbe Bulk-Push
  // den View somit zweimal. Ein zweiter clear/create-Durchlauf während/kurz
  // nach dem ersten machte sich bei komplexen Bühnen als partiell geleerte
  // Elementliste bemerkbar. Ein Reload-Token ist pro Python-Push eindeutig;
  // identische, bereits vollständig vorhandene Tokens sind daher strikt
  // idempotent und brauchen keinen erneuten Szenenaufbau.
  const incomingIds = (incoming && Array.isArray(incoming.objects))
    ? incoming.objects.map(o => o && o.id).filter(Boolean).sort()
    : [];
  const currentIds = Object.keys(stageObjects).sort();
  const isAlreadyComplete = incomingIds.length === currentIds.length
    && incomingIds.every((id, index) => id === currentIds[index]);
  if (typeof incomingToken === 'number'
      && incomingToken === _currentStageReloadToken
      && isAlreadyComplete) {
    return;
  }
  // VIZ-87: NEUER Token, aber dieselbe Buehne, die schon steht. Das ist der
  // Normalfall nach jedem Seiten-Neuladen (Qualitaetsstufe, "Szene neu
  // laden"): die frische Seite baut die Buehne sofort aus dem Poll-Zustand,
  // und 400 ms nach loadFinished schickt Python dieselbe Buehne mit neuem
  // Token noch einmal. Bisher hiess das: alles abreissen und neu bauen — bei
  // grossen Buehnen unter Windows (ANGLE) Sekunden, und das Pending-Gate in
  // Python lief derweil in seinen 6-s-Rueckfall ("pending stage snapshot
  // blieb aus"). Jetzt: Token uebernehmen, Auswahl wie bei einem Load
  // zuruecksetzen und das finale Echo schicken — ohne Neubau.
  if (typeof incomingToken === 'number' && isAlreadyComplete
      && !(Array.isArray(incoming.fixtures) && incoming.fixtures.length)
      && stageStimmtUeberein(incoming.objects)) {
    _currentStageReloadToken = incomingToken;
    _userRemovedIds.clear();
    view.selectedStageId = null;
    clearResizeHandles();
    try { updateOutlinesRef.get()(); } catch (e) { /* Auswahl-UI best effort */ }
    notifyStageListChanged();
    requestRender();
    return;
  }
  _isLoadingStage = true;
  try {
    const data = incoming;
    if (typeof data._reloadToken === 'number') _currentStageReloadToken = data._reloadToken;
    // Ein frischer autoritativer Load ueberschreibt alte Loesch-Tombstones:
    // was Python jetzt pusht, gilt.
    _userRemovedIds.clear();
    clearStageObjects();
    view.selectedStageId = null;
    clearResizeHandles();
    clearStageLabels();
    if (data.objects && Array.isArray(data.objects)) {
      data.objects.forEach(o => {
        // Per-Element-Fangnetz: EIN defektes Element (z.B. Build-Throw bei
        // GPU-Context-Loss) darf den restlichen Bulk-Bau nicht abreissen —
        // sonst bleibt von einer 15-Element-Buehne nur Element #0 uebrig
        // (Live-Befund 2026-07-11).
        try {
          createStageObject(o.type, o.position, o.size, o.color, o.rotation, o.id, o.name);
        } catch (e) {
          console.log('loadStageJson: Element uebersprungen', o && o.id, e);
        }
      });
    }
    if (data.fixtures && Array.isArray(data.fixtures)) {
      data.fixtures.forEach(fp => {
        const f = fixtures[fp.fid];
        if (f) {
          f.group.position.set(fp.x || 0, fp.y || 6.5, fp.z || 0);
          if (typeof fp.rotationX === 'number') f.group.rotation.x = fp.rotationX;
          if (typeof fp.rotationY === 'number') f.group.rotation.y = fp.rotationY;
          if (typeof fp.rotationZ === 'number') f.group.rotation.z = fp.rotationZ;
        }
      });
    }
    updateOutlinesRef.get()();
  } catch (e) {
    console.log('loadStageJson error:', e);
  } finally {
    _isLoadingStage = false;
    // EINE einzige finale Sync ans Python schicken (statt N×)
    notifyStageListChanged();
    // QtWebEngine kann direkt nach einem großen QWebChannel-Callback einen
    // unvollständigen stageObjects-Snapshot rendern. Der vollständige Payload
    // ist lokal vorhanden, daher lassen sich fehlende IDs ohne einen weiteren
    // Python-Roundtrip idempotent ergänzen. Die kurzen Wiederholungen decken
    // späte WebGL-/Modell-Callbacks ab, ohne spätere User-Löschungen dauerhaft
    // zurückzunehmen.
    const expectedObjects = Array.isArray(incoming && incoming.objects)
      ? incoming.objects.slice() : [];
    // Zombie-Guards (Review 2026-07-11): (1) ein NEUERER Load (anderer
    // Token) macht diese Repair-Kette obsolet — sonst reanimiert sie
    // Elemente der VORHERIGEN Buehne; (2) explizit geloeschte IDs
    // (_userRemovedIds-Tombstone) bleiben geloescht; (3) per-Element-
    // try/catch, damit ein Dauer-Thrower die restliche Reparatur und die
    // Folgeversuche nicht abwuergt.
    const armedToken = _currentStageReloadToken;
    let repairAttempt = 0;
    const repairIncompleteStage = () => {
      if (_currentStageReloadToken !== armedToken) return;
      const missing = expectedObjects.filter(o => o && o.id
        && !stageObjects[o.id] && !_userRemovedIds.has(o.id));
      let repaired = 0;
      for (const o of missing) {
        try {
          createStageObject(o.type, o.position, o.size, o.color, o.rotation, o.id, o.name);
          repaired += 1;
        } catch (e) {
          console.log('stage repair: Element uebersprungen', o && o.id, e);
        }
      }
      if (repaired) notifyStageListChanged();
      repairAttempt += 1;
      if (repairAttempt < 3) setTimeout(repairIncompleteStage, 300);
    };
    if (expectedObjects.length) setTimeout(repairIncompleteStage, 120);
    // 3c-2: Bulk-Load deckt auch den direkten Fixture-Transform-Zweig oben
    // (f.group.position/rotation OHNE verdrahteten Helfer) + den Fehlerfall ab.
    requestRender();
  }
}

// VIZ-68 (Review A): gebuendeltes Anlegen/Entfernen (Raster). Jedes
// notifyStageListChanged serialisiert die GANZE Liste — je Element einmal war
// bei einem Raster quadratisch. In `gebuendelt(fn)` meldet nur das Ende.
let _buendeln = 0;
export function gebuendelt(fn) {
  _buendeln++;
  try {
    return fn();
  } finally {
    _buendeln--;
    if (_buendeln === 0) notifyStageListChanged();
  }
}

export function notifyStageListChanged() {
  if (_isLoadingStage) return;  // unterdrücken während Bulk-Load
  if (_buendeln) return;        // VIZ-68: Raster meldet einmal am Ende
  const bridge = bridgeRef.get();
  if (bridge && bridge.stageListChanged) {
    const payload = {
      objects: Object.values(stageObjects).map(s => s.data),
      _reloadToken: _currentStageReloadToken,
    };
    try { bridge.stageListChanged(JSON.stringify(payload)); } catch (e) {}
  }
}

// ── Spaet-Bindung (zirkulaere Abhaengigkeiten aufloesen, wie im Design-
// Dokument Abschnitt (a) "Kern-Gotcha" vorgeschrieben) ──────────────────────
// stage_objects.js <-> bridge/bridge.js (bridge-Objekt entsteht erst beim
// WebChannel-Connect) und stage_objects.js <-> interaction/tools.js
// (updateOutlines rundet Selektions-UI ab, die wiederum Stage-Objekte kennt)
// sind gegenseitig abhaengig. Statt echtem zirkulaeren Modul-Import (der bei
// ES-Modulen mit Top-Level-Werten Probleme macht, weil einer der beiden zum
// Import-Zeitpunkt noch nicht fertig ausgewertet ist) registriert app.js
// beim Bootstrap schmale Getter-Referenzen. Das entspricht dem im Original
// impliziten "alle Funktionen sehen sich gegenseitig im selben Scope"-
// Verhalten 1:1, nur explizit gemacht. _dockHighlightId selbst lebt in
// interaction/docking.js (dort auch gelesen/geschrieben ausserhalb dieses
// Moduls) - hier nur ueber den Getter/Setter erreichbar.
export const bridgeRef = { get: () => null };
export const updateOutlinesRef = { get: () => () => {} };
export const dockHighlightRef = { get: () => null, set: () => {} };

export function wireStageObjectsLateBindings({ getBridge, updateOutlines, dockHighlight }) {
  bridgeRef.get = getBridge;
  updateOutlinesRef.get = () => updateOutlines;
  dockHighlightRef.get = dockHighlight.get;
  dockHighlightRef.set = dockHighlight.set;
}
