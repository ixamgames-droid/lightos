// VIZ-13 Schritt 3a-4: Fixture-Registry + DMX-Apply
// (ehem. stage_scene.html:1013 rebuildFixtureMeshList, 1708-1741 Beam-Helper,
// 1742-2004 addFixture/removeFixture/updateFixture). Reines Verschieben.
import * as THREE from '../three/three.js';
import { scene } from '../scene/renderer.js';
import { disposeObj } from '../scene/grid_floor.js';
import { buildFixtureModel } from './registry.js';
import { buildTopDownIcon, tintTopDownIcon } from './topdown_icons.js';
import { fixtures, topDownIcons, settings, view } from '../state.js';
import { deg2rad } from '../scene/renderer.js';

// fixtureMeshes: Raycast-Cache, kein geteilter Modul-State laut Design-
// Dokument "Kern-Gotcha" (ehem. stage_scene.html:1026).
export const fixtureMeshes = []; // for raycasting

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
    opacity: Math.max(0.02, intensity * settings.beamOpacity),
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
    spot.castShadow = true;
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
  // Clean selection
  const idx = view.selectedFids.indexOf(Number(fid));
  if (idx >= 0) view.selectedFids.splice(idx, 1);
  rebuildFixtureMeshList();
  updateOutlinesRef.get()();
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

  // ── Spider: zwei parallele Bars, je 4 EINZELFARBEN-LEDs ────────────────────
  // Jede LED leuchtet einzeln nach ihrem eigenen Kanal (cr/cg/cb/cw der Bar);
  // Master-Dimmer (intensity) ist gemeinsam. Tilt je Bar -> Scheren-Look.
  if (f.isSpider && f.bars) {
    const hs = f.lastHeads || [];
    for (let i = 0; i < f.bars.length; i++) {
      const bar = f.bars[i];
      const h = hs[i] || hs[0] || {};
      const chan = [h.cr || 0, h.cg || 0, h.cb || 0, h.cw || 0];  // [r,g,b,w]-Kanalwerte
      // Tilt ueber den physischen Bereich des Geraets (wie der Moving-Head-Pfad),
      // statt fix 128/±90°; Default 180 ergibt PI/2 wie zuvor.
      const tHalf = (f.tiltRange || 180) * Math.PI / 360;
      const tZero = (f.tiltZero == null) ? 128 : f.tiltZero;
      const tRad = (((h.tilt == null ? tZero : h.tilt) - tZero) / 128) * tHalf;
      bar.pivot.rotation.x = tRad;
      for (let k = 0; k < bar.lenses.length; k++) {
        const lens = bar.lenses[k];
        const ledVal = (chan[lens.userData.ch] || 0) / 255;   // dieser LED-Kanal
        const bright = ledVal * intNorm;                       // * Master-Dimmer
        if (lens.material) {
          lens.material.emissive = lens.userData.ledColor;
          lens.material.emissiveIntensity = bright * 1.9;
        }
        const bm = bar.beams[k];
        if (bm) {
          bm.material.color = lens.userData.ledColor;
          bm.material.opacity = Math.max(0.0, bright * settings.beamOpacity);
          bm.visible = settings.showCones && bright > 0.01 && view.mode === '3D';
        }
      }
    }
    // Top-Down-Icon: beide Bars einzeln faerben (cells; 3c-1 zentrales Tinting)
    tintTopDownIcon(f.icon, { r, g, b }, intNorm, f.lastHeads);
    if (f.icon) f.icon.position.set(f.group.position.x, 0.05, f.group.position.z);
    return;   // Spider fertig — generische Single-Head-Logik ueberspringen
  }

  // ── FM-3: PAR-Bar — N einzeln gefaerbte PARs, gemeinsamer Master-Dimmer ─────
  // Jeder PAR = ein Kopf (heads[i].r/g/b = Summenfarbe inkl. Weiss). Fallback:
  // Kopf 0 = Basis-Farbe, weitere ohne Head-Daten aus.
  if (f.isParBar && f.parHeads) {
    const hs = f.lastHeads || [];
    for (let i = 0; i < f.parHeads.length; i++) {
      const ph = f.parHeads[i];
      const h = hs[i] || {};
      const hr = (h.r != null) ? h.r : (i === 0 ? r : 0);
      const hg = (h.g != null) ? h.g : (i === 0 ? g : 0);
      const hb = (h.b != null) ? h.b : (i === 0 ? b : 0);
      const col = new THREE.Color(hr / 255, hg / 255, hb / 255);
      const bright = intNorm;   // gemeinsamer Master-Dimmer
      if (ph.lens && ph.lens.material) {
        ph.lens.material.color = col;
        ph.lens.material.emissive = col;
        ph.lens.material.emissiveIntensity = bright * 1.9;
      }
      if (ph.beam && ph.beam.material) {
        ph.beam.material.color = col;
        ph.beam.material.opacity = Math.max(0.0, bright * settings.beamOpacity);
        ph.beam.visible = settings.showCones && bright > 0.01 && view.mode === '3D';
      }
    }
    // Top-Down-Icon: N PAR-Zellen einzeln faerben (3c-1 zentrales Tinting)
    tintTopDownIcon(f.icon, { r, g, b }, intNorm, f.lastHeads);
    if (f.icon) f.icon.position.set(f.group.position.x, 0.05, f.group.position.z);
    return;   // PAR-Bar fertig
  }

  // ── FM-4: Mover-Bar — N Mini-Moving-Heads, jeder Kopf einzeln pan/tilt/farbe ─
  if (f.isMoverBar && f.moverHeads) {
    const hs = f.lastHeads || [];
    const panHalf = (f.panRange || 360) * Math.PI / 360;
    const tiltHalf = (f.tiltRange || 180) * Math.PI / 360;
    const pZero = (f.panZero == null) ? 128 : f.panZero;
    const tZero = (f.tiltZero == null) ? 128 : f.tiltZero;
    for (let i = 0; i < f.moverHeads.length; i++) {
      const mh = f.moverHeads[i];
      const h = hs[i] || {};
      const hr = (h.r != null) ? h.r : (i === 0 ? r : 0);
      const hg = (h.g != null) ? h.g : (i === 0 ? g : 0);
      const hb = (h.b != null) ? h.b : (i === 0 ? b : 0);
      const col = new THREE.Color(hr / 255, hg / 255, hb / 255);
      const bright = intNorm;
      const hp = (h.pan == null) ? pan : h.pan;    // pro-Kopf-Pan (FM-2)
      const ht = (h.tilt == null) ? tilt : h.tilt; // pro-Kopf-Tilt
      mh.yoke.rotation.y = ((hp - pZero) / 128) * panHalf;
      mh.head.rotation.x = ((ht - tZero) / 128) * tiltHalf;
      if (mh.lens && mh.lens.material) {
        mh.lens.material.color = col;
        mh.lens.material.emissive = col;
        mh.lens.material.emissiveIntensity = bright * 1.9;
      }
      if (mh.beam && mh.beam.material) {
        mh.beam.material.color = col;
        mh.beam.material.opacity = Math.max(0.0, bright * settings.beamOpacity);
        mh.beam.visible = settings.showCones && bright > 0.01 && view.mode === '3D';
      }
    }
    // Top-Down-Icon: N Kopf-Zellen einzeln faerben (3c-1 zentrales Tinting)
    tintTopDownIcon(f.icon, { r, g, b }, intNorm, f.lastHeads);
    if (f.icon) f.icon.position.set(f.group.position.x, 0.05, f.group.position.z);
    return;   // Mover-Bar fertig
  }

  // Generischer Single-Head-Pfad (par, led_bar, dimmer, strobe, laser, smoke,
  // hazer, moving_head, scanner, Fallback). Reihenfolge-Vertrag: Farbe ->
  // Pan/Tilt -> Floor-Aiming -> Icon-Position (applyFloorAim liest die in
  // applyPanTilt gesetzte Kopf-Rotation ueber getWorldQuaternion).
  applyGenericColor(f, dmx);
  applyPanTilt(f, dmx);
  applyFloorAim(f, dmx);
  syncIconPos(f);
}

