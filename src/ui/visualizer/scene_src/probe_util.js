// VIZ-13 Schritt 3a-1: minimales Blatt-Modul ohne eigene Abhaengigkeiten.
// Zweck: NUR belegen, dass ein importiertes ES-Modul in der echten
// Produktiv-Ladekonstellation (qwebchannel.js qrc-Script + three_local.js
// klassisch + <script type="module">) ausgefuehrt wird UND Zugriff auf das
// von three_local.js gesetzte globale `window.THREE` hat (Ladereihenfolge-
// Beleg fuer Weg A aus dem Design-Dokument, Abschnitt (b)).
//
// Bewusst KEIN Rendering, KEIN Renderer-Objekt: WebGL ist im offscreen-
// Testlauf (QT_QPA_PLATFORM=offscreen) nicht verfuegbar - der Beleg darf nur
// den THREE-Namespace anfassen (siehe Auftrag, "Belegt darf keinen Renderer
// instanziieren").
export function probeThreeNamespace() {
  const hasThree = (typeof window !== 'undefined') && !!window.THREE;
  const hasVector3 = hasThree && typeof window.THREE.Vector3 === 'function';
  return { hasThree, hasVector3 };
}

// VIZ-13 Schritt 3a-2: Beleg fuer den three-Wrapper (scene_src/three/three.js).
// Instanziiert NUR ein `THREE.Scene` (kein Renderer, kein WebGL noetig) ueber
// den benannten Re-Export `Scene`, um zu belegen, dass ein ES-Modul die
// Klasse ueber den Wrapper statt ueber `window.THREE` direkt bekommt.
import { Scene } from './three/three.js';

export function probeThreeWrapper() {
  const scene = new Scene();
  const isScene = (typeof window !== 'undefined')
    && !!window.THREE
    && scene instanceof window.THREE.Scene;
  return { wrapperSceneOk: isScene };
}

// VIZ-13 Schritt 3a-3: Beleg fuer scene_src/state.js. Prueft nur, dass das
// Modul fehlerfrei importierbar ist und die erwartete Form hat (leere
// State-Objekte, view-Accessor mit lesbaren/schreibbaren Gettern/Settern) -
// KEIN Verhalten aus stage_scene.html wird hier ausgefuehrt, state.js ist in
// 3a-3 noch ungenutzt (siehe Kommentar in state.js). Kein WebGL/Renderer
// noetig (reines Objekt-Modul, keine THREE-Instanzen).
import { fixtures, stageObjects, topDownIcons, settings, view } from './state.js';

export function probeState() {
  const objectsOk = (
    typeof fixtures === 'object' && fixtures !== null &&
    typeof stageObjects === 'object' && stageObjects !== null &&
    typeof topDownIcons === 'object' && topDownIcons !== null &&
    typeof settings === 'object' && settings !== null &&
    typeof settings.gridStep === 'number'
  );
  // view-Accessor: Getter/Setter statt re-exportiertem `let` (Design-Risiko
  // 1) - belegen, dass ein Import-Konsument lesen UND (ueber den Setter)
  // schreiben kann, ohne die Modul-Bindung selbst neu zuzuweisen.
  const modeReadOk = view.mode === '3D';
  view.mode = '2D';
  const modeWriteOk = view.mode === '2D';
  view.mode = '3D'; // zuruecksetzen - Probe darf keinen bleibenden State hinterlassen

  const selectedFidsReadOk = Array.isArray(view.selectedFids) && view.selectedFids.length === 0;
  view.selectedFids = [42];
  const selectedFidsWriteOk = Array.isArray(view.selectedFids) && view.selectedFids[0] === 42;
  view.selectedFids = [];

  const selectedStageIdReadOk = view.selectedStageId === null;
  view.selectedStageId = 'probe';
  const selectedStageIdWriteOk = view.selectedStageId === 'probe';
  view.selectedStageId = null;

  return {
    stateObjectsOk: objectsOk,
    stateViewModeOk: modeReadOk && modeWriteOk,
    stateViewSelectedFidsOk: selectedFidsReadOk && selectedFidsWriteOk,
    stateViewSelectedStageIdOk: selectedStageIdReadOk && selectedStageIdWriteOk,
  };
}
