// VIZ-13 Schritt 3a-4: Einzel-Builder pro Fixture-Typ
// (ehem. stage_scene.html:1042-1500). Reines Verschieben.
// VIZ-13 3c Teil 2: zusaetzlich die pro-Typ-updateDmx-Handler (Split des
// ehemaligen updateFixture-Monolithen) — build + updateDmx desselben Typs
// leben bewusst beisammen; registry.js bleibt die deklarative Map.
import * as THREE from '../three/three.js';
import { loadModel, fitModelToSize } from '../scene/model_loader.js';
import { settings, view } from '../state.js';
import { tintTopDownIcon } from './topdown_icons.js';
import { isLowSpec } from '../scene/renderer.js';

// LowRes-Anschluss (VIZ-15/VIZ-LOWSPEC): Auf Low-Tier-GPUs halbieren die
// Gehaeuse-Rundkoerper ihre Radial-Segmente (Boden 6) — analog zum Beam-Kegel
// in fixtures.js (12 statt 24 Segmente). High-Tier behaelt die vollen Werte.
function segs(n) {
  return isLowSpec ? Math.max(6, Math.round(n / 2)) : n;
}

// ── Builders ─────────────────────────────────────────────────────────────────
export function buildMovingHead() {
  // FM-8: detailliertes PROZEDURALES Moving-Head-Modell (statt des groben
  // moving_head.dae = flache Platte + Knubbel). Erkennbare Silhouette: runde
  // Bodenplatte + Hals -> U-Yoke mit Motor-/Lager-Gehaeusen (pant um Y) -> Kopf-
  // Trommel mit Zier-Ringen + Linsen-Ring + emissiver Linse (kippt um X). Ausgang
  // ist -Y (deckt sich mit dem Beam aus createBeamCone) -> Linse an der Unterseite.
  // Pivots/Return-Vertrag unveraendert (yoke pant um Y, head kippt um X, lens =
  // Farb-Feedback via updateFixture, addFixture haengt den Beam an model.head).
  // Reale Referenz (FM-Runde 2): Mittelklasse-LED-Spot wie Chauvet Intimidator
  // Spot 260 — 232 x 351 x 163 mm. Das Modell nutzt eine leicht groessere
  // Generik (Basis Ø ~0,30 m, Gesamthoehe ~0,47 m), weil die Builtins MH8/16
  // auch fuer groessere Heads stehen; vorher war die Basis Ø 0,60 m (Fantasie).
  const group = new THREE.Group();
  const darkMetal = new THREE.MeshStandardMaterial({ color: 0x191920, metalness: 0.8, roughness: 0.35 });
  const midMetal  = new THREE.MeshStandardMaterial({ color: 0x26262e, metalness: 0.7, roughness: 0.30 });
  const trim      = new THREE.MeshStandardMaterial({ color: 0x3a3a46, metalness: 0.6, roughness: 0.40 });

  // ── Basis: Bodenplatte + kegeliger Hals ──
  const baseP = new THREE.Mesh(new THREE.CylinderGeometry(0.15, 0.16, 0.045, segs(28)), darkMetal);
  baseP.position.y = 0.022; baseP.castShadow = true; group.add(baseP);
  const neck = new THREE.Mesh(new THREE.CylinderGeometry(0.105, 0.145, 0.065, segs(28)), midMetal);
  neck.position.y = 0.075; group.add(neck);

  // ── Yoke (pant um Y) ──
  const yoke = new THREE.Group();
  yoke.position.y = 0.11;
  group.add(yoke);
  const turn = new THREE.Mesh(new THREE.CylinderGeometry(0.095, 0.095, 0.032, segs(28)), trim);
  turn.position.y = 0.006; yoke.add(turn);
  [-0.12, 0.12].forEach(x => {
    const arm = new THREE.Mesh(new THREE.BoxGeometry(0.04, 0.245, 0.075), midMetal);   // U-Arm
    arm.position.set(x, 0.155, 0); arm.castShadow = true; yoke.add(arm);
    const motor = new THREE.Mesh(new THREE.CylinderGeometry(0.046, 0.046, 0.052, segs(22)), darkMetal);
    motor.rotation.z = Math.PI / 2; motor.position.set(x * 0.82, 0.265, 0); yoke.add(motor);
  });

  // ── Kopf (kippt um X), Lichtausgang -Y ──
  const head = new THREE.Group();
  head.position.y = 0.265;
  yoke.add(head);
  const headBody = new THREE.Mesh(new THREE.CylinderGeometry(0.088, 0.100, 0.20, segs(28)), midMetal);
  headBody.name = 'mh-head-body';
  headBody.castShadow = true; head.add(headBody);
  [0.052, -0.017].forEach(y => {                   // zwei Zier-Ringe (Rillen)
    const ring = new THREE.Mesh(new THREE.CylinderGeometry(0.103, 0.103, 0.011, segs(28)), trim);
    ring.position.y = y; head.add(ring);
  });
  const lensRing = new THREE.Mesh(new THREE.CylinderGeometry(0.096, 0.087, 0.03, segs(28)), darkMetal);
  lensRing.position.y = -0.10; head.add(lensRing);
  const lens = new THREE.Mesh(                      // emissive Linse (Farb-Feedback)
    new THREE.CylinderGeometry(0.077, 0.077, 0.012, segs(28)),
    new THREE.MeshStandardMaterial({ color: 0x606060, emissive: 0x000000, metalness: 0.3, roughness: 0.2 })
  );
  lens.position.y = -0.115; head.add(lens);

  return { group, yoke, head, lens };
}

