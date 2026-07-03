// VIZ-13 Schritt 3a-4: 2D top-down icon (ehem. stage_scene.html:1520-1705).
// Reines Verschieben - bleibt in 3a INTAKT (stirbt erst in 3c, siehe Design-
// Dokument Abschnitt (d)).
import * as THREE from '../three/three.js';

export function buildTopDownIcon(type) {
  const group = new THREE.Group();
  const matLine = new THREE.LineBasicMaterial({ color: 0xcccccc });
  let body, ring;
  if (type === 'moving_head') {
    // circle + arrow
    body = new THREE.Mesh(
      new THREE.CircleGeometry(0.6, 24),
      new THREE.MeshBasicMaterial({ color: 0x2a4060, transparent: true, opacity: 0.85 })
    );
    body.rotation.x = -Math.PI / 2;
    group.add(body);
    const arrowPts = [
      new THREE.Vector3(0, 0.05, 0),
      new THREE.Vector3(0, 0.05, -0.7),
    ];
    const arrowGeo = new THREE.BufferGeometry().setFromPoints(arrowPts);
    const arrow = new THREE.Line(arrowGeo, matLine);
    group.add(arrow);
    const tipPts = [
      new THREE.Vector3(-0.15, 0.05, -0.5),
      new THREE.Vector3(0, 0.05, -0.7),
      new THREE.Vector3(0.15, 0.05, -0.5),
    ];
    const tipGeo = new THREE.BufferGeometry().setFromPoints(tipPts);
    const tip = new THREE.Line(tipGeo, matLine);
    group.add(tip);
  } else if (type === 'par') {
    body = new THREE.Mesh(
      new THREE.CircleGeometry(0.55, 24),
      new THREE.MeshBasicMaterial({ color: 0x404040, transparent: true, opacity: 0.85 })
    );
    body.rotation.x = -Math.PI / 2;
    group.add(body);
  } else if (type === 'led_bar') {
    body = new THREE.Mesh(
      new THREE.PlaneGeometry(1.6, 0.4),
      new THREE.MeshBasicMaterial({ color: 0x303030, transparent: true, opacity: 0.85 })
    );
    body.rotation.x = -Math.PI / 2;
    group.add(body);
  } else if (type === 'spider') {
    // zwei kurze parallele Bars (Top-Down)
    const mkBar = (zoff) => {
      const m = new THREE.Mesh(
        new THREE.PlaneGeometry(1.3, 0.16),
        new THREE.MeshBasicMaterial({ color: 0x303048, transparent: true, opacity: 0.85 })
      );
      m.rotation.x = -Math.PI / 2;
      m.position.z = zoff;
      return m;
    };
    body = mkBar(-0.22);
    group.add(body);
    group.add(mkBar(0.22));
  } else if (type === 'strobe') {
    body = new THREE.Mesh(
      new THREE.PlaneGeometry(0.8, 0.8),
      new THREE.MeshBasicMaterial({ color: 0x505050, transparent: true, opacity: 0.85 })
    );
    body.rotation.x = -Math.PI / 2;
    group.add(body);
    // X cross
    const xpts = [
      new THREE.Vector3(-0.35, 0.05, -0.35), new THREE.Vector3(0.35, 0.05, 0.35),
      new THREE.Vector3(-0.35, 0.05, 0.35), new THREE.Vector3(0.35, 0.05, -0.35),
    ];
    const xGeo = new THREE.BufferGeometry().setFromPoints(xpts);
    const xLine = new THREE.LineSegments(xGeo, matLine);
    group.add(xLine);
  } else if (type === 'scanner') {
    // Square base + diagonal mirror line (top-down view of tilted mirror)
    body = new THREE.Mesh(
      new THREE.PlaneGeometry(0.8, 0.8),
      new THREE.MeshBasicMaterial({ color: 0x203040, transparent: true, opacity: 0.85 })
    );
    body.rotation.x = -Math.PI / 2;
    group.add(body);
    // Diagonal line representing the mirror
    const mpts = [
      new THREE.Vector3(-0.28, 0.05, -0.28),
      new THREE.Vector3(0.28, 0.05, 0.28),
    ];
    const mGeo = new THREE.BufferGeometry().setFromPoints(mpts);
    const mLine = new THREE.Line(mGeo, new THREE.LineBasicMaterial({ color: 0x88ccff }));
    group.add(mLine);
    // Arrow showing beam direction
    const sPts = [
      new THREE.Vector3(0, 0.05, 0),
      new THREE.Vector3(0, 0.05, -0.55),
    ];
    const sGeo = new THREE.BufferGeometry().setFromPoints(sPts);
    group.add(new THREE.Line(sGeo, matLine));
    const stPts = [
      new THREE.Vector3(-0.12, 0.05, -0.38),
      new THREE.Vector3(0, 0.05, -0.55),
      new THREE.Vector3(0.12, 0.05, -0.38),
    ];
    const stGeo = new THREE.BufferGeometry().setFromPoints(stPts);
    group.add(new THREE.Line(stGeo, matLine));
  } else if (type === 'smoke') {
    // Rounded rectangle (wider than tall) + cloud-puff arcs suggestion
    body = new THREE.Mesh(
      new THREE.PlaneGeometry(0.9, 0.55),
      new THREE.MeshBasicMaterial({ color: 0x3a3a3a, transparent: true, opacity: 0.85 })
    );
    body.rotation.x = -Math.PI / 2;
    group.add(body);
    // Three small circles suggesting puff output
    [{ x: -0.22, z: -0.32 }, { x: 0, z: -0.38 }, { x: 0.22, z: -0.32 }].forEach(p => {
      const puff = new THREE.Mesh(
        new THREE.CircleGeometry(0.08, 12),
        new THREE.MeshBasicMaterial({ color: 0x888888, transparent: true, opacity: 0.55 })
      );
      puff.rotation.x = -Math.PI / 2;
      puff.position.set(p.x, 0.04, p.z);
      group.add(puff);
    });
  } else if (type === 'hazer') {
    // Wide rectangle (landscape) + haze wave lines
    body = new THREE.Mesh(
      new THREE.PlaneGeometry(1.0, 0.55),
      new THREE.MeshBasicMaterial({ color: 0x353530, transparent: true, opacity: 0.85 })
    );
    body.rotation.x = -Math.PI / 2;
    group.add(body);
    // Two parallel wave-suggest lines across the front
    [-0.12, 0.12].forEach(xOff => {
      const wPts = [
        new THREE.Vector3(-0.38, 0.05, xOff),
        new THREE.Vector3(-0.19, 0.05, xOff - 0.08),
        new THREE.Vector3(0, 0.05, xOff),
        new THREE.Vector3(0.19, 0.05, xOff - 0.08),
        new THREE.Vector3(0.38, 0.05, xOff),
      ];
      const wGeo = new THREE.BufferGeometry().setFromPoints(wPts);
      group.add(new THREE.Line(wGeo, new THREE.LineBasicMaterial({ color: 0xaaaaaa })));
    });
  } else if (type === 'laser') {
    // Small square emitter body + radiating beam lines
    body = new THREE.Mesh(
      new THREE.PlaneGeometry(0.4, 0.3),
      new THREE.MeshBasicMaterial({ color: 0x102010, transparent: true, opacity: 0.9 })
    );
    body.rotation.x = -Math.PI / 2;
    group.add(body);
    // Fan of 5 beam rays radiating forward (negative Z = forward in top-down)
    const fanAngles = [-0.4, -0.2, 0, 0.2, 0.4];
    fanAngles.forEach(a => {
      const len = 0.75;
      const rPts = [
        new THREE.Vector3(0, 0.05, -0.15),
        new THREE.Vector3(Math.sin(a) * len, 0.05, -0.15 - Math.cos(a) * len),
      ];
      const rGeo = new THREE.BufferGeometry().setFromPoints(rPts);
      group.add(new THREE.Line(rGeo, new THREE.LineBasicMaterial({ color: 0x44ff44 })));
    });
  } else {
    body = new THREE.Mesh(
      new THREE.CircleGeometry(0.45, 16),
      new THREE.MeshBasicMaterial({ color: 0x606060, transparent: true, opacity: 0.85 })
    );
    body.rotation.x = -Math.PI / 2;
    group.add(body);
  }
  // Outline ring
  ring = new THREE.Mesh(
    new THREE.RingGeometry(0.62, 0.72, 24),
    new THREE.MeshBasicMaterial({ color: 0x88aaff, transparent: true, opacity: 0.0, side: THREE.DoubleSide })
  );
  ring.rotation.x = -Math.PI / 2;
  ring.position.y = 0.03;
  group.add(ring);
  group.userData.body = body;
  group.userData.ring = ring;
  // Force-pickable via tag
  body.userData.isTopDownIcon = true;
  body.userData.isFixtureMesh = true;
  // 2D-OCCLUSION-FIX: Fixture-Icons IMMER ueber (translucenten) Buehnen-Objekten
  // zeichnen, damit Strahler in der Top-Down-Ansicht nie unter einer Plattform/
  // einem Boden verschwinden (depthTest aus + hohe renderOrder).
  body.renderOrder = 3;
  ring.renderOrder = 3;
  if (body.material) body.material.depthTest = false;
  return group;
}
