// VIZ-13 Schritt 3a-4: Fixture-Registry + DMX-Apply
// (ehem. stage_scene.html:1013 rebuildFixtureMeshList, 1708-1741 Beam-Helper,
// 1742-2004 addFixture/removeFixture/updateFixture). Reines Verschieben.
// VIZ-13 3c Teil 2: updateFixture ist seither nur noch die dmxBatch-Fassade
// (Signatur unveraendert, siehe bridge.js + test_viz12_bridge_batch.py) und
// dispatcht per registry.js#updateFixtureDmx auf die pro-Typ-Handler in
// builders.js — belegt durch tests/test_viz13c_updatedmx_registry.py.
import * as THREE from '../three/three.js';
import { scene, renderer } from '../scene/renderer.js';
import { disposeObj } from '../scene/grid_floor.js';
// VIZ-13 3c Teil 2: build UND DMX-Update dispatchen ueber die FixtureType-
// Registry; die pro-Typ-Handler leben bei ihren Buildern (builders.js), wo
// auch tintTopDownIcon konsumiert wird — nicht mehr hier.
import { buildFixtureModel, updateFixtureDmx } from './registry.js';
import { buildTopDownIcon } from './topdown_icons.js';
import { fixtures, topDownIcons, settings, view } from '../state.js';
import { deg2rad } from '../scene/renderer.js';
// VIZ-13 3c-2: On-Demand-Rendering — jede DMX-/Bestands-Aenderung an
// Fixtures muss einen Frame anfordern (render_loop.js ist import-frei,
// kein Zyklus-Risiko).
import { requestRender } from '../scene/render_loop.js';

// fixtureMeshes: Raycast-Cache, kein geteilter Modul-State laut Design-
// Dokument "Kern-Gotcha" (ehem. stage_scene.html:1026).
export const fixtureMeshes = []; // for raycasting

// ── Shadow-Budget ────────────────────────────────────────────────────────────
// Jede schattenwerfende SpotLight belegt im Fragment-Shader JEDES beleuchteten
// Materials eine Texture-Unit (Shadow-Map). GPUs wie die Adreno in Davids
// Surface haben nur MAX_TEXTURE_IMAGE_UNITS=16 — bei grossen Rigs (48 Fixtures
// im Demo-Rig) kompilierte deshalb KEIN Lit-Shader mehr ("FRAGMENT shader
// texture image units count exceeds MAX_TEXTURE_IMAGE_UNITS(16)") und die
// gesamte Buehne blieb unsichtbar (nur MeshBasic-Beams zeichneten noch).
// Daher: nur die ersten N Spots werfen Schatten, der Rest leuchtet ohne.
// Reserve deckt Material-/Sonstige-Texturen (Boden-Canvas, Label-Sprites) ab.
const SHADOW_TEXTURE_RESERVE = 6;
let _shadowSpotBudget = null;

function shadowSpotBudget() {
  if (_shadowSpotBudget === null) {
    const maxTex = (renderer && renderer.capabilities
      && renderer.capabilities.maxTextures) || 16;
    _shadowSpotBudget = Math.max(2, maxTex - SHADOW_TEXTURE_RESERVE);
  }
  return _shadowSpotBudget;
}

// Idempotent: verteilt das Budget deterministisch (fid-Reihenfolge) auf alle
// vorhandenen Spots. three.js r128 erkennt den castShadow-Wechsel ueber die
// lightsStateVersion selbst und kompiliert betroffene Programme neu.
export function syncSpotShadowBudget() {
  const budget = shadowSpotBudget();
  let used = 0;
  let changed = false;
  for (const fid in fixtures) {
    const spot = fixtures[fid] && fixtures[fid].spot;
    if (!spot) continue;
    const want = used < budget;
    if (want) used += 1;
    if (spot.castShadow !== want) { spot.castShadow = want; changed = true; }
  }
  if (changed) requestRender();
}

export function rebuildFixtureMeshList() {
  fixtureMeshes.length = 0;
  for (const fid in fixtures) {
    const f = fixtures[fid];
    f.group.traverse(o => {
      if (o.isMesh) {
        o.userData.fid = Number(fid);
        fixtureMeshes.push(o);
      }
    });
  }
}