export function buildPar() {
  // Reale Referenz (FM-Runde 2): PAR-64-Dose, z.B. Eurolite LED PAR-64 short
  // (280 x 265 x 320 mm inkl. Buegel, Tubus Ø ~0,23 m) — vorher Ø 0,44 m.
  const group = new THREE.Group();
  const bodyMat = new THREE.MeshStandardMaterial({ color: 0x222222, metalness: 0.5, roughness: 0.5 });
  const body = new THREE.Mesh(
    new THREE.CylinderGeometry(0.115, 0.115, 0.30, segs(16)),
    bodyMat
  );
  body.name = 'par-body';
  body.castShadow = true;
  group.add(body);
  const front = new THREE.Mesh(
    new THREE.CylinderGeometry(0.115, 0.115, 0.03, segs(16)),
    new THREE.MeshStandardMaterial({ color: 0xcccccc, metalness: 0.95, roughness: 0.05 })
  );
  front.position.y = -0.165;
  group.add(front);
  // Haengebuegel (Doppelbuegel wie am echten PAR): zwei Arme + Querjoch.
  const bracketParts = [];
  [-0.13, 0.13].forEach(x => {
    const arm = new THREE.Mesh(new THREE.BoxGeometry(0.022, 0.16, 0.05), bodyMat);
    arm.position.set(x, 0.09, 0);
    group.add(arm);
    bracketParts.push(arm);
  });
  const yokeBar = new THREE.Mesh(new THREE.BoxGeometry(0.29, 0.028, 0.05), bodyMat);
  yokeBar.position.y = 0.175;
  group.add(yokeBar);
  bracketParts.push(yokeBar);
  // Try to overlay a real PAR model. If loaded, hide procedural body (incl.
  // Buegel — das .dae bringt seine eigene Silhouette mit), keep lens emissive.
  loadModel('assets/models/fixtures/par.dae', (model) => {
    if (!model) return;
    fitModelToSize(model, { x: 0.26, y: 0.32, z: 0.26 });
    model.traverse(c => { if (c.isMesh) { c.castShadow = true; } });
    body.visible = false;
    bracketParts.forEach(p => { p.visible = false; });
    group.add(model);
  });
  return { group, head: group, lens: front };
}

export function buildLedBar() {
  // Reale Referenz (FM-Runde 2): 1-m-LED-Bar, z.B. Stairville LED Bar 240/8
  // (1070 x 88 x 65 mm) — vorher 1,2 m lang und 0,18 m tief (zu klobig).
  const group = new THREE.Group();
  const body = new THREE.Mesh(
    new THREE.BoxGeometry(1.07, 0.088, 0.065),
    new THREE.MeshStandardMaterial({ color: 0x111111, metalness: 0.4, roughness: 0.5 })
  );
  body.castShadow = true;
  group.add(body);
  // Pixel-LEDs teilen EIN emissives Material; lamp zeigt darauf -> updateFixture
  // faerbt ueber f.lamp.material ALLE Pixel. Das dunkle Gehaeuse (body) bleibt
  // unbeleuchtet (vorher leuchtete faelschlich das Gehaeuse, Pixel blieben grau).
  const pxMat = new THREE.MeshStandardMaterial({
    color: 0x222222, emissive: 0x000000, emissiveIntensity: 0.0, roughness: 0.4,
  });
  let firstPx = null;
  for (let i = 0; i < 8; i++) {
    const px = new THREE.Mesh(new THREE.BoxGeometry(0.115, 0.06, 0.015), pxMat);
    px.position.set(-0.4375 + i * 0.125, 0, 0.037);
    group.add(px);
    if (!firstPx) firstPx = px;
  }
  return { group, head: group, lamp: firstPx };
}

export function buildStrobe() {
  // Reale Referenz (FM-Runde 2): Eurolite Superstrobe 2700 — 460 x 240 x 140 mm
  // (B x T x H). Vorher 0,6 x 0,5 m Grundflaeche (fast doppelt zu tief).
  const group = new THREE.Group();
  const body = new THREE.Mesh(
    new THREE.BoxGeometry(0.46, 0.14, 0.24),
    new THREE.MeshStandardMaterial({ color: 0x111111, metalness: 0.4, roughness: 0.5 })
  );
  body.castShadow = true;
  group.add(body);
  // Breite Blitzroehren-Wanne an der Unterseite (Lichtausgang -Y wie bisher).
  const lamp = new THREE.Mesh(
    new THREE.BoxGeometry(0.38, 0.03, 0.17),
    new THREE.MeshStandardMaterial({ color: 0xeeeeee, roughness: 0.1 })
  );
  lamp.position.y = -0.075;
  group.add(lamp);
  loadModel('assets/models/fixtures/strobe.dae', (model) => {
    if (!model) return;
    fitModelToSize(model, { x: 0.48, y: 0.18, z: 0.26 });
    model.traverse(c => { if (c.isMesh) { c.castShadow = true; } });
    body.visible = false;
    group.add(model);
  });
  return { group, head: group, lamp };
}

export function buildDimmer() {
  // Reale Referenz (FM-Runde 2): 4-Kanal-Truss-Dimmerpack (Botex-/Eurolite-
  // Klasse, ~0,30 x 0,13 x 0,19 m) statt des frueheren 0,44-m-Wuerfels. Ein
  // Dimmerpack hat keine Torblenden — stattdessen Ausgangs-Dosen an der Front.
  const group = new THREE.Group();

  // ── Dark-metal housing ────────────────────────────────────────────────────
  const housingMat = new THREE.MeshStandardMaterial({ color: 0x1a1a1a, metalness: 0.65, roughness: 0.45 });
  const housing = new THREE.Mesh(
    new THREE.BoxGeometry(0.30, 0.13, 0.19),
    housingMat
  );
  housing.position.y = 0.0;
  housing.castShadow = true;
  group.add(housing);

  // ── Mounting-ear flanges (left and right) ─────────────────────────────────
  const earMat = new THREE.MeshStandardMaterial({ color: 0x222222, metalness: 0.55, roughness: 0.5 });
  [-0.17, 0.17].forEach((xOff) => {
    const ear = new THREE.Mesh(
      new THREE.BoxGeometry(0.04, 0.06, 0.12),
      earMat
    );
    ear.position.set(xOff, 0.055, 0);
    ear.castShadow = true;
    group.add(ear);
  });

  // ── Frosted lens panel (becomes the 'lamp' — emissive-driven) ─────────────
  const lampMat = new THREE.MeshStandardMaterial({
    color: 0xfff5e0,
    emissive: new THREE.Color(0xffffff),
    emissiveIntensity: 0,
    roughness: 0.6,
    transparent: true,
    opacity: 0.88,
    side: THREE.DoubleSide,
  });
  const lensPanel = new THREE.Mesh(
    new THREE.PlaneGeometry(0.24, 0.08),
    lampMat
  );
  lensPanel.position.set(0, 0.015, 0.098);
  group.add(lensPanel);

  // ── 4×1 Reihe emissiver Kanal-LEDs (teilen lampMat: ein Update fuer alle) ──
  const ledCols = 4;
  const ledXStep = 0.055;
  for (let col = 0; col < ledCols; col++) {
    const disc = new THREE.Mesh(
      new THREE.CircleGeometry(0.016, segs(10)),
      lampMat   // shared material — emissiveIntensity update on lampMat drives all
    );
    disc.position.set(
      (col - (ledCols - 1) / 2) * ledXStep,
      0.015,
      0.100   // just in front of the lens panel to avoid z-fight
    );
    group.add(disc);
  }

  // ── 4 Ausgangs-Dosen (Kaltgeraete-/Schuko-Andeutung) an der Front unten ────
  const socketMat = new THREE.MeshStandardMaterial({ color: 0x111111, metalness: 0.7, roughness: 0.4 });
  for (let col = 0; col < 4; col++) {
    const socket = new THREE.Mesh(
      new THREE.BoxGeometry(0.038, 0.038, 0.012),
      socketMat
    );
    socket.position.set((col - 1.5) * 0.055, -0.032, 0.098);
    group.add(socket);
  }

  return { group, head: group, lamp: lensPanel };
}

