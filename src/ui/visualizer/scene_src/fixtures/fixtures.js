// VIZ-13 Schritt 3a-4: Fixture-Registry + DMX-Apply
// (ehem. stage_scene.html:1013 rebuildFixtureMeshList, 1708-1741 Beam-Helper,
// 1742-2004 addFixture/removeFixture/updateFixture). Reines Verschieben.
import * as THREE from '../three/three.js';
import { scene } from '../scene/renderer.js';
import { disposeObj } from '../scene/grid_floor.js';
import { buildFixtureModel } from './registry.js';
import { buildTopDownIcon } from './topdown_icons.js';
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
  const model = buildFixtureModel(rtype, { mirror: data.mirror });
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

  // 2D top-down icon
  const icon = buildTopDownIcon(rtype);
  icon.position.set(root.position.x, 0.05, root.position.z);
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
    // Top-Down-Icon: Farbe der linken Bar (Kopf 0) spiegeln
    if (f.icon && f.icon.userData.body && f.icon.userData.body.material) {
      const h0 = (f.lastHeads && f.lastHeads[0]) || { r, g, b };
      if (intNorm > 0.05) {
        f.icon.userData.body.material.color.setRGB((h0.r||0)/255, (h0.g||0)/255, (h0.b||0)/255);
        f.icon.userData.body.material.opacity = Math.min(1.0, 0.5 + intNorm * 0.5);
      } else {
        f.icon.userData.body.material.color.setHex(0x3a3a4a);
        f.icon.userData.body.material.opacity = 0.85;
      }
    }
    if (f.icon) f.icon.position.set(f.group.position.x, 0.05, f.group.position.z);
    return;   // Spider fertig — generische Single-Head-Logik ueberspringen
  }

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
  if (f.icon && f.icon.userData.body && f.icon.userData.body.material) {
    if (intNorm > 0.05) {
      f.icon.userData.body.material.color.copy(color);
      f.icon.userData.body.material.opacity = Math.min(1.0, 0.5 + intNorm * 0.5);
    } else {
      f.icon.userData.body.material.color.setHex(0x3a3a4a);
      f.icon.userData.body.material.opacity = 0.85;
    }
  }

  // Pan/Tilt (Moving Head UND Scanner — FM-1: Scanner-Spiegel bewegt sich jetzt)
  if ((f.type === 'moving_head' || f.type === 'scanner') && f.yoke && f.head) {
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

  // Floor spot follow direction
  if (!skipBeam && f.floorSpot && f.spotTarget) {
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
  // Keep top-down icon position synced
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
