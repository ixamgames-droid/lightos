// FM-13: EINE Quelle fuer die Pixel-Reihenfolge eines Matrix-Panels (JS-Seite).
//
// Ein Panel adressiert seine Pixel ueber die DMX-Reihenfolge — WO sie sitzen,
// sagt das Profil nicht. Die ADJ Dotz Matrix nummeriert im Werkszustand in
// Schlangenlinien (1-2-3-4 / 8-7-6-5 / ...), der Renderer legte sie dagegen
// zeilenweise an: eine horizontale Lauflicht-Figur laeuft am echten Geraet im
// Zickzack, im 3D aber geradeaus.
//
// Die Python-Seite hat dieselbe Regel in `src/core/pixel_order.py`; ein Test
// haelt beide Fassungen gegeneinander, damit sie nicht auseinanderlaufen
// (zwei parallele Regeln sind eine Drift-Quelle, Lehre FM16E).
//
// WICHTIG: Diese Funktion ist die einzige Stelle, die den DMX-Index in eine
// Rasterposition uebersetzt — sowohl das 3D-Panel (`buildMatrixPanel`) als auch
// das 2D-Top-Down-Icon (`addGridCells`) gehen hier durch. Frueher rechneten
// beide dieselbe Formel getrennt aus.

export const PIXEL_ORDERS = ['rowwise', 'serpentine', 'mirrored'];
export const DEFAULT_PIXEL_ORDER = 'rowwise';

export function normalizePixelOrder(value) {
  const v = String(value || '').trim().toLowerCase();
  return PIXEL_ORDERS.indexOf(v) >= 0 ? v : DEFAULT_PIXEL_ORDER;
}

/**
 * ★ VIZ-51: Pixelzahl -> Rasterform {count, cols, rows}.
 *
 * Die Formel stand ZWEIMAL — in `buildMatrixPanel` (3D) und in `addGridCells`
 * (2D-Icon), jeweils mit eigener Klemmung auf 1..256. Die FM-13-Zusage „nur
 * eine Stelle rechnet" galt damit fuer die ZELLE (`pixelCell`), nicht fuer die
 * FORM. Zwei Formeln fuer dieselbe Frage sind genau die Drift-Quelle, gegen die
 * dieses Modul angetreten ist: waere eine der beiden je angefasst worden,
 * haetten 2D und 3D dasselbe Panel verschieden geschnitten.
 */
export function panelGrid(n) {
  const count = Math.max(1, Math.min(256, Math.floor(n || 16)));
  const cols = Math.ceil(Math.sqrt(count));
  const rows = Math.ceil(count / cols);
  return { count, cols, rows };
}

/** DMX-Pixelindex -> {r, c} im sichtbaren Raster. */
export function pixelCell(index, cols, order) {
  const nc = Math.max(1, Math.floor(cols || 1));
  const i = Math.max(0, Math.floor(index || 0));
  const r = Math.floor(i / nc);
  let c = i % nc;
  const o = normalizePixelOrder(order);
  if (o === 'serpentine' && r % 2 === 1) c = nc - 1 - c;
  else if (o === 'mirrored') c = nc - 1 - c;
  return { r, c };
}


// ── ORIENT (2026-08-05): Zwilling zu core/pixel_order.py ────────────────────
//
// `pixelCell` sagt, wie das GERAET nummeriert. Das hier sagt, wie es HAENGT —
// zwei unabhaengige Aussagen. Ein Panel kann in Schlangenlinien zaehlen UND
// hochkant montiert sein.
//
// Bei 90°/270° tauschen Zeilen und Spalten die Rollen; das Raster selbst
// aendert seine Form. Deshalb gibt `placeElement` `rows`/`cols` MIT zurueck —
// sonst rechnet jeder Aufrufer es wieder selbst, und genau daran laufen zwei
// Fassungen auseinander (FM16E-Lehre).

export const ELEMENT_ROTATIONS = [0, 90, 180, 270];

export function normalizeElementRotation(value) {
  let v = Number(value || 0);
  if (!Number.isFinite(v)) return 0;
  v = ((Math.round(v) % 360) + 360) % 360;
  return ELEMENT_ROTATIONS.indexOf(v) >= 0 ? v : 0;
}

/** (r, c) im gedrehten Raster + dessen neue Groesse. */
export function rotateCell(row, col, rows, cols, rotation, flip) {
  let r = Math.floor(row), c = Math.floor(col);
  let nr = Math.max(1, Math.floor(rows || 1));
  let nc = Math.max(1, Math.floor(cols || 1));
  const rot = normalizeElementRotation(rotation);
  if (rot === 90) {
    const r2 = c, c2 = nr - 1 - r;
    r = r2; c = c2; const t = nr; nr = nc; nc = t;
  } else if (rot === 180) {
    r = nr - 1 - r; c = nc - 1 - c;
  } else if (rot === 270) {
    const r2 = nc - 1 - c, c2 = r;
    r = r2; c = c2; const t = nr; nr = nc; nc = t;
  }
  if (flip) c = nc - 1 - c;
  return { r: r, c: c, rows: nr, cols: nc };
}

/** DMX-Index -> endgueltige Position + Rastergroesse.
 *  Reihenfolge wie in Python: erst nummerieren, dann drehen. */
export function placeElement(index, cols, rows, order, rotation, flip) {
  const nc = Math.max(1, Math.floor(cols || 1));
  const nr = Math.max(1, Math.floor(rows || 1));
  const z = pixelCell(index, nc, order);
  return rotateCell(z.r, z.c, nr, nc, rotation, flip);
}
