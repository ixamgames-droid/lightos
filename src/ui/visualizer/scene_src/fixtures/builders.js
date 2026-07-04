// VIZ-13 Schritt 3a-4: Einzel-Builder pro Fixture-Typ
// (ehem. stage_scene.html:1042-1500). Reines Verschieben.
import * as THREE from '../three/three.js';
import { loadModel, fitModelToSize } from '../scene/model_loader.js';

// ── Builders ─────────────────────────────────────────────────────────────────
export function buildMovingHead() {
  const group = new THREE.Group();
  const baseMat = new THREE.MeshStandardMaterial({ color: 0x222222, metalness: 0.6, roughness: 0.4 });
  const base = new THREE.Mesh(new THREE.CylinderGeometry(0.22, 0.25, 0.18, 16), baseMat);
  base.position.y = 0.09;
  base.castShadow = true;
  group.add(base);
  const yoke = new THREE.Group();
  yoke.position.y = 0.18;
  group.add(yoke);
  const yokeMat = new THREE.MeshStandardMaterial({ color: 0x111111, metalness: 0.5, roughness: 0.5 });
  [-0.18, 0.18].forEach(x => {
    const arm = new THREE.Mesh(new THREE.BoxGeometry(0.08, 0.45, 0.08), yokeMat);
    arm.position.set(x, 0.22, 0);
    yoke.add(arm);
  });
  const head = new THREE.Group();
  head.position.y = 0.4;
  yoke.add(head);
  const headBody = new THREE.Mesh(
    new THREE.CylinderGeometry(0.16, 0.16, 0.36, 16),
    new THREE.MeshStandardMaterial({ color: 0x1a1a1a, metalness: 0.5, roughness: 0.4 })
  );
  headBody.rotation.z = Math.PI / 2;
  head.add(headBody);
  const lens = new THREE.Mesh(
    new THREE.CylinderGeometry(0.14, 0.14, 0.02, 16),
    new THREE.MeshStandardMaterial({ color: 0x808080, metalness: 0.9, roughness: 0.05 })
  );
  lens.rotation.z = Math.PI / 2;
  lens.position.x = 0.19;
  head.add(lens);
  // BEWUSST KEIN .dae-Overlay: das geladene moving_head.dae wurde an die statische
  // Root-Group gehaengt (nicht an yoke/head) -> es pante/tiltete NICHT mit und der
  // Moving Head stand optisch still. Die prozedurale Geometrie (yoke pant um Y,
  // head tiltet um X) bewegt sich korrekt — bei einem Bewegungs-Visualizer ist
  // genau das der Sinn. (Ein optisch schoeneres Modell muesste sauber in yoke/head
  // gesplittet werden, sonst wuerde der Sockel mitkippen.)
  return { group, yoke, head, lens };
}

export function buildPar() {
  const group = new THREE.Group();
  const body = new THREE.Mesh(
    new THREE.CylinderGeometry(0.22, 0.22, 0.32, 16),
    new THREE.MeshStandardMaterial({ color: 0x222222, metalness: 0.5, roughness: 0.5 })
  );
  body.castShadow = true;
  group.add(body);
  const front = new THREE.Mesh(
    new THREE.CylinderGeometry(0.22, 0.22, 0.04, 16),
    new THREE.MeshStandardMaterial({ color: 0xcccccc, metalness: 0.95, roughness: 0.05 })
  );
  front.position.y = -0.18;
  group.add(front);
  // Try to overlay a real PAR model. If loaded, hide procedural body but keep lens for emissive.
  loadModel('assets/models/fixtures/par.dae', (model) => {
    if (!model) return;
    fitModelToSize(model, { x: 0.5, y: 0.5, z: 0.5 });
    model.traverse(c => { if (c.isMesh) { c.castShadow = true; } });
    body.visible = false;
    group.add(model);
  });
  return { group, head: group, lens: front };
}

export function buildLedBar() {
  const group = new THREE.Group();
  const body = new THREE.Mesh(
    new THREE.BoxGeometry(1.2, 0.12, 0.18),
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
    const px = new THREE.Mesh(new THREE.BoxGeometry(0.12, 0.08, 0.02), pxMat);
    px.position.set(-0.5 + i * 0.14, 0, 0.1);
    group.add(px);
    if (!firstPx) firstPx = px;
  }
  return { group, head: group, lamp: firstPx };
}

