// LAS-32 (Slice S1), Stil „c": SICHT DES LASERS als kleines Fenster im 3D.
//
// Ein Bild-im-Bild aus dem Austrittsfenster heraus: das Maximalfeld als
// Rechteck, die Sperrzonen als dunkle Flecken darin — so, wie man eine Blende
// einstellen wuerde. NUR ANZEIGE: das Fenster faengt keine Eingabe
// (pointer-events: none) und schaltet nichts.
//
// Gezeichnet wird mit 2D-Canvas, nicht mit einer zweiten 3D-Kamera: die
// Bildebene ist die Tangens-Ebene des Lasers (u = rechts, v = oben), in der
// das Feld exakt ein Rechteck ist. Alle Punkte kommen schon in
// Laser-Koordinaten an (sperrzonen.js), hier wird nur projiziert.
import { schneide, blick } from './sperrzonen_geo.js';

const BREITE = 420, HOEHE = 356;
const RAND = 10, KOPF = 26, FUSS = 22;
const NAH = 0.05;

let _kasten = null, _leinwand = null, _muster = null, _dpr = 1;
let _letzte = null;

function anlegen() {
  if (_kasten) return;
  _kasten = document.createElement('div');
  _kasten.id = 'sperrzonen-lasersicht';
  _kasten.style.cssText = [
    'position:absolute', 'left:12px', 'bottom:40px', 'z-index:6',
    'pointer-events:none', 'display:none',
    'background:rgba(10,12,18,0.90)', 'border:1px solid rgba(255,176,0,0.75)',
    'border-radius:6px', 'box-shadow:0 2px 14px rgba(0,0,0,0.6)',
  ].join(';');
  _leinwand = document.createElement('canvas');
  const dpr = Math.max(1, Math.min(3, window.devicePixelRatio || 1));
  _leinwand.width = Math.round(BREITE * dpr);
  _leinwand.height = Math.round(HOEHE * dpr);
  _leinwand.style.cssText = `display:block;width:${BREITE}px;height:${HOEHE}px`;
  _dpr = dpr;
  _kasten.appendChild(_leinwand);
  document.body.appendChild(_kasten);
}

function schraffur(g) {
  if (_muster) return _muster;
  const c = document.createElement('canvas');
  c.width = c.height = 8;
  const m = c.getContext('2d');
  m.fillStyle = 'rgba(255,40,40,0.55)';
  m.fillRect(0, 0, 8, 8);
  m.strokeStyle = 'rgba(255,225,225,0.95)';
  m.lineWidth = 2;
  for (const d of [-8, 0, 8]) {
    m.beginPath(); m.moveTo(d, 8); m.lineTo(d + 8, 0); m.stroke();
  }
  _muster = g.createPattern(c, 'repeat');
  return _muster;
}

function vorn(polygon) {
  return schneide(polygon, p => NAH - p[2]);
}

/**
 * @param {?object} d  null = ausblenden. Sonst
 *   { titel, tan:{l,r,o,u}, tanOhne:{l,r,o,u}, winkel:{links,rechts,oben,unten,zuschlag},
 *     zonen:[{name, erreicht, flaechen:[polygon]}], linien:[[a,b]], koerper:[[a,b]] }
 *   — alle Punkte in Laser-Koordinaten.
 */
