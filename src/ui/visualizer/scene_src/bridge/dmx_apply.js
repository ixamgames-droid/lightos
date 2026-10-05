// VIZ-71: EINE Stelle, an der DMX-Werte in der Szene ankommen — fuer den Push
// (`runJavaScript` aus visualizer/dmx_push.py) und fuer den Poll-Rueckfall
// (`pollControl` -> `s.dmx`).
//
// Sequenznummern: der Service nummeriert jeden gebauten Tick; jeder Eintrag
// traegt die Nummer des Ticks, aus dem er stammt. Ein Eintrag, der AELTER ist
// als der zuletzt angewandte derselben fid, wird verworfen — Push und Poll
// reisen ueber verschiedene IPC-Wege und koennen sich ueberholen. Eintraege
// ohne Nummer (Alt-Aufrufer, Tests) gelten immer.
//
// `??` statt `||`: `d.pan||128` machte aus Pan 0 (ganz links!) die Mitte 128.
import { fixtures } from '../state.js';
import { updateFixture } from '../fixtures/fixtures.js';
import { cachedSeq, noteShowGen, rememberDmx } from '../fixtures/dmx_cache.js';

export function applyDmxEntry(d) {
  updateFixture(d.fid, d.r ?? 0, d.g ?? 0, d.b ?? 0, d.intensity ?? 0,
                d.pan ?? 128, d.tilt ?? 128, d.heads || null);
}

// arr: Payload-Liste; seq: Zahl (gilt fuer alle), Liste (je Eintrag) oder
// nichts; gen: Show-Generation des Batches (s. dmx_cache.js) oder nichts.
// Rueckgabe: Zahl der Eintraege, die ein vorhandenes Geraet erreicht haben
// (unbekannte fids landen nur im Cache). Python liest die ZAHL — ein Array
// kaeme in PySide 6.11 als '' an.
export function applyDmx(arr, seq, gen) {
  if (!Array.isArray(arr)) return 0;
  // Neuere Generation: Cache der alten Show leeren, BEVOR dieser Batch ihn
  // fuellt. Aeltere: verspaeteter Batch der alten Show -> verwerfen (0 ist
  // eine gueltige Antwort, kein "nicht bereit").
  if (!noteShowGen(gen)) return 0;
  let n = 0;
  for (let i = 0; i < arr.length; i++) {
    const d = arr[i];
    if (!d || d.fid === undefined || d.fid === null) continue;
    let s = Array.isArray(seq) ? seq[i] : seq;
    if (s === undefined) s = null;
    const alt = cachedSeq(d.fid);
    if (s !== null && alt !== null && s < alt) continue;   // ueberholt
    rememberDmx(d.fid, (s !== null) ? s : alt, d);
    if (fixtures[d.fid]) {
      try { applyDmxEntry(d); n += 1; } catch (e) { /* ein Geraet bremst nie den Batch */ }
    }
  }
  return n;
}