// FLA-4: neutrale Geometrie fuer importierte Geraete der Klasse `other`.
// QLC+ bildet u.a. Fan/Effect/Other hierhin ab; der bisherige PAR-Fallback
// suggerierte deshalb eine runde Lampe. Das Modell bleibt absichtlich
// herstellerneutral, behaelt aber den bisherigen Single-Head-/DMX-Vertrag:
// `head` traegt den Beam, `lamp` zeigt Farbe und Intensitaet an.
export function buildOther() {
  const group = new THREE.Group();
  group.userData.fixtureModel = 'other';

  const housingMat = new THREE.MeshStandardMaterial({
    color: 0x20232b, metalness: 0.65, roughness: 0.42,
  });
  const edgeMat = new THREE.MeshStandardMaterial({
    color: 0x353a46, metalness: 0.78, roughness: 0.32,
  });
  const detailMat = new THREE.MeshStandardMaterial({
    color: 0x7a8292, metalness: 0.72, roughness: 0.28,
  });

  // Kompaktes Effektgeraet/Controller-Gehaeuse statt einer Lampen-Silhouette.
  const housing = new THREE.Mesh(new THREE.BoxGeometry(0.56, 0.28, 0.42), housingMat);
  housing.name = 'other-housing';
  housing.castShadow = true;
  group.add(housing);

  // Deckel, Boden und vier geschuetzte Gehaeusekanten erzeugen einen
  // robusten Flightcase-Look, ohne einen konkreten Geraetetyp vorzugeben.
  [-0.155, 0.155].forEach((y) => {
    const plate = new THREE.Mesh(new THREE.BoxGeometry(0.60, 0.035, 0.46), edgeMat);
    plate.position.y = y;
    plate.castShadow = true;
    group.add(plate);
  });
  [-0.285, 0.285].forEach((x) => {
    [-0.215, 0.215].forEach((z) => {
      const guard = new THREE.Mesh(new THREE.BoxGeometry(0.035, 0.31, 0.035), edgeMat);
      guard.position.set(x, 0, z);
      guard.castShadow = true;
      group.add(guard);
    });
  });

  // Universal-Haltebuegel: das Modell bleibt sowohl stehend als auch an einer
  // Traverse sofort als technisches Geraet erkennbar.
  [-0.34, 0.34].forEach((x) => {
    const arm = new THREE.Mesh(new THREE.BoxGeometry(0.045, 0.30, 0.07), edgeMat);
    arm.position.set(x, 0.20, 0);
    arm.castShadow = true;
    group.add(arm);
  });
  const bridge = new THREE.Mesh(new THREE.BoxGeometry(0.72, 0.055, 0.07), edgeMat);
  bridge.position.y = 0.35;
  bridge.castShadow = true;
  group.add(bridge);

  // Frontseitiges Ident-Feld mit geometrischem Fragezeichen. Kein Font- oder
  // Textur-Asset noetig, daher bleibt das Modell offline und cache-freundlich.
  const idPlate = new THREE.Mesh(
    new THREE.PlaneGeometry(0.28, 0.19),
    new THREE.MeshStandardMaterial({ color: 0x101218, metalness: 0.35, roughness: 0.58 })
  );
  idPlate.position.set(0, 0.025, 0.216);
  group.add(idPlate);
  const mark = new THREE.Line(
    new THREE.BufferGeometry().setFromPoints([
      new THREE.Vector3(-0.055, 0.100, 0.225),
      new THREE.Vector3(0.035, 0.100, 0.225),
      new THREE.Vector3(0.060, 0.072, 0.225),
      new THREE.Vector3(0.060, 0.035, 0.225),
      new THREE.Vector3(-0.015, -0.005, 0.225),
      new THREE.Vector3(-0.015, -0.042, 0.225),
    ]),
    new THREE.LineBasicMaterial({ color: 0xaab2c2 })
  );
  group.add(mark);
  const markDot = new THREE.Mesh(new THREE.BoxGeometry(0.026, 0.026, 0.012), detailMat);
  markDot.position.set(-0.015, -0.082, 0.224);
  group.add(markDot);

  // Rueckseitige Lueftungsschlitze in EINEM LineSegments-Drawcall.
  const ventPoints = [];
  for (let i = 0; i < 5; i++) {
    const x = -0.07 + i * 0.035;
    ventPoints.push(
      new THREE.Vector3(x, -0.06, -0.217),
      new THREE.Vector3(x, 0.06, -0.217)
    );
  }
  group.add(new THREE.LineSegments(
    new THREE.BufferGeometry().setFromPoints(ventPoints),
    new THREE.LineBasicMaterial({ color: 0x7a8292 })
  ));

  // Unterseitiges Status-/Output-Feld: dieselbe DMX-Rueckmeldung wie der alte
  // PAR-Fallback, aber rechteckig und damit optisch eindeutig `other`.
  const lamp = new THREE.Mesh(
    new THREE.BoxGeometry(0.24, 0.018, 0.13),
    new THREE.MeshStandardMaterial({
      color: 0x30343f, emissive: 0x000000, emissiveIntensity: 0,
      metalness: 0.2, roughness: 0.32,
    })
  );
  lamp.name = 'other-status-lamp';
  lamp.position.y = -0.182;
  group.add(lamp);

  return { group, head: group, lamp };
}