export function zeichneLasersicht(d) {
  _letzte = d ? { sichtbar: true, titel: d.titel, zonen: d.zonen.map(z => z.name),
                  erreicht: d.zonen.filter(z => z.erreicht).map(z => z.name) }
              : { sichtbar: false };
  if (!d) {
    if (_kasten) _kasten.style.display = 'none';
    return;
  }
  anlegen();
  _kasten.style.display = 'block';
  const g = _leinwand.getContext('2d');
  const dpr = _dpr;
  g.setTransform(dpr, 0, 0, dpr, 0, 0);
  g.clearRect(0, 0, BREITE, HOEHE);

  const t = d.tan;
  const px = RAND, py = KOPF, pw = BREITE - 2 * RAND, ph = HOEHE - KOPF - FUSS;
  // Massstab: Feld mit gut einem Drittel Luft rundherum.
  const fb = t.l + t.r, fh = t.o + t.u;
  const k = Math.min(pw / (fb * 1.75), ph / (fh * 1.75));
  const mu = (t.r - t.l) / 2, mv = (t.o - t.u) / 2;       // Feldmitte
  const X = u => px + pw / 2 + (u - mu) * k;
  const Y = v => py + ph / 2 - (v - mv) * k;
  const weg = pts => {
    g.beginPath();
    pts.forEach((p, i) => { const b = blick(p); if (i) g.lineTo(X(b[0]), Y(b[1])); else g.moveTo(X(b[0]), Y(b[1])); });
    g.closePath();
  };

  // Kopf
  g.font = 'bold 12px sans-serif';
  g.textBaseline = 'middle';
  g.textAlign = 'left';
  g.fillStyle = '#ffb000';
  g.fillText(d.titel, RAND, KOPF / 2 + 1);
  const erreicht = d.zonen.filter(z => z.erreicht).map(z => z.name);
  g.textAlign = 'right';
  g.font = '12px sans-serif';
  if (erreicht.length) {
    g.fillStyle = '#ff6060';
    g.fillText('im Feld: ' + erreicht.join(', '), BREITE - RAND, KOPF / 2 + 1, BREITE - 150);
  } else {
    g.fillStyle = '#9fb0a0';
    g.fillText('keine Zone im Feld', BREITE - RAND, KOPF / 2 + 1);
  }

  g.save();
  g.beginPath();
  g.rect(px, py, pw, ph);
  g.clip();
  g.fillStyle = '#05070b';
  g.fillRect(px, py, pw, ph);

  // Boden-Raster und Buehnenkoerper: nur zur Orientierung.
  const strecken = (liste, farbe, breite) => {
    g.strokeStyle = farbe;
    g.lineWidth = breite;
    g.beginPath();
    for (const s of liste) {
      const v = vorn(s);
      if (v.length < 2) continue;
      const a = blick(v[0]), b = blick(v[1]);
      g.moveTo(X(a[0]), Y(a[1]));
      g.lineTo(X(b[0]), Y(b[1]));
    }
    g.stroke();
  };
  strecken(d.linien || [], 'rgba(150,170,210,0.16)', 1);
  strecken(d.koerper || [], 'rgba(190,200,220,0.42)', 1);

  // Zonen: dunkle Flecken …
  const feldWeg = () => {
    g.beginPath();
    g.rect(X(-t.l), Y(t.o), (t.l + t.r) * k, (t.o + t.u) * k);
  };
  const schilder = [];
  for (const z of d.zonen) {
    let su = 0, sv = 0, n = 0;
    const sichtbar = z.flaechen.map(vorn).filter(p => p.length >= 3);
    g.fillStyle = 'rgba(120,10,10,0.50)';
    g.strokeStyle = 'rgba(255,90,90,0.9)';
    g.lineWidth = 1;
    for (const p of sichtbar) {
      weg(p); g.fill(); g.stroke();
      for (const q of p) {
        const b = blick(q);
        su += Math.max(mu - pw / 2 / k, Math.min(mu + pw / 2 / k, b[0]));
        sv += Math.max(mv - ph / 2 / k, Math.min(mv + ph / 2 / k, b[1]));
        n++;
      }
    }
    // … und der Teil IM Feld kraeftig schraffiert.
    if (sichtbar.length) {
      g.save();
      feldWeg(); g.clip();
      g.fillStyle = schraffur(g);
      for (const p of sichtbar) { weg(p); g.fill(); }
      g.restore();
    }
    if (n) schilder.push({ name: z.name, x: X(su / n), y: Y(sv / n), erreicht: z.erreicht });
  }

  // Feld: aussen = mit Zuschlag (damit wird gerechnet), innen = Randwinkel.
  const o = d.tanOhne;
  g.setLineDash([5, 4]);
  g.strokeStyle = 'rgba(255,176,0,0.75)';
  g.lineWidth = 1;
  g.strokeRect(X(-o.l), Y(o.o), (o.l + o.r) * k, (o.o + o.u) * k);
  g.setLineDash([]);
  g.strokeStyle = '#ffb000';
  g.lineWidth = 2;
  g.strokeRect(X(-t.l), Y(t.o), (t.l + t.r) * k, (t.o + t.u) * k);
  // Achse
  g.strokeStyle = 'rgba(255,255,255,0.75)';
  g.lineWidth = 1;
  g.beginPath();
  g.moveTo(X(0) - 6, Y(0)); g.lineTo(X(0) + 6, Y(0));
  g.moveTo(X(0), Y(0) - 6); g.lineTo(X(0), Y(0) + 6);
  g.stroke();

  // Randwinkel an den vier Seiten
  const w = d.winkel || {};
  g.font = '10px sans-serif';
  g.fillStyle = 'rgba(255,200,90,0.95)';
  const grad = v => (Math.round(Number(v) * 10) / 10) + '°';
  g.textBaseline = 'middle';
  const beschrifte = (text, x, y, ausrichtung) => {
    const b = g.measureText(text).width + 6;
    const x0 = ausrichtung === 'center' ? x - b / 2 : (ausrichtung === 'right' ? x - b + 3 : x - 3);
    g.fillStyle = 'rgba(5,7,11,0.78)';
    g.fillRect(x0, y - 7, b, 14);
    g.fillStyle = 'rgba(255,200,90,0.98)';
    g.textAlign = ausrichtung;
    g.fillText(text, x, y + 1);
  };
  beschrifte('oben ' + grad(w.oben), X(mu), Y(t.o) - 10, 'center');
  beschrifte('unten ' + grad(w.unten), X(mu), Y(-t.u) + 11, 'center');
  beschrifte('links ' + grad(w.links), X(-t.l) - 6, Y(mv), 'right');
  beschrifte('rechts ' + grad(w.rechts), X(t.r) + 6, Y(mv), 'left');

  // Zonen-Namen
  g.font = 'bold 11px sans-serif';
  g.textAlign = 'center';
  g.textBaseline = 'middle';
  for (const s of schilder) {
    const b = g.measureText(s.name).width + 10;
    const x = Math.max(px + b / 2 + 2, Math.min(px + pw - b / 2 - 2, s.x));
    const y = Math.max(py + 10, Math.min(py + ph - 10, s.y));
    g.fillStyle = 'rgba(70,0,0,0.92)';
    g.fillRect(x - b / 2, y - 8, b, 16);
    g.strokeStyle = '#ff5050';
    g.lineWidth = 1;
    g.strokeRect(x - b / 2 + 0.5, y - 7.5, b - 1, 15);
    g.fillStyle = '#ffffff';
    g.fillText(s.name, x, y + 1);
  }
  g.restore();
  g.strokeStyle = 'rgba(255,255,255,0.18)';
  g.lineWidth = 1;
  g.strokeRect(px + 0.5, py + 0.5, pw - 1, ph - 1);

  // Fuss
  g.font = '10px sans-serif';
  g.textBaseline = 'middle';
  g.textAlign = 'left';
  g.fillStyle = 'rgba(200,205,215,0.85)';
  g.fillText('gelb: Feld + ' + grad(w.zuschlag) + ' Zuschlag · gestrichelt: Randwinkel',
             RAND, HOEHE - FUSS / 2);
  g.textAlign = 'right';
  g.fillStyle = '#ffcc00';
  g.fillText('Nur Anzeige', BREITE - RAND, HOEHE - FUSS / 2);
}

/** Test-/Diagnose-Seam. */
export function lasersichtInfo() {
  const sichtbar = !!(_kasten && _kasten.style.display !== 'none');
  return Object.assign({}, _letzte || { sichtbar: false }, {
    sichtbar,
    faengtEingabe: !!(_kasten && _kasten.style.pointerEvents !== 'none'),
    breite: _leinwand ? _leinwand.width : 0,
  });
}