// ── updateDmx-Helfer (VIZ-13 3c Teil 2) ─────────────────────────────────────
// 1:1 aus dem ehemaligen generischen Schlussteil von updateFixture extrahiert
// (reiner Refactor, keine Verhaltensaenderung).

// Beam/Spot/FloorSpot/Linse/Lampe/Laser-Faecher + Icon-Tint. Alle Zweige sind
// guard-basiert (nur vorhandene Refs werden angefasst) — dadurch bedient EIN
// Helfer alle Single-Head-Typen identisch zum alten Durchlauf.
function applyGenericColor(f, dmx) {
  const { color, intNorm } = dmx;
  if (f.beam) {
    f.beam.material.color = color;
    f.beam.material.opacity = Math.max(0.0, intNorm * settings.beamOpacity);
    f.beam.visible = settings.showCones && intNorm > 0.01 && view.mode === '3D';
  }
  if (f.spot) {
    f.spot.color = color;
    f.spot.intensity = intNorm * 3.0;
  }
  if (f.floorSpot) {
    f.floorSpot.material.color = color;
    f.floorSpot.material.opacity = Math.max(0.0, intNorm * 0.55);
    f.floorSpot.visible = settings.showFloorSpots && intNorm > 0.01;
  }
  if (f.lens && f.lens.material) {
    f.lens.material.emissive = color;
    f.lens.material.emissiveIntensity = intNorm * 1.5;
  }
  if (f.lamp && f.lamp.material) {
    f.lamp.material.emissive = color;
    f.lamp.material.emissiveIntensity = intNorm * 1.5;
  }
  // Laser-Faecher: jede Linie folgt DMX-Farbe + Intensitaet (statt fix gruen/an)
  if (f.laserBeams) {
    const laserVis = settings.showCones && intNorm > 0.01 && view.mode === '3D';
    for (const bm of f.laserBeams) {
      if (!bm.material) continue;
      bm.material.color = color;
      bm.material.opacity = Math.max(0.0, intNorm * 0.6);
      bm.visible = laserVis;
    }
  }
  // Top-down icon color reflects active output color (only when bright)
  tintTopDownIcon(f.icon, color, intNorm);
}