export function buildScanner() {
  // FM-1: Scanner mit BEWEGLICHER Spiegel-Optik (vorher statisch). Aufbau wie ein
  // Moving Head: festes Gehaeuse -> yoke (pant um Y) -> head/Spiegel (kippt um X).
  // Der Strahl haengt (via model.head in fixtures.js#addFixture) am Kopf und
  // schwenkt so mit Pan/Tilt-DMX. updateFixture animiert Scanner analog zum MH.
  // Reale Referenz (FM-Runde 2): kompakter Spiegel-Scanner der JB-Systems-
  // Dynamo-Klasse — 385 x 170 x 120 mm, laengliches Gehaeuse, Spiegel sitzt
  // am GEHAEUSE-ENDE (nicht mittig): Lampe/Optik stecken im hinteren Teil,
  // der Strahl tritt vorn aus und trifft den freistehenden Spiegel.
  const group = new THREE.Group();
  const baseMat = new THREE.MeshStandardMaterial({ color: 0x1a1a1a, metalness: 0.6, roughness: 0.4 });
  // Festes Gehaeuse (Lampen-/Elektronik-Kompartment), lange Achse X,
  // nach hinten (+X) versetzt, damit vorn (-X) Platz fuer den Spiegel bleibt.
  const body = new THREE.Mesh(new THREE.BoxGeometry(0.40, 0.14, 0.15), baseMat);
  body.position.set(0.06, 0.07, 0);
  body.castShadow = true;
  group.add(body);
  // Pan-Pivot (rotiert um Y) am vorderen Gehaeuse-Ende
  const yoke = new THREE.Group();
  yoke.position.set(-0.12, 0.14, 0);
  group.add(yoke);
  const armMat = new THREE.MeshStandardMaterial({ color: 0x111111, metalness: 0.5, roughness: 0.5 });
  const arm = new THREE.Mesh(new THREE.BoxGeometry(0.06, 0.13, 0.06), armMat);
  arm.position.set(-0.09, 0.055, 0);
  yoke.add(arm);
  // Tilt-Pivot (Spiegelkopf, kippt um X)
  const head = new THREE.Group();
  head.position.set(0, 0.12, 0);
  yoke.add(head);
  // Spiegel: metallische ~45°-Scheibe (die sichtbare bewegte Kernoptik)
  const mirror = new THREE.Mesh(
    new THREE.CircleGeometry(0.085, segs(24)),
    new THREE.MeshStandardMaterial({ color: 0x99a0aa, metalness: 0.95, roughness: 0.05, side: THREE.DoubleSide })
  );
  mirror.rotation.x = -Math.PI / 4;
  head.add(mirror);
  // Emissive Lens (DMX-Farb-Feedback) am Kopf -> pant/kippt mit
  const lens = new THREE.Mesh(
    new THREE.CircleGeometry(0.045, segs(16)),
    new THREE.MeshStandardMaterial({ color: 0xffffff, emissive: 0xffffff, emissiveIntensity: 0, roughness: 0.1, side: THREE.DoubleSide })
  );
  lens.position.set(0, -0.015, 0.08);
  lens.rotation.x = -Math.PI / 2;
  head.add(lens);
  // BEWUSST KEIN scanner.dae-Overlay: das statische Modell wuerde den beweglichen
  // Spiegelkopf verdecken (gleiche Entscheidung wie beim Moving Head). Ein optisch
  // reicheres Modell muesste sauber in yoke/head gesplittet werden.
  return { group, yoke, head, lens, mirror };
}

export function buildSmoke() {
  // Reale Referenz (FM-Runde 2): kompakte DJ-Nebelmaschine (Eurolite N-10:
  // 145 x 170 x 265 mm; Antari-Z-Klasse etwas groesser) — flacher laenglicher
  // Kasten mit vorstehender Duese. Vorher ein 0,55-m-Klotz.
  const group = new THREE.Group();
  const baseMat = new THREE.MeshStandardMaterial({ color: 0x2a2a2a, metalness: 0.4, roughness: 0.6 });
  const body = new THREE.Mesh(
    new THREE.BoxGeometry(0.20, 0.17, 0.33),
    baseMat
  );
  body.castShadow = true;
  group.add(body);
  // Vorstehende Ausstoss-Duese (Zylinder) an der Front.
  const spout = new THREE.Mesh(
    new THREE.CylinderGeometry(0.028, 0.034, 0.05, segs(12)),
    new THREE.MeshStandardMaterial({ color: 0x555555, metalness: 0.7, roughness: 0.3 })
  );
  spout.rotation.x = Math.PI / 2;
  spout.position.set(0, 0.02, -0.185);
  group.add(spout);
  // Haengebuegel oben (die Klasse wird oft an der Traverse montiert).
  const bracket = new THREE.Mesh(new THREE.BoxGeometry(0.16, 0.02, 0.05), baseMat);
  bracket.position.y = 0.10;
  group.add(bracket);
  // Nozzle / emissive mesh (small circle at front)
  const nozzle = new THREE.Mesh(
    new THREE.CircleGeometry(0.026, segs(12)),
    new THREE.MeshStandardMaterial({ color: 0xcccccc, emissive: 0xffffff, emissiveIntensity: 0, roughness: 0.2, side: THREE.DoubleSide })
  );
  nozzle.position.set(0, 0.02, -0.211);
  nozzle.rotation.x = Math.PI / 2;
  group.add(nozzle);
  // Load real model
  loadModel('assets/models/fixtures/smoke.dae', (model) => {
    if (!model) return;
    fitModelToSize(model, { x: 0.22, y: 0.18, z: 0.36 });
    model.traverse(c => { if (c.isMesh) { c.castShadow = true; } });
    body.visible = false;
    group.add(model);
  });
  return { group, head: group, lamp: nozzle };
}

