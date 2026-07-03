// VIZ-13 Schritt 3a-2: Wrapper-Modul, das das globale `window.THREE`
// (gesetzt von three_local.js, klassisches UMD-Script r128, geladen VOR
// allen <script type="module">-Modulen - siehe Design-Dokument Abschnitt
// (b) "Weg A") fuer ES-Module importierbar macht.
//
// KEIN Verhalten geaendert: dieses Modul instanziiert nichts, rendert
// nichts, es re-exportiert nur Referenzen auf bereits existierende
// THREE-Klassen/-Konstanten. Faellt `window.THREE` nicht vor dem ersten
// `import` dieses Moduls vorhanden zu sein (falsche Ladereihenfolge), wirft
// die Destrukturierung unten sofort einen TypeError - das ist gewollt
// (Fail-Fast statt stiller `undefined`-Exports).
//
// Named-Export-Menge = exakt die in stage_scene.html genutzte Menge
// (per `grep -oE 'THREE\.[A-Za-z0-9_]+' stage_scene.html | sort -u`
// ermittelt, Stand 3a-2). OBJLoader/ColladaLoader haengen sich (wie die
// Kernklassen) an `window.THREE` - sie werden als eigene klassische
// Scripts VOR three_local.js... nein, NACH three_local.js aber weiterhin
// klassisch (nicht als Modul) geladen (assets/OBJLoader.js,
// assets/ColladaLoader.js, siehe stage_scene.html <head>) und sind daher
// zum Zeitpunkt des ersten Modul-Imports ebenfalls bereits vorhanden.
export default window.THREE;

export const {
  ACESFilmicToneMapping,
  AdditiveBlending,
  AmbientLight,
  Box3,
  BoxGeometry,
  BoxHelper,
  BufferGeometry,
  CanvasTexture,
  CircleGeometry,
  ColladaLoader,
  Color,
  ConeGeometry,
  CylinderGeometry,
  DirectionalLight,
  DoubleSide,
  FogExp2,
  GridHelper,
  Group,
  HemisphereLight,
  Line,
  LineBasicMaterial,
  LineSegments,
  MathUtils,
  Mesh,
  MeshBasicMaterial,
  MeshStandardMaterial,
  OBJLoader,
  Object3D,
  OrthographicCamera,
  PCFSoftShadowMap,
  PerspectiveCamera,
  Plane,
  PlaneGeometry,
  Quaternion,
  Raycaster,
  RingGeometry,
  Scene,
  SpotLight,
  Sprite,
  SpriteMaterial,
  Vector2,
  Vector3,
  WebGLRenderer,
  sRGBEncoding,
} = window.THREE;
