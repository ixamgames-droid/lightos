// VIZ-13 Schritt 3a-1: Entry-Modul des ESM-Machbarkeits-Skeletons.
// Importiert das einzige Blatt-Modul, ruft dessen Probe auf und exponiert
// das Ergebnis als `window.__lightosEsmOk` - das ist der Vertrag, den der
// neue Smoke-Test (tests/test_viz13_esm_smoke.py) per QWebEngineView abfragt.
//
// WICHTIG: dieses Skeleton ist NUR der Build-Strategie-Beleg fuer 3a-1. Der
// eigentliche Modul-Schnitt aus dem Design-Dokument (a) folgt in den
// naechsten 3a-Schritten - hier passiert bewusst noch keine Verhaltens-
// Verschiebung aus stage_scene.html.
import { probeThreeNamespace } from './probe_util.js';

const probe = probeThreeNamespace();
window.__lightosEsmOk = true;
window.__lightosEsmProbe = probe;