export function buildHazer() {
  // Reale Referenz (FM-Runde 2): Kompressor-Hazer der Antari-HZ-100-Klasse —
  // 250 x 294 x 490 mm: laenglicher, leicht hochkantiger Kasten (hoeher als
  // breit), Ausblasgitter vorn oben, Tragegriff. Vorher 0,55-m-Wuerfel.
  const group = new THREE.Group();
  const baseMat = new THREE.MeshStandardMaterial({ color: 0x222222, metalness: 0.45, roughness: 0.55 });
  const body = new THREE.Mesh(
    new THREE.BoxGeometry(0.25, 0.28, 0.48),
    baseMat
  );
  body.castShadow = true;
  group.add(body);
  // Tragegriff oben (Buegel).
  const handle = new THREE.Mesh(new THREE.BoxGeometry(0.05, 0.025, 0.24), baseMat);
  handle.position.y = 0.165;
  group.add(handle);
  // Ausblasgitter-Rahmen vorn oben (die Duese sitzt beim Hazer hoch).
  const grille = new THREE.Mesh(
    new THREE.BoxGeometry(0.16, 0.09, 0.015),
    new THREE.MeshStandardMaterial({ color: 0x3a3a3a, metalness: 0.6, roughness: 0.4 })
  );
  grille.position.set(0, 0.08, -0.243);
  group.add(grille);
  // Lamp / indicator mesh on front face
  const lamp = new THREE.Mesh(
    new THREE.CircleGeometry(0.045, segs(12)),
    new THREE.MeshStandardMaterial({ color: 0xaaaaaa, emissive: 0xffffff, emissiveIntensity: 0, roughness: 0.15, side: THREE.DoubleSide })
  );
  lamp.position.set(0, 0.08, -0.252);
  lamp.rotation.x = Math.PI / 2;
  group.add(lamp);
  // Load real model
  loadModel('assets/models/fixtures/hazer.dae', (model) => {
    if (!model) return;
    fitModelToSize(model, { x: 0.26, y: 0.30, z: 0.50 });
    model.traverse(c => { if (c.isMesh) { c.castShadow = true; } });
    body.visible = false;
    group.add(model);
  });
  return { group, head: group, lamp };
}

export function buildLaser() {
  // Reale Referenz (FM-Runde 2): Ehaho L2600 Partylaser — 201 x 155 x 66 mm
  // flaches Alu-Gehaeuse mit Frontfenster und Haltebuegel. Vorher ein zu
  // hoher 0,14-m-Wuerfelblock ohne Buegel.
  const group = new THREE.Group();
  const emitterMat = new THREE.MeshStandardMaterial({ color: 0x0d0d0d, metalness: 0.7, roughness: 0.3 });
  const emitter = new THREE.Mesh(
    new THREE.BoxGeometry(0.20, 0.07, 0.16),
    emitterMat
  );
  emitter.castShadow = true;
  group.add(emitter);
  // Frontblende mit Austrittsfenster (dunkles Glas, leicht vorstehend).
  const windowPane = new THREE.Mesh(
    new THREE.BoxGeometry(0.12, 0.045, 0.008),
    new THREE.MeshStandardMaterial({ color: 0x101418, metalness: 0.3, roughness: 0.15 })
  );
  windowPane.position.set(0, 0, -0.082);
  group.add(windowPane);
  // Haltebuegel (die Klasse haengt am Buegel oder steht auf ihm).
  [-0.115, 0.115].forEach(x => {
    const arm = new THREE.Mesh(new THREE.BoxGeometry(0.018, 0.10, 0.04), emitterMat);
    arm.position.set(x, 0.03, 0);
    group.add(arm);
  });
  const yokeBar = new THREE.Mesh(new THREE.BoxGeometry(0.25, 0.02, 0.04), emitterMat);
  yokeBar.position.y = 0.085;
  group.add(yokeBar);
  // Seitliches Lueftergitter (charakteristisch fuer die Alu-Klasse).
  const vent = new THREE.Mesh(
    new THREE.BoxGeometry(0.008, 0.045, 0.10),
    new THREE.MeshStandardMaterial({ color: 0x2c2f34, metalness: 0.6, roughness: 0.4 })
  );
  vent.position.set(0.10, 0, 0.01);
  group.add(vent);
  // Aperture lamp (emissive; colour driven by DMX)
  const lamp = new THREE.Mesh(
    new THREE.CircleGeometry(0.025, segs(10)),
    new THREE.MeshStandardMaterial({ color: 0x00ff00, emissive: 0x00ff00, emissiveIntensity: 1.0, roughness: 0.05, side: THREE.DoubleSide })
  );
  lamp.position.set(0, 0, -0.088);
  lamp.rotation.x = Math.PI / 2;
  group.add(lamp);
  // Fan of ~5 thin emissive beam lines radiating forward (downward in world-Y when hung)
  const beamMat = new THREE.MeshBasicMaterial({
    color: 0x00ff00,
    transparent: true,
    opacity: 0.6,
    blending: THREE.AdditiveBlending,
    depthWrite: false,
  });
  const FAN_ANGLES = [-0.35, -0.175, 0, 0.175, 0.35];  // radians spread in X
  const laserBeams = [];
  FAN_ANGLES.forEach((angle) => {
    const beamLen = 1.8;
    const geo = new THREE.CylinderGeometry(0.005, 0.005, beamLen, 4);
    const beam = new THREE.Mesh(geo, beamMat.clone());
    // Position: start just below emitter, fan out along Z (forward) with X spread
    beam.position.set(Math.sin(angle) * beamLen * 0.5, 0, -0.1 - Math.cos(angle) * beamLen * 0.5);
    beam.rotation.x = Math.PI / 2 - angle * 0.6;  // tilt so beam fans outward
    beam.rotation.z = angle;
    group.add(beam);
    laserBeams.push(beam);
  });
  // laserBeams zurueckgeben, damit updateFixture sie per DMX faerbt/dimmt
  // (vorher fix gruen 0x00ff00 / opacity 0.6, unabhaengig von Farbe/Intensitaet).
  return { group, head: group, lamp, laserBeams };
}

