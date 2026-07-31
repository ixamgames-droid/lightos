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