// ── Beam helpers ─────────────────────────────────────────────────────────────
export function createBeamCone(color, intensity, angle, length) {
  const radius = Math.tan(angle) * length;
  const geo = new THREE.ConeGeometry(radius, length, 24, 1, true);
  const mat = new THREE.MeshBasicMaterial({
    color: color,
    transparent: true,
    // Ein Fixture mit Dimmer = 0 darf auch beim allerersten Build keinen
    // Restkegel hinterlassen. Bei großen Rigs überlagerten sich die zuvor
    // erzwungenen 2 % zu einem scheinbaren Flackern, bis der erste DMX-Batch
    // die Materialien nachträglich korrigierte.
    opacity: Math.max(0.0, intensity * settings.beamOpacity),
    side: THREE.DoubleSide,
    depthWrite: false,
    blending: THREE.AdditiveBlending,
  });
  const cone = new THREE.Mesh(geo, mat);
  cone.position.y = -length / 2;
  cone.visible = settings.showCones;
  // Aus Fit/Fit-Auswahl-Bounds ausschliessen: der Kegel ist bis zu 8 m lang und
  // wuerde die Bounding-Box sonst dominieren -> Fit zoomt viel zu weit raus
  // (camera/presets.js#_boundsFromMeshes ueberspringt Meshes mit diesem Flag).
  cone.userData.excludeFromFit = true;
  return cone;
}

export function createFloorSpot(color, intensity, radius) {
  const geo = new THREE.CircleGeometry(radius, 32);
  const mat = new THREE.MeshBasicMaterial({
    color: color,
    transparent: true,
    opacity: Math.max(0.0, intensity * 0.55),
    side: THREE.DoubleSide,
    depthWrite: false,
    blending: THREE.AdditiveBlending,
  });
  const disc = new THREE.Mesh(geo, mat);
  disc.rotation.x = -Math.PI / 2;
  disc.position.y = 0.01;
  disc.visible = settings.showFloorSpots;
  return disc;
}