// ── Spider (Doppel-Bar Moving Head) ─────────────────────────────────────────
// Echtes Geraet (z.B. U King SPIDER14): KEIN Pan/Yoke, sondern ZWEI PARALLEL
// liegende Lichtleisten/Bars mit je EIGENEM Tilt-Motor. Jede Bar traegt 4
// EINZELFARBEN-LEDs (kein RGBW-Mix pro Linse): Bar L = Rot, Gruen, Blau, Weiss;
// Bar R ist GESPIEGELT = Weiss, Blau, Gruen, Rot. Jede LED leuchtet einzeln nach
// ihrem eigenen Kanal (color_r->rote LED, color_g->gruene, color_b->blaue,
// color_w->weisse). Die zwei Bars schwenken gegeneinander (Tilt um X) = Schere.
// mirrored (Default true): 2. Bar zeigt die Farben GESPIEGELT (W,B,G,R). Bei
// false sind beide Bars gleichlaeufig/parallel (R,G,B,W) — selber Controller,
// leicht andere Bauweise (per-Fixture-Option im Patch-Dialog).
export function buildSpider(mirrored) {
  // Reale Referenz (FM-Runde 2): 8x10W-RGBW-Spider (U`King-/Lixada-Klasse) —
  // 400 x 250 x 200 mm, 4,5 kg. Vorher war das Gehaeuse 0,88 m breit und
  // 0,54 m tief (mehr als doppelt so gross wie das echte Geraet).
  const group = new THREE.Group();
  // ── Nicer central body (replaces plain bracket) ───────────────────────────
  // Main body block — slightly chamfered look via two layered boxes
  const bodyMat = new THREE.MeshStandardMaterial({ color: 0x1c1c1c, metalness: 0.7, roughness: 0.38 });
  const bodyMain = new THREE.Mesh(new THREE.BoxGeometry(0.40, 0.11, 0.22), bodyMat);
  bodyMain.position.y = 0.075;
  bodyMain.castShadow = true;
  group.add(bodyMain);
  // Slim accent strip along the front face of the body
  const accentMat = new THREE.MeshStandardMaterial({ color: 0x2e2e2e, metalness: 0.8, roughness: 0.3 });
  const accentStrip = new THREE.Mesh(new THREE.BoxGeometry(0.38, 0.03, 0.02), accentMat);
  accentStrip.position.set(0, 0.075, 0.115);
  group.add(accentStrip);
  // Side ribs for visual detail
  [-0.185, 0.185].forEach((xOff) => {
    const rib = new THREE.Mesh(new THREE.BoxGeometry(0.03, 0.13, 0.24), bodyMat);
    rib.position.set(xOff, 0.075, 0);
    rib.castShadow = true;
    group.add(rib);
  });

  // ── Top yoke-mount cap (non-emissive, on root group) ──────────────────────
  const yokeMat = new THREE.MeshStandardMaterial({ color: 0x252525, metalness: 0.75, roughness: 0.35 });
  const yokeCap = new THREE.Mesh(new THREE.CylinderGeometry(0.055, 0.07, 0.045, segs(14)), yokeMat);
  yokeCap.position.set(0, 0.125, 0);
  yokeCap.castShadow = true;
  group.add(yokeCap);
  // Small bolt detail on top of cap
  const boltMat = new THREE.MeshStandardMaterial({ color: 0x3a3a3a, metalness: 0.9, roughness: 0.2 });
  const bolt = new THREE.Mesh(new THREE.CylinderGeometry(0.018, 0.018, 0.03, 8), boltMat);
  bolt.position.set(0, 0.16, 0);
  group.add(bolt);

  // Fixfarben der LEDs. ch = Index in [color_r, color_g, color_b, color_w].
  const LED = {
    r: { c: new THREE.Color(1.00, 0.00, 0.00), ch: 0 },
    g: { c: new THREE.Color(0.00, 1.00, 0.00), ch: 1 },
    b: { c: new THREE.Color(0.10, 0.25, 1.00), ch: 2 },
    w: { c: new THREE.Color(1.00, 1.00, 1.00), ch: 3 },
  };
  // Bar L (Bank 1, vorne): immer R G B W.
  const barL = [LED.r, LED.g, LED.b, LED.w];
  // Bar R (Bank 2, hinten): gespiegelt W B G R, oder parallel R G B W.
  const barR = (mirrored === false)
    ? [LED.r, LED.g, LED.b, LED.w]
    : [LED.w, LED.b, LED.g, LED.r];
  const LAYOUT = [
    { zoff: -0.075, leds: barL },
    { zoff:  0.075, leds: barR },
  ];
  const XS = [-0.126, -0.042, 0.042, 0.126];   // LED-Positionen entlang der Bar (X)

  const bars = [];
  LAYOUT.forEach((def) => {
    // Pivot dreht die ganze Bar um X (Tilt). rotation.x=0 => Beams nach unten.
    const pivot = new THREE.Group();
    pivot.position.set(0, 0, def.zoff);
    group.add(pivot);
    // Bar-Koerper laeuft entlang X
    const arm = new THREE.Mesh(
      new THREE.BoxGeometry(0.34, 0.05, 0.07),
      new THREE.MeshStandardMaterial({ color: 0x0d0d0d, metalness: 0.5, roughness: 0.5 })
    );
    arm.castShadow = true;
    pivot.add(arm);

    // ── Cosmetic additions on the pivot (tilt with the bar) ────────────────
    // Bottom fascia strip — a thin plate below the arm
    const fasciaMat = new THREE.MeshStandardMaterial({ color: 0x202020, metalness: 0.6, roughness: 0.42 });
    const fascia = new THREE.Mesh(new THREE.BoxGeometry(0.34, 0.014, 0.085), fasciaMat);
    fascia.position.set(0, -0.05, 0);
    pivot.add(fascia);

    // End-cap discs at the arm ends (cosmetic, non-emissive)
    const capMat = new THREE.MeshStandardMaterial({ color: 0x1a1a1a, metalness: 0.65, roughness: 0.4 });
    [-0.165, 0.165].forEach((xEnd) => {
      const cap = new THREE.Mesh(new THREE.CylinderGeometry(0.026, 0.026, 0.075, segs(10)), capMat);
      cap.rotation.z = Math.PI / 2;
      cap.position.set(xEnd, 0, 0);
      pivot.add(cap);
    });

    const lenses = [];
    def.leds.forEach((led, k) => {
      // Grund-Tint in der LED-Fixfarbe (dezent), damit man die R/G/B/W-Anordnung
      // auch bei dunkler LED erkennt.
      const lens = new THREE.Mesh(
        new THREE.CircleGeometry(0.030, segs(18)),
        new THREE.MeshStandardMaterial({
          color: led.c.clone().multiplyScalar(0.22),
          emissive: 0x000000, roughness: 0.25, side: THREE.DoubleSide,
        })
      );
      lens.position.set(XS[k], -0.038, 0);
      lens.rotation.x = -Math.PI / 2;        // Flaeche zeigt nach unten
      lens.userData.ledColor = led.c;
      lens.userData.ch = led.ch;             // welcher Kanal diese LED treibt
      pivot.add(lens);
      lenses.push(lens);

      // Thin bezel ring around each lens (RingGeometry, non-emissive, on pivot)
      const bezelMat = new THREE.MeshStandardMaterial({ color: 0x303030, metalness: 0.75, roughness: 0.35, side: THREE.DoubleSide });
      const bezel = new THREE.Mesh(
        new THREE.RingGeometry(0.031, 0.042, segs(18)),
        bezelMat
      );
      bezel.position.set(XS[k], -0.036, 0);  // same plane as lens, slightly raised
      bezel.rotation.x = -Math.PI / 2;
      pivot.add(bezel);
    });
    bars.push({ pivot, lenses, beams: [] });
  });
  return { group, bars, isSpider: true };
}