// Pan/Tilt (Moving Head UND Scanner — FM-1: Scanner-Spiegel bewegt sich jetzt).
// Der Typ-Guard bleibt bewusst 1:1 erhalten (Byte-Identitaet): fuer alle
// anderen Typen ist der Aufruf ein No-Op wie im Monolith.
function applyPanTilt(f, dmx) {
  if ((f.type === 'moving_head' || f.type === 'scanner') && f.yoke && f.head) {
    const { pan, tilt } = dmx;
    // Pan/Tilt-DMX -> Winkel ueber den physischen Bereich des Geraets (halber
    // Bereich in Radiant = bereich*PI/360); Default 360/180 = generisch wie zuvor.
    const panHalf = (f.panRange || 360) * Math.PI / 360;
    const tiltHalf = (f.tiltRange || 180) * Math.PI / 360;
    const pZero = (f.panZero == null) ? 128 : f.panZero;
    const tZero = (f.tiltZero == null) ? 128 : f.tiltZero;
    const panRad = ((pan - pZero) / 128) * panHalf;
    const tiltRad = ((tilt - tZero) / 128) * tiltHalf;
    f.yoke.rotation.y = panRad;
    f.head.rotation.x = tiltRad;
    // Reflect pan in top-down icon (rotate the whole icon)
    f._lastPanRad = panRad;   // fuer konsistente Icon-Yaw in den Rotate-Pfaden
    if (f.icon) f.icon.rotation.y = panRad + f.group.rotation.y;
  }
}

// Floor spot follow direction
function applyFloorAim(f, dmx) {
  if (!dmx.skipBeam && f.floorSpot && f.spotTarget) {
    const dir = new THREE.Vector3(0, -1, 0);
    // Floor-Spot folgt der Strahlrichtung fuer ALLE Beam-Fixtures: Moving Head
    // ueber den Kopf (Pan/Tilt), statische ueber die Gruppen-Rotation (rotX/rotZ).
    // Vorher blieb der Boden-Pool bei getilteten PARs/Scannern senkrecht drunter.
    const aimObj = ((f.type === 'moving_head' || f.type === 'scanner') && f.head) ? f.head : f.group;
    if (aimObj) {
      aimObj.updateMatrixWorld();
      const wq = new THREE.Quaternion();
      aimObj.getWorldQuaternion(wq);
      dir.applyQuaternion(wq);
    }
    const origin = new THREE.Vector3();
    f.group.getWorldPosition(origin);
    if (Math.abs(dir.y) > 0.001) {
      const t = -origin.y / dir.y;
      if (t > 0 && t < 100) {
        const hitX = origin.x + dir.x * t;
        const hitZ = origin.z + dir.z * t;
        f.floorSpot.position.set(hitX, 0.01, hitZ);
        f.spotTarget.position.set(hitX, 0.0, hitZ);
      }
    }
  }
}

// Keep top-down icon position synced
function syncIconPos(f) {
  if (f.icon) {
    f.icon.position.set(f.group.position.x, 0.05, f.group.position.z);
  }
}

// ── Spaet-Bindung (zirkulaere Abhaengigkeit: removeFixture() ruft im
// Original updateOutlines() auf, das aber selbst Fixtures/Selektion kennt
// und in interaction/tools.js liegt, welches wiederum fixtures.js fuer
// Fixture-Operationen braucht - siehe Design-Dokument "Kern-Gotcha") ────────
export const updateOutlinesRef = { get: () => () => {} };
export function wireFixturesLateBindings({ updateOutlines }) {
  updateOutlinesRef.get = () => updateOutlines;
}