export function addFixture(data) {
  const fid = data.fid;
  if (fixtures[fid]) removeFixture(fid);
  // 'model' ist das Render-Modell (von Python bestimmt, z.B. 'spider' fuer
  // Doppel-Bar-Geraete); faellt auf den fixture_type zurueck.
  const rtype = data.model || data.type || 'par';
  // FM-8: echte PIXEL-Bars (fixture_type 'led_bar' mit vielen Farb-Banks) als
  // schlanke Bar mit N Einzelsegmenten rendern statt als N PAR-Dosen. Schwelle
  // >=6: 4er-Bars ("vier einzelne PAR-Lichter", PARBAR4/Dotz TPar) behalten
  // bewusst den PAR-Dosen-Look; 6/8/12+-Segment-Bars sind Pixel-Bars.
  const pixelBar = data.type === 'led_bar' && (data.nHeads || 0) >= 6;
  const model = buildFixtureModel(rtype, { mirror: data.mirror, nHeads: data.nHeads, pixelBar });
  const root = new THREE.Group();
  root.position.set(data.x || 0, data.y == null ? 6.5 : data.y, data.z || 0);
  // Multi-Achsen-Ausrichtung (Grad aus Python) gleich beim Erzeugen setzen.
  root.rotation.set(deg2rad(data.rotX), deg2rad(data.rotY), deg2rad(data.rotZ));
  root.add(model.group);

  const color = new THREE.Color((data.r||0)/255, (data.g||0)/255, (data.b||0)/255);
  const intensity = (data.intensity||0) / 255;

  let beam = null, spot = null, spotTarget = null, floorSpot = null;

  if (model.isSpider) {
    // Spider: pro Bar 4 schmale Beams in der FIXFARBE der jeweiligen LED, die
    // dem Tilt der Bar folgen. Kein Yoke/Pan, kein zentraler Spotlight/Floor-
    // Spot — jede LED strahlt einzeln (Scheren-Look ueber die zwei Bars).
    const beamLength = 6.5;
    const beamAngle = Math.PI / 20;
    model.bars.forEach(bar => {
      bar.beams = [];
      bar.lenses.forEach(lens => {
        const host = new THREE.Group();
        host.position.copy(lens.position);
        const bcone = createBeamCone(lens.userData.ledColor.clone(), 0, beamAngle, beamLength);
        host.add(bcone);
        bar.pivot.add(host);
        bar.beams.push(bcone);
      });
    });
  } else if (model.isParBar) {
    // FM-3: PAR-Bar — pro PAR ein nach unten gerichteter Beam in der PAR-Farbe.
    // Kein zentraler Spot/Floor-Spot; jeder PAR strahlt einzeln (wie beim Spider).
    const beamAngle = Math.PI / 12;
    model.parHeads.forEach(ph => {
      const host = new THREE.Group();
      host.position.copy(ph.lens.position);
      const bcone = createBeamCone(new THREE.Color(0, 0, 0), 0, beamAngle, 7.0);
      host.add(bcone);
      model.group.add(host);
      ph.beam = bcone;
    });
  } else if (model.isMoverBar) {
    // FM-4: Mover-Bar — pro Kopf ein Beam am Tilt-Pivot (pant/kippt mit dem Kopf).
    const beamAngle = Math.PI / 13;
    model.moverHeads.forEach(mh => {
      const host = new THREE.Group();
      host.position.set(0, -0.11, 0);   // an der Linse im Kopf-Frame
      mh.head.add(host);
      const bcone = createBeamCone(new THREE.Color(0, 0, 0), 0, beamAngle, 7.5);
      host.add(bcone);
      mh.beam = bcone;
    });
  } else if (rtype === 'smoke' || rtype === 'hazer') {
    // Nebel/Hazer sind KEINE Licht-Fixtures -> kein Beam/SpotLight/Floor-Spot
    // (nur der emissive Indikator-Lamp aus dem build); vorher bekamen sie
    // faelschlich einen Lichtkegel + schattenwerfenden SpotLight.
  } else {
    const headHost = model.head || model.group;
    const beamLength = rtype === 'led_bar' ? 6.0 : 8.0;
    const beamAngle = rtype === 'led_bar' ? Math.PI/14 : Math.PI/10;
    beam = createBeamCone(color, intensity, beamAngle, beamLength);
    headHost.add(beam);

    spot = new THREE.SpotLight(color, intensity * 3.0, 25, beamAngle * 1.2, 0.6, 1.0);
    // castShadow vergibt syncSpotShadowBudget() nach der Registrierung —
    // ein hartes `true` je Fixture sprengt auf 16-Unit-GPUs das Shader-Limit.
    spot.castShadow = false;
    spot.shadow.mapSize.width = 512;
    spot.shadow.mapSize.height = 512;
    root.add(spot);

    spotTarget = new THREE.Object3D();
    spotTarget.position.set(0, -root.position.y, 0);
    scene.add(spotTarget);
    spot.target = spotTarget;

    floorSpot = createFloorSpot(color, intensity, 1.2);
    scene.add(floorSpot);
  }

  scene.add(root);

  // 2D top-down icon (3c-1: nHeads fuer die Einzel-Zellen der Bar-Icons)
  const icon = buildTopDownIcon(rtype, data.nHeads);
  icon.position.set(root.position.x, 0.05, root.position.z);
  // Yaw uebernehmen: laengliche Icons (Bars/Spider) lagen sonst nach dem
  // Show-Reload quer, bis die erste Rotations-Geste sie synct (die Update-
  // Pfade in bridge.js/pointer.js/touch.js laufen nur bei Transform-Edits).
  icon.rotation.y = root.rotation.y;
  icon.userData.fid = Number(fid);
  // Force pickable: tag children
  icon.traverse(o => { if (o.isMesh) o.userData.fid = Number(fid); });
  icon.visible = (view.mode === '2D');
  scene.add(icon);
  topDownIcons[fid] = icon;

  // Hide 3D model in 2D mode
  root.visible = (view.mode === '3D');

  fixtures[fid] = {
    group: root,
    yoke: model.yoke || null,
    head: model.head || null,
    lens: model.lens || null,
    lamp: model.lamp || null,
    laserBeams: model.laserBeams || null,
    bars: model.bars || null,
    isSpider: !!model.isSpider,
    parHeads: model.parHeads || null,   // FM-3: PAR-Bar-Koepfe (je {lens, beam})
    isParBar: !!model.isParBar,
    moverHeads: model.moverHeads || null,   // FM-4: Mover-Bar-Koepfe (je {yoke, head, lens, beam})
    isMoverBar: !!model.isMoverBar,
    beam, spot, spotTarget, floorSpot,
    icon,
    type: rtype,
    dockedTo: data.dockedTo || null,
    // Pan/Tilt physischer Bereich (Grad) + Nullpunkt -> Beam-Abbildung = Hardware.
    panRange: (data.panRange != null) ? data.panRange : 360,
    tiltRange: (data.tiltRange != null) ? data.tiltRange : 180,
    panZero: (data.panZero != null) ? data.panZero : 128,
    tiltZero: (data.tiltZero != null) ? data.tiltZero : 128,
    data: { ...data },
  };

  syncSpotShadowBudget();
  rebuildFixtureMeshList();
  updateFixture(fid, data.r||0, data.g||0, data.b||0, data.intensity||0, data.pan||128, data.tilt||128, data.heads||null);
}