// FM-3: PAR-Bar — N einzeln faerbbare PARs auf einem horizontalen Balken (z.B.
// 4er-/8er-PAR-Bar). Jeder PAR = ein Kopf (heads[i]) mit eigener Farbe + eigenem
// nach unten gerichteten Beam. Statisch (kein Pan/Tilt); dafuer ist die Mover-Bar
// (FM-4) zustaendig. n aus dem Kanal-Layout (Anzahl RGBW-Banks, via Python nHeads).
export function buildParBar(n, pixelStyle) {
  n = Math.max(1, Math.min(24, Math.floor(n || 4)));
  const group = new THREE.Group();
  const barMat = new THREE.MeshStandardMaterial({ color: 0x1a1a1a, metalness: 0.5, roughness: 0.5 });

  if (pixelStyle) {
    // FM-8: PIXEL-Bar-Variante (fixture_type 'led_bar' mit vielen Segmenten):
    // schlankes Gehaeuse + N rechteckige, EINZELN faerbbare Segmente an der
    // Unterseite (Ausgang -Y wie die PAR-Variante -> par_bar-Render-Branch in
    // fixtures.js passt unveraendert: ph.lens + ph.beam pro Kopf). Gleicher
    // parHeads-Vertrag wie unten — nur die Optik ist Bar-mit-Pixeln statt
    // N PAR-Dosen. Querschnitt real ~88 x 65 mm (Stairville-1m-Klasse).
    const spacing = 0.125;
    const width = (n - 1) * spacing + 0.19;
    const housing = new THREE.Mesh(new THREE.BoxGeometry(width, 0.075, 0.09), barMat);
    housing.castShadow = true;
    group.add(housing);
    const parHeads = [];
    const startX = -(n - 1) * spacing / 2;
    for (let i = 0; i < n; i++) {
      const x = startX + i * spacing;
      const lens = new THREE.Mesh(
        new THREE.BoxGeometry(0.105, 0.018, 0.07),
        new THREE.MeshStandardMaterial({
          color: 0x303030, emissive: 0x000000, emissiveIntensity: 0, roughness: 0.3,
        })
      );
      lens.position.set(x, -0.044, 0);       // Unterseite, Ausgang -Y
      group.add(lens);
      parHeads.push({ lens, x });
    }
    return { group, parHeads, isParBar: true };
  }

  // Reale Referenz (FM-Runde 2): ADJ Dotz TPar System — 4 Pods auf ~1,0 m
  // Bar (1000 x 320 x 82 mm), Pod-Pitch ~0,25 m, Pod Ø ~0,16 m. Vorher
  // ergaben 4 Koepfe eine 1,8-m-Bar mit Ø-0,4-m-Dosen.
  const spacing = 0.25;
  const width = (n - 1) * spacing + 0.30;
  // Horizontaler Traeger-Balken entlang X
  const bar = new THREE.Mesh(new THREE.BoxGeometry(width, 0.08, 0.10), barMat);
  bar.castShadow = true;
  group.add(bar);
  const parHeads = [];
  const startX = -(n - 1) * spacing / 2;
  for (let i = 0; i < n; i++) {
    const x = startX + i * spacing;
    // PAR-Gehaeuse (kurzer Zylinder, nach unten offen)
    const can = new THREE.Mesh(new THREE.CylinderGeometry(0.075, 0.085, 0.15, segs(16)), barMat);
    can.position.set(x, -0.10, 0);
    can.castShadow = true;
    group.add(can);
    // Linse (emissive, faerbbar) — zeigt nach unten
    const lens = new THREE.Mesh(
      new THREE.CircleGeometry(0.065, segs(20)),
      new THREE.MeshStandardMaterial({
        color: 0x808080, emissive: 0x000000, emissiveIntensity: 0,
        roughness: 0.2, side: THREE.DoubleSide,
      })
    );
    lens.rotation.x = -Math.PI / 2;          // Normale -Y (nach unten)
    lens.position.set(x, -0.178, 0);
    group.add(lens);
    parHeads.push({ lens, x });
  }
  return { group, parHeads, isParBar: true };
}

// FM-4: Mover-Bar — N Mini-Moving-Heads auf einem Balken, jeder Kopf einzeln
// pan/tilt/faerbbar (z.B. Pixel-Beam-Bar mit 4/8 beweglichen Koepfen). Jeder
// Kopf = Yoke (pant um Y) -> Head (kippt um X) -> Linse. heads[i].pan/tilt/farbe
// treiben Kopf i (Datenmodell via FM-2 pro-Kopf-Pan). n = RGBW-Bank-Anzahl.
export function buildMoverBar(n) {
  // Reale Referenz (FM-Runde 2): 4-Kopf-Moving-Bar (Soundsation-AXIS-Klasse) —
  // 1004 x 271 x 115 mm, Kopf-Pitch ~0,25 m, Kopf Ø ~0,10 m. Vorher ergaben
  // 4 Koepfe eine 2,05-m-Bar mit Ø-0,22-m-Koepfen.
  n = Math.max(1, Math.min(24, Math.floor(n || 4)));
  const group = new THREE.Group();
  const barMat = new THREE.MeshStandardMaterial({ color: 0x1a1a1a, metalness: 0.5, roughness: 0.5 });
  const yokeMat = new THREE.MeshStandardMaterial({ color: 0x111111, metalness: 0.5, roughness: 0.5 });
  const spacing = 0.25;
  const width = (n - 1) * spacing + 0.30;
  const bar = new THREE.Mesh(new THREE.BoxGeometry(width, 0.10, 0.115), barMat);
  bar.castShadow = true;
  group.add(bar);
  const moverHeads = [];
  const startX = -(n - 1) * spacing / 2;
  for (let i = 0; i < n; i++) {
    const x = startX + i * spacing;
    // Pan-Pivot (yoke) unter dem Balken
    const yoke = new THREE.Group();
    yoke.position.set(x, -0.06, 0);
    group.add(yoke);
    [-0.062, 0.062].forEach(ax => {
      const arm = new THREE.Mesh(new THREE.BoxGeometry(0.03, 0.13, 0.03), yokeMat);
      arm.position.set(ax, -0.065, 0);
      yoke.add(arm);
    });
    // Tilt-Pivot (head)
    const head = new THREE.Group();
    head.position.set(0, -0.13, 0);
    yoke.add(head);
    const headBody = new THREE.Mesh(new THREE.CylinderGeometry(0.05, 0.05, 0.11, segs(14)), barMat);
    head.add(headBody);
    // Linse (faerbbar), zeigt bei Tilt=0 nach unten (-Y)
    const lens = new THREE.Mesh(
      new THREE.CircleGeometry(0.045, segs(18)),
      new THREE.MeshStandardMaterial({
        color: 0x808080, emissive: 0x000000, emissiveIntensity: 0,
        roughness: 0.2, side: THREE.DoubleSide,
      })
    );
    lens.rotation.x = -Math.PI / 2;
    lens.position.y = -0.062;
    head.add(lens);
    moverHeads.push({ yoke, head, lens });
  }
  return { group, moverHeads, isMoverBar: true };
}