export function buildStrobe() {
  const group = new THREE.Group();
  const body = new THREE.Mesh(
    new THREE.BoxGeometry(0.6, 0.15, 0.5),
    new THREE.MeshStandardMaterial({ color: 0x111111, metalness: 0.4, roughness: 0.5 })
  );
  body.castShadow = true;
  group.add(body);
  const lamp = new THREE.Mesh(
    new THREE.BoxGeometry(0.5, 0.04, 0.4),
    new THREE.MeshStandardMaterial({ color: 0xeeeeee, roughness: 0.1 })
  );
  lamp.position.y = -0.08;
  group.add(lamp);
  loadModel('assets/models/fixtures/strobe.dae', (model) => {
    if (!model) return;
    fitModelToSize(model, { x: 0.7, y: 0.3, z: 0.6 });
    model.traverse(c => { if (c.isMesh) { c.castShadow = true; } });
    body.visible = false;
    group.add(model);
  });
  return { group, head: group, lamp };
}

export function buildDimmer() {
  const group = new THREE.Group();

  // ── Dark-metal housing ────────────────────────────────────────────────────
  const housingMat = new THREE.MeshStandardMaterial({ color: 0x1a1a1a, metalness: 0.65, roughness: 0.45 });
  const housing = new THREE.Mesh(
    new THREE.BoxGeometry(0.44, 0.36, 0.38),
    housingMat
  );
  housing.position.y = 0.0;
  housing.castShadow = true;
  group.add(housing);

  // ── Mounting-ear flanges (left and right) ─────────────────────────────────
  const earMat = new THREE.MeshStandardMaterial({ color: 0x222222, metalness: 0.55, roughness: 0.5 });
  [-0.28, 0.28].forEach((xOff) => {
    const ear = new THREE.Mesh(
      new THREE.BoxGeometry(0.06, 0.10, 0.22),
      earMat
    );
    ear.position.set(xOff, 0.13, 0);
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
    new THREE.PlaneGeometry(0.38, 0.28),
    lampMat
  );
  lensPanel.position.set(0, 0, 0.195);
  group.add(lensPanel);

  // ── 4×2 grid of emissive LED discs (share lampMat so one update covers all) ─
  const ledCols = 4;
  const ledRows = 2;
  const ledXStep = 0.085;
  const ledYStep = 0.09;
  for (let row = 0; row < ledRows; row++) {
    for (let col = 0; col < ledCols; col++) {
      const disc = new THREE.Mesh(
        new THREE.CircleGeometry(0.030, 10),
        lampMat   // shared material — emissiveIntensity update on lampMat drives all
      );
      disc.position.set(
        (col - (ledCols - 1) / 2) * ledXStep,
        (row - (ledRows - 1) / 2) * ledYStep,
        0.198   // just in front of the lens panel to avoid z-fight
      );
      group.add(disc);
    }
  }

  // ── Barn-door stub panels (top and bottom, non-emissive) ──────────────────
  const barnMat = new THREE.MeshStandardMaterial({ color: 0x111111, metalness: 0.7, roughness: 0.4 });
  [{ yOff: 0.195, rotX:  0.35 }, { yOff: -0.195, rotX: -0.35 }].forEach(({ yOff, rotX }) => {
    const door = new THREE.Mesh(
      new THREE.BoxGeometry(0.42, 0.06, 0.14),
      barnMat
    );
    door.position.set(0, yOff, 0.12);
    door.rotation.x = rotX;
    door.castShadow = true;
    group.add(door);
  });

  return { group, head: group, lamp: lensPanel };
}

export function buildScanner() {
  // FM-1: Scanner mit BEWEGLICHER Spiegel-Optik (vorher statisch). Aufbau wie ein
  // Moving Head: festes Gehaeuse -> yoke (pant um Y) -> head/Spiegel (kippt um X).
  // Der Strahl haengt (via model.head in fixtures.js#addFixture) am Kopf und
  // schwenkt so mit Pan/Tilt-DMX. updateFixture animiert Scanner analog zum MH.
  const group = new THREE.Group();
  const baseMat = new THREE.MeshStandardMaterial({ color: 0x1a1a1a, metalness: 0.6, roughness: 0.4 });
  // Festes Gehaeuse (Lampen-/Elektronik-Kompartment)
  const body = new THREE.Mesh(new THREE.BoxGeometry(0.52, 0.16, 0.34), baseMat);
  body.position.y = 0.08;
  body.castShadow = true;
  group.add(body);
  // Pan-Pivot (rotiert um Y) auf dem Gehaeuse
  const yoke = new THREE.Group();
  yoke.position.y = 0.16;
  group.add(yoke);
  const armMat = new THREE.MeshStandardMaterial({ color: 0x111111, metalness: 0.5, roughness: 0.5 });
  const arm = new THREE.Mesh(new THREE.BoxGeometry(0.12, 0.18, 0.12), armMat);
  arm.position.set(-0.18, 0.09, 0);
  yoke.add(arm);
  // Tilt-Pivot (Spiegelkopf, kippt um X)
  const head = new THREE.Group();
  head.position.set(0, 0.18, 0);
  yoke.add(head);
  // Spiegel: metallische ~45°-Scheibe (die sichtbare bewegte Kernoptik)
  const mirror = new THREE.Mesh(
    new THREE.CircleGeometry(0.16, 24),
    new THREE.MeshStandardMaterial({ color: 0x99a0aa, metalness: 0.95, roughness: 0.05, side: THREE.DoubleSide })
  );
  mirror.rotation.x = -Math.PI / 4;
  head.add(mirror);
  // Emissive Lens (DMX-Farb-Feedback) am Kopf -> pant/kippt mit
  const lens = new THREE.Mesh(
    new THREE.CircleGeometry(0.07, 16),
    new THREE.MeshStandardMaterial({ color: 0xffffff, emissive: 0xffffff, emissiveIntensity: 0, roughness: 0.1, side: THREE.DoubleSide })
  );
  lens.position.set(0, -0.02, 0.14);
  lens.rotation.x = -Math.PI / 2;
  head.add(lens);
  // BEWUSST KEIN scanner.dae-Overlay: das statische Modell wuerde den beweglichen
  // Spiegelkopf verdecken (gleiche Entscheidung wie beim Moving Head). Ein optisch
  // reicheres Modell muesste sauber in yoke/head gesplittet werden.
  return { group, yoke, head, lens, mirror };
}

export function buildSmoke() {
  const group = new THREE.Group();
  const baseMat = new THREE.MeshStandardMaterial({ color: 0x2a2a2a, metalness: 0.4, roughness: 0.6 });
  // Procedural fallback: simple box
  const body = new THREE.Mesh(
    new THREE.BoxGeometry(0.55, 0.35, 0.38),
    baseMat
  );
  body.castShadow = true;
  group.add(body);
  // Nozzle / emissive mesh (small circle at front)
  const nozzle = new THREE.Mesh(
    new THREE.CircleGeometry(0.06, 12),
    new THREE.MeshStandardMaterial({ color: 0xcccccc, emissive: 0xffffff, emissiveIntensity: 0, roughness: 0.2, side: THREE.DoubleSide })
  );
  nozzle.position.set(0, 0, -0.2);
  nozzle.rotation.x = Math.PI / 2;
  group.add(nozzle);
  // Load real model
  loadModel('assets/models/fixtures/smoke.dae', (model) => {
    if (!model) return;
    fitModelToSize(model, { x: 0.6, y: 0.4, z: 0.4 });
    model.traverse(c => { if (c.isMesh) { c.castShadow = true; } });
    body.visible = false;
    group.add(model);
  });
  return { group, head: group, lamp: nozzle };
}

export function buildHazer() {
  const group = new THREE.Group();
  const baseMat = new THREE.MeshStandardMaterial({ color: 0x222222, metalness: 0.45, roughness: 0.55 });
  // Procedural fallback: box slightly taller than smoke
  const body = new THREE.Mesh(
    new THREE.BoxGeometry(0.55, 0.45, 0.48),
    baseMat
  );
  body.castShadow = true;
  group.add(body);
  // Lamp / indicator mesh on front face
  const lamp = new THREE.Mesh(
    new THREE.CircleGeometry(0.07, 12),
    new THREE.MeshStandardMaterial({ color: 0xaaaaaa, emissive: 0xffffff, emissiveIntensity: 0, roughness: 0.15, side: THREE.DoubleSide })
  );
  lamp.position.set(0, 0.05, -0.25);
  lamp.rotation.x = Math.PI / 2;
  group.add(lamp);
  // Load real model
  loadModel('assets/models/fixtures/hazer.dae', (model) => {
    if (!model) return;
    fitModelToSize(model, { x: 0.6, y: 0.4, z: 0.5 });
    model.traverse(c => { if (c.isMesh) { c.castShadow = true; } });
    body.visible = false;
    group.add(model);
  });
  return { group, head: group, lamp };
}

export function buildLaser() {
  const group = new THREE.Group();
  // Small emitter body
  const emitterMat = new THREE.MeshStandardMaterial({ color: 0x0d0d0d, metalness: 0.7, roughness: 0.3 });
  const emitter = new THREE.Mesh(
    new THREE.BoxGeometry(0.22, 0.14, 0.18),
    emitterMat
  );
  emitter.castShadow = true;
  group.add(emitter);
  // Aperture lamp (emissive; colour driven by DMX)
  const lamp = new THREE.Mesh(
    new THREE.CircleGeometry(0.04, 10),
    new THREE.MeshStandardMaterial({ color: 0x00ff00, emissive: 0x00ff00, emissiveIntensity: 1.0, roughness: 0.05, side: THREE.DoubleSide })
  );
  lamp.position.set(0, 0, -0.1);
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
  const group = new THREE.Group();
  // ── Nicer central body (replaces plain bracket) ───────────────────────────
  // Main body block — slightly chamfered look via two layered boxes
  const bodyMat = new THREE.MeshStandardMaterial({ color: 0x1c1c1c, metalness: 0.7, roughness: 0.38 });
  const bodyMain = new THREE.Mesh(new THREE.BoxGeometry(0.88, 0.18, 0.54), bodyMat);
  bodyMain.position.y = 0.12;
  bodyMain.castShadow = true;
  group.add(bodyMain);
  // Slim accent strip along the front face of the body
  const accentMat = new THREE.MeshStandardMaterial({ color: 0x2e2e2e, metalness: 0.8, roughness: 0.3 });
  const accentStrip = new THREE.Mesh(new THREE.BoxGeometry(0.86, 0.04, 0.03), accentMat);
  accentStrip.position.set(0, 0.12, 0.275);
  group.add(accentStrip);
  // Side ribs for visual detail
  [-0.38, 0.38].forEach((xOff) => {
    const rib = new THREE.Mesh(new THREE.BoxGeometry(0.04, 0.22, 0.56), bodyMat);
    rib.position.set(xOff, 0.12, 0);
    rib.castShadow = true;
    group.add(rib);
  });

  // ── Top yoke-mount cap (non-emissive, on root group) ──────────────────────
  const yokeMat = new THREE.MeshStandardMaterial({ color: 0x252525, metalness: 0.75, roughness: 0.35 });
  const yokeCap = new THREE.Mesh(new THREE.CylinderGeometry(0.10, 0.13, 0.10, 14), yokeMat);
  yokeCap.position.set(0, 0.27, 0);
  yokeCap.castShadow = true;
  group.add(yokeCap);
  // Small bolt detail on top of cap
  const boltMat = new THREE.MeshStandardMaterial({ color: 0x3a3a3a, metalness: 0.9, roughness: 0.2 });
  const bolt = new THREE.Mesh(new THREE.CylinderGeometry(0.03, 0.03, 0.06, 8), boltMat);
  bolt.position.set(0, 0.35, 0);
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
    { zoff: -0.17, leds: barL },
    { zoff:  0.17, leds: barR },
  ];
  const XS = [-0.27, -0.09, 0.09, 0.27];   // LED-Positionen entlang der Bar (X)

  const bars = [];
  LAYOUT.forEach((def) => {
    // Pivot dreht die ganze Bar um X (Tilt). rotation.x=0 => Beams nach unten.
    const pivot = new THREE.Group();
    pivot.position.set(0, 0, def.zoff);
    group.add(pivot);
    // Bar-Koerper laeuft entlang X
    const arm = new THREE.Mesh(
      new THREE.BoxGeometry(0.72, 0.07, 0.10),
      new THREE.MeshStandardMaterial({ color: 0x0d0d0d, metalness: 0.5, roughness: 0.5 })
    );
    arm.castShadow = true;
    pivot.add(arm);

    // ── Cosmetic additions on the pivot (tilt with the bar) ────────────────
    // Bottom fascia strip — a thin plate below the arm
    const fasciaMat = new THREE.MeshStandardMaterial({ color: 0x202020, metalness: 0.6, roughness: 0.42 });
    const fascia = new THREE.Mesh(new THREE.BoxGeometry(0.72, 0.018, 0.12), fasciaMat);
    fascia.position.set(0, -0.07, 0);
    pivot.add(fascia);

    // End-cap discs at the arm ends (cosmetic, non-emissive)
    const capMat = new THREE.MeshStandardMaterial({ color: 0x1a1a1a, metalness: 0.65, roughness: 0.4 });
    [-0.36, 0.36].forEach((xEnd) => {
      const cap = new THREE.Mesh(new THREE.CylinderGeometry(0.038, 0.038, 0.10, 10), capMat);
      cap.rotation.z = Math.PI / 2;
      cap.position.set(xEnd, 0, 0);
      pivot.add(cap);
    });

    const lenses = [];
    def.leds.forEach((led, k) => {
      // Grund-Tint in der LED-Fixfarbe (dezent), damit man die R/G/B/W-Anordnung
      // auch bei dunkler LED erkennt.
      const lens = new THREE.Mesh(
        new THREE.CircleGeometry(0.05, 18),
        new THREE.MeshStandardMaterial({
          color: led.c.clone().multiplyScalar(0.22),
          emissive: 0x000000, roughness: 0.25, side: THREE.DoubleSide,
        })
      );
      lens.position.set(XS[k], -0.05, 0);
      lens.rotation.x = -Math.PI / 2;        // Flaeche zeigt nach unten
      lens.userData.ledColor = led.c;
      lens.userData.ch = led.ch;             // welcher Kanal diese LED treibt
      pivot.add(lens);
      lenses.push(lens);

      // Thin bezel ring around each lens (RingGeometry, non-emissive, on pivot)
      const bezelMat = new THREE.MeshStandardMaterial({ color: 0x303030, metalness: 0.75, roughness: 0.35, side: THREE.DoubleSide });
      const bezel = new THREE.Mesh(
        new THREE.RingGeometry(0.051, 0.068, 18),
        bezelMat
      );
      bezel.position.set(XS[k], -0.048, 0);  // same plane as lens, slightly raised
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
export function buildParBar(n) {
  n = Math.max(1, Math.min(24, Math.floor(n || 4)));
  const group = new THREE.Group();
  const barMat = new THREE.MeshStandardMaterial({ color: 0x1a1a1a, metalness: 0.5, roughness: 0.5 });
  const spacing = 0.44;
  const width = (n - 1) * spacing + 0.5;
  // Horizontaler Traeger-Balken entlang X
  const bar = new THREE.Mesh(new THREE.BoxGeometry(width, 0.16, 0.26), barMat);
  bar.castShadow = true;
  group.add(bar);
  const parHeads = [];
  const startX = -(n - 1) * spacing / 2;
  for (let i = 0; i < n; i++) {
    const x = startX + i * spacing;
    // PAR-Gehaeuse (kurzer Zylinder, nach unten offen)
    const can = new THREE.Mesh(new THREE.CylinderGeometry(0.17, 0.2, 0.18, 16), barMat);
    can.position.set(x, -0.13, 0);
    can.castShadow = true;
    group.add(can);
    // Linse (emissive, faerbbar) — zeigt nach unten
    const lens = new THREE.Mesh(
      new THREE.CircleGeometry(0.15, 20),
      new THREE.MeshStandardMaterial({
        color: 0x808080, emissive: 0x000000, emissiveIntensity: 0,
        roughness: 0.2, side: THREE.DoubleSide,
      })
    );
    lens.rotation.x = -Math.PI / 2;          // Normale -Y (nach unten)
    lens.position.set(x, -0.223, 0);
    group.add(lens);
    parHeads.push({ lens, x });
  }
  return { group, parHeads, isParBar: true };
}