export function removeFixture(fid) {
  const f = fixtures[fid];
  if (!f) return;
  scene.remove(f.group);
  if (f.spotTarget) scene.remove(f.spotTarget);
  if (f.floorSpot) { scene.remove(f.floorSpot); disposeObj(f.floorSpot); }
  if (f.icon) { scene.remove(f.icon); f.icon.traverse(disposeObj); }
  f.group.traverse(disposeObj);
  delete fixtures[fid];
  delete topDownIcons[fid];
  // Frei gewordenes Shadow-Budget an verbleibende Spots weiterreichen.
  syncSpotShadowBudget();
  // Clean selection
  const idx = view.selectedFids.indexOf(Number(fid));
  if (idx >= 0) view.selectedFids.splice(idx, 1);
  rebuildFixtureMeshList();
  updateOutlinesRef.get()();
  requestRender();  // 3c-2: Objekt aus der Szene entfernt
}

export function updateFixture(fid, r, g, b, intensity, pan, tilt, heads) {
  const f = fixtures[fid];
  if (!f) return;
  const color = new THREE.Color(r/255, g/255, b/255);
  const intNorm = intensity / 255;
  const skipBeam = (view.mode === '2D' && Object.keys(fixtures).length > 50);
  // VIZ-13 3c Teil 2: gebuendelter DMX-Kontext fuer die updateDmx-Handler —
  // traegt den byte-identischen dmxBatch-Vertrag (r,g,b,intensity,pan,tilt,
  // heads) plus die abgeleiteten Werte, damit kein Handler sie neu rechnet.
  // WICHTIG: `color` ist EINE geteilte THREE.Color-Instanz pro Update-Aufruf;
  // die Handler WEISEN sie den Materialien ZU (kein .copy()) — exakt die
  // Instanz-Sharing-Semantik des Monolithen.
  const dmx = { r, g, b, intensity, pan, tilt, heads, color, intNorm, skipBeam };

  if (heads) f.lastHeads = heads;

  // Dispatch ueber die FixtureType-Registry (Design (e)) — ersetzt die alte
  // if-Kette (Spider/ParBar/MoverBar -> Rest) verhaltens-identisch:
  // f.type ist das Render-Modell aus addFixture (data.model || data.type),
  // die Multihead-Handler tragen die alten Flag-Guards selbst (Durchfall auf
  // den generischen Pfad), unbekannte Typen fallen wie beim build auf den
  // PAR-Eintrag zurueck. Belegt durch tests/test_viz13c_updatedmx_registry.py
  // (Golden-Parity gegen den eingefrorenen Monolith-Zustand).
  updateFixtureDmx(f, dmx);
  // 3c-2 Dirty-Quelle 1 (dmxBatch): der Batch-Handler in bridge.js ruft pro
  // Element dieses updateFixture — der Aufruf HIER deckt damit den ganzen
  // Batch UND den addFixture-Initialaufruf ab (reiner Flag-Setter, N-fach
  // billig; rAF coalesced auf einen Frame).
  requestRender();
}

// ── Spaet-Bindung (zirkulaere Abhaengigkeit: removeFixture() ruft im
// Original updateOutlines() auf, das aber selbst Fixtures/Selektion kennt
// und in interaction/tools.js liegt, welches wiederum fixtures.js fuer
// Fixture-Operationen braucht - siehe Design-Dokument "Kern-Gotcha") ────────
export const updateOutlinesRef = { get: () => () => {} };
export function wireFixturesLateBindings({ updateOutlines }) {
  updateOutlinesRef.get = () => updateOutlines;
}