// ════════════════════════════════════════════════════════════════════════════
// updateDmx-Handler pro Fixture-Typ (VIZ-13 3c Teil 2)
// Bodies 1:1 aus den ehemaligen updateFixture-Zweigen in fixtures.js
// (reiner Refactor). Signatur-Vertrag fuer die Registry (Design-Dokument
// Abschnitt (e)): updateDmx(f, dmx) mit dmx = {r,g,b,intensity,pan,tilt,
// heads,color,intNorm,skipBeam}; `dmx.color` ist EINE geteilte THREE.Color-
// Instanz pro Update-Aufruf und wird den Materialien ZUGEWIESEN (kein
// .copy()) — exakt die Instanz-Sharing-Semantik des Monolithen.
// ════════════════════════════════════════════════════════════════════════════

// ── Spider: zwei parallele Bars, je 4 EINZELFARBEN-LEDs ────────────────────
// Jede LED leuchtet einzeln nach ihrem eigenen Kanal (cr/cg/cb/cw der Bar);
// Master-Dimmer (intensity) ist gemeinsam. Tilt je Bar -> Scheren-Look.
export function updateSpiderDmx(f, dmx) {
  // Durchfall-Semantik der alten if-Kette: ohne Multihead-Struktur lief das
  // Fixture im Monolith durch den generischen Single-Head-Pfad.
  if (!f.isSpider || !f.bars) return updateGenericDmx(f, dmx);
  const { r, g, b, intNorm } = dmx;
  // FM-12-Review-Fix (HIGH): Ohne Multihead-Banks (z.B. viz_model-Override
  // 'spider' auf einem RGB-Geraet, oder Head-Daten transient noch nicht da)
  // blieben alle LEDs dauerhaft dunkel (chan aus leerem lastHeads = 0). Dann
  // die Top-Level-Farbe als Kanalwerte beider Bars verwenden, Tilt = Basis-Tilt.
  const hs = (f.lastHeads && f.lastHeads.length)
    ? f.lastHeads
    : [{ cr: r, cg: g, cb: b, cw: 0, tilt: dmx.tilt }];
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
  syncIconPos(f);
}

// ── FM-3: PAR-Bar — N einzeln gefaerbte PARs, gemeinsamer Master-Dimmer ─────
// Jeder PAR = ein Kopf (heads[i].r/g/b = Summenfarbe inkl. Weiss). Fallback:
// Kopf 0 = Basis-Farbe, weitere ohne Head-Daten aus.
export function updateParBarDmx(f, dmx) {
  if (!f.isParBar || !f.parHeads) return updateGenericDmx(f, dmx);
  const { r, g, b, intNorm } = dmx;
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
  syncIconPos(f);
}

// ── FM-4: Mover-Bar — N Mini-Moving-Heads, jeder Kopf einzeln pan/tilt/farbe ─
export function updateMoverBarDmx(f, dmx) {
  if (!f.isMoverBar || !f.moverHeads) return updateGenericDmx(f, dmx);
  const { r, g, b, intNorm, pan, tilt } = dmx;
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
  syncIconPos(f);
}

// Moving Head + Scanner: generischer Farb-Pfad PLUS Pan/Tilt-Mechanik.
// Reihenfolge-Vertrag: applyFloorAim liest die in applyPanTilt gesetzte
// Kopf-Rotation (getWorldQuaternion) — PanTilt MUSS vor FloorAim laufen.
export function updateMovingHeadDmx(f, dmx) {
  applyGenericColor(f, dmx);
  applyPanTilt(f, dmx);
  applyFloorAim(f, dmx);
  syncIconPos(f);
}

// Alle unbeweglichen Single-Head-Typen (par, led_bar, dimmer, strobe, laser,
// smoke, hazer, Fallback): wie updateMovingHeadDmx, nur ohne den PanTilt-
// Aufruf — der war fuer diese Typen im Monolith ein typ-geguardeter No-Op.
// smoke/hazer bekommen BEWUSST keinen No-Op-Handler: ihr Indikator-Lamp
// (f.lamp) und ihr Icon folgen im Monolith der DMX-Farbe — das bleibt so.
export function updateGenericDmx(f, dmx) {
  applyGenericColor(f, dmx);
  applyFloorAim(f, dmx);
  syncIconPos(f);
}

// ── updateDmx-Helfer (modul-privat) ─────────────────────────────────────────
// 1:1 aus dem ehemaligen generischen Schlussteil von updateFixture.

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
    // Dunkle Lichter komplett aus der Licht-Auswertung nehmen: ein SpotLight
    // mit intensity 0 kostet sonst weiterhin Shading in JEDEM beleuchteten
    // Pixel (three.js wertet alle sichtbaren Lichter pro Fragment aus) —
    // bei 48 Fixtures der groesste laufende Kostenblock auf schwachen GPUs.
    f.spot.visible = intNorm > 0.01;
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
