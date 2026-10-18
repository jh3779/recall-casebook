import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import { RoomEnvironment } from "three/addons/environments/RoomEnvironment.js";
import { prepareVehicle } from "./vehicle";
import { createEstimatedParts } from "./estimatedParts";
import { MODELS, PAINTS } from "../config";
import type { CategoryKey, Mode, ModelKey, PartInfo, PartsMap } from "../types";
import { DEFAULT_PANEL_SHIFT, panelOffset } from "./viewOffset";
import { PEEL_BONES, boneOfTitle, clampPeel, peelFraming, peelShift, smootherstep } from "./peel";

interface Hotspot {
  point: THREE.Vector3;
  box: THREE.Box3;
  /** 이 분류의 메시가 매달린 뼈대 이름. 걷어내면 핫스팟도 이 뼈대를 따라간다(추정 도형은 움직이지 않으므로 없다) */
  bone?: string;
}

/** 걷어내기로 움직이는 뼈대: rest는 조립 상태의 로컬 위치, toLocal·scale은 차량 좌표의 이동량을 부모 뼈대 좌표로 바꾸는 값 */
interface PeelBone {
  name: string;
  bone: THREE.Object3D;
  rest: THREE.Vector3;
  toLocal: THREE.Quaternion;
  scale: number;
}

interface Entry {
  root: THREE.Object3D;
  meshes: THREE.Mesh[];
  hotspots: Partial<Record<CategoryKey, Hotspot>>;
  rig: PeelBone[];
}

const HOME = { pos: new THREE.Vector3(6.8, 2.6, -7.6), target: new THREE.Vector3(0, 0.8, 0) };
const ease = (t: number) => 1 - Math.pow(1 - t, 3);
const partOf = (m: THREE.Mesh) => m.userData.part as PartInfo;

function createMaterials() {
  return {
    paint: new THREE.MeshPhysicalMaterial({
      color: PAINTS[0].color, metalness: 0.35, roughness: 0.38, clearcoat: 0.7, clearcoatRoughness: 0.2,
      side: THREE.DoubleSide, polygonOffset: true, polygonOffsetFactor: -2, polygonOffsetUnits: -2,
    }),
    glass: new THREE.MeshPhysicalMaterial({
      color: 0x1b2530, metalness: 0, roughness: 0.04, transparent: true, opacity: 0.38,
      side: THREE.DoubleSide, depthWrite: false,
    }),
    tire: new THREE.MeshStandardMaterial({ color: 0x141518, roughness: 0.92, metalness: 0, side: THREE.DoubleSide }),
    rim: new THREE.MeshStandardMaterial({ color: 0xc8ccd2, roughness: 0.22, metalness: 1, side: THREE.DoubleSide }),
    chrome: new THREE.MeshStandardMaterial({ color: 0xe4e6e9, roughness: 0.08, metalness: 1, side: THREE.DoubleSide }),
    light: new THREE.MeshPhysicalMaterial({
      color: 0xf4f6f8, roughness: 0.05, metalness: 0.2, emissive: 0xffffff, emissiveIntensity: 0.15,
      side: THREE.DoubleSide,
    }),
    tailLight: new THREE.MeshStandardMaterial({ color: 0x940c18, emissive: 0x6b0610, emissiveIntensity: 0.3, roughness: 0.25, side: THREE.DoubleSide }),
    under: new THREE.MeshStandardMaterial({ color: 0x3b3f46, roughness: 0.7, metalness: 0.35, side: THREE.DoubleSide }),
    ghost: new THREE.MeshBasicMaterial({
      color: 0x9cc3ea, transparent: true, opacity: 0.07, depthWrite: false, side: THREE.DoubleSide,
    }),
    defect: new THREE.MeshStandardMaterial({ color: 0x6e7f94, roughness: 0.5, metalness: 0.4, side: THREE.DoubleSide }),
    hot: new THREE.MeshStandardMaterial({
      color: 0xff6a2b, emissive: 0xff4a10, emissiveIntensity: 0.9, roughness: 0.35, metalness: 0.2,
      side: THREE.DoubleSide,
    }),
  };
}

/**
 * 3D 무대(three.js). 화면 상태는 React가 갖고, 이 클래스는 받은 상태대로 그리기만 한다.
 * 핫스팟 위치는 매 프레임 바뀌므로 React 상태 대신 bindHotspot으로 받은 요소를 직접 옮긴다.
 */
export class Showroom {
  private readonly renderer: THREE.WebGLRenderer;
  private readonly scene = new THREE.Scene();
  private readonly camera = new THREE.PerspectiveCamera(32, innerWidth / innerHeight, 0.05, 200);
  private readonly controls: OrbitControls;
  private readonly floor: THREE.Mesh;
  private readonly ring: THREE.Mesh<THREE.RingGeometry, THREE.MeshBasicMaterial>;
  private readonly mat = createMaterials();
  private readonly loader = new GLTFLoader();
  private readonly loads = new Map<ModelKey, Promise<Entry>>();
  private readonly entries = new Map<ModelKey, Entry>();
  private readonly hotspotEls = new Map<CategoryKey, HTMLElement>();
  private readonly v = new THREE.Vector3();
  private current: Entry | null = null;
  private look: { mode: Mode; category: CategoryKey | null; activeCats: ReadonlySet<CategoryKey> } = {
    mode: "exterior",
    category: null,
    activeCats: new Set(),
  };
  private fly: { p0: THREE.Vector3; t0: THREE.Vector3; p1: THREE.Vector3; t1: THREE.Vector3; start: number; ms: number } | null = null;
  private focusCat: CategoryKey | null = null;
  private peelNow = 0;
  private peelTo = 0;
  private peelAnim: { from: number; to: number; start: number; ms: number } | null = null;
  private raf = 0;
  private disposed = false;
  private readonly reducedMotion = matchMedia("(prefers-reduced-motion: reduce)").matches;

  private readonly container: HTMLElement;

  private readonly panelShift: number;

  constructor(container: HTMLElement, options: { panelShift?: number } = {}) {
    this.panelShift = options.panelShift ?? DEFAULT_PANEL_SHIFT;
    this.container = container;
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
    renderer.setSize(container.clientWidth, container.clientHeight);
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.0;
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.PCFShadowMap; // r186에서 PCFSoftShadowMap이 없어짐
    container.appendChild(renderer.domElement);
    this.renderer = renderer;

    const pmrem = new THREE.PMREMGenerator(renderer);
    this.scene.environment = pmrem.fromScene(new RoomEnvironment(), 0.04).texture;

    const controls = new OrbitControls(this.camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.07;
    controls.minDistance = 1.2;
    controls.maxDistance = 16;
    // 차량 중앙의 수직축만 돈다. 팬·상하 회전으로 축이 흐트러지지 않게 한다.
    controls.enablePan = false;
    const polarAngle = new THREE.Spherical().setFromVector3(HOME.pos.clone().sub(HOME.target)).phi;
    controls.minPolarAngle = polarAngle;
    controls.maxPolarAngle = polarAngle;
    controls.autoRotateSpeed = 0.6;
    // 사용자가 직접 돌리면 자동 회전·카메라 이동을 멈춘다
    controls.addEventListener("start", () => {
      controls.autoRotate = false;
      this.fly = null;
    });
    this.controls = controls;

    const key = new THREE.DirectionalLight(0xffffff, 1.6);
    key.position.set(4, 8, -3);
    key.castShadow = true;
    key.shadow.mapSize.set(2048, 2048);
    Object.assign(key.shadow.camera, { left: -5, right: 5, top: 5, bottom: -5, near: 0.5, far: 20 });
    key.shadow.bias = -0.0003;
    key.shadow.normalBias = 0.03;
    key.shadow.radius = 6;
    this.scene.add(key);
    this.scene.add(new THREE.HemisphereLight(0xffffff, 0xb9c2cc, 0.6));

    this.floor = new THREE.Mesh(
      new THREE.CircleGeometry(9, 64).rotateX(-Math.PI / 2),
      new THREE.ShadowMaterial({ opacity: 0.22 }),
    );
    this.floor.receiveShadow = true;
    this.scene.add(this.floor);

    this.ring = new THREE.Mesh(
      new THREE.RingGeometry(3.6, 3.62, 128).rotateX(-Math.PI / 2),
      new THREE.MeshBasicMaterial({ color: 0x9aa4b2, transparent: true, opacity: 0.35 }),
    );
    this.ring.position.y = 0.002;
    this.scene.add(this.ring);

    this.camera.position.copy(HOME.pos);
    controls.target.copy(HOME.target);
    controls.update();
    addEventListener("resize", this.fitView);
    this.fitView();
    this.raf = requestAnimationFrame(this.tick);
  }

  isLoaded(key: ModelKey) {
    return this.entries.has(key);
  }

  /** 모델을 받아 준비한다(한 번만). 3D 위치가 있는 부품 분류를 돌려준다. */
  async load(key: ModelKey): Promise<ReadonlySet<CategoryKey>> {
    let p = this.loads.get(key);
    if (!p) {
      p = this.loadEntry(key);
      this.loads.set(key, p);
      p.catch(() => this.loads.delete(key)); // 실패하면 다음에 다시 시도
    }
    const entry = await p;
    return new Set(Object.keys(entry.hotspots) as CategoryKey[]);
  }

  /** load()가 끝난 모델을 무대에 올린다. 직전 재질 상태를 바로 입혀 차종을 바꿀 때 외관이 한 프레임 비치지 않게 한다 */
  show(key: ModelKey) {
    if (this.current) this.scene.remove(this.current.root);
    this.current = this.entries.get(key)!;
    this.scene.add(this.current.root);
    this.applyPeel();
    this.applyLook();
  }

  /**
   * 걷어내기 층(0 = 완성 … 4 = 차체 껍데기까지)으로 옮긴다. 모션 감소 설정이면 바로 바뀌고, 아니면 0.7초에 걸쳐 부드럽게 옮긴다.
   * 부품이 나가는 만큼 카메라도 뒤로 빠진다(직접 돌려 둔 방향은 유지한다).
   */
  setPeel(level: number) {
    const to = clampPeel(level);
    const changed = to !== this.peelTo;
    this.peelTo = to;
    if (this.reducedMotion || to === this.peelNow) {
      this.peelAnim = null;
      this.peelNow = to;
      this.applyPeel();
    } else {
      this.peelAnim = { from: this.peelNow, to, start: performance.now(), ms: 700 };
    }
    if (changed) this.aim(true);
  }

  private applyPeel() {
    const entry = this.current;
    if (!entry) return;
    const shift = new THREE.Vector3();
    for (const { name, bone, rest, toLocal, scale } of entry.rig) {
      shift.set(...peelShift(name, this.peelNow)).applyQuaternion(toLocal).divideScalar(scale);
      bone.position.copy(rest).add(shift);
    }
  }

  /** 외관: 도장·재질 그대로 / 결함 투시: 고른 부품은 주황, 나머지 결함 부품은 회색, 그 밖은 반투명 */
  setLook(mode: Mode, category: CategoryKey | null, activeCats: ReadonlySet<CategoryKey>) {
    this.look = { mode, category, activeCats };
    this.applyLook();
  }

  private applyLook() {
    const { mat } = this;
    const { mode, category, activeCats } = this.look;
    this.floor.visible = mode === "exterior";
    this.ring.material.color.set(mode === "xray" ? 0x3d4a5c : 0x9aa4b2);
    for (const m of this.current?.meshes ?? []) {
      const cat = partOf(m).defect;
      m.visible = !m.userData.estimated || (mode === "xray" && !!cat && activeCats.has(cat) && (!category || cat === category));
      if (mode === "exterior") {
        m.material = m.userData.base;
        m.castShadow = true;
      } else {
        m.castShadow = false;
        if (cat && cat === category) m.material = mat.hot;
        else if (cat && !category && activeCats.has(cat)) m.material = mat.defect;
        else m.material = mat.ghost;
      }
      m.renderOrder = m.material === mat.ghost ? 1 : 0;
    }
  }

  /** 부품 쪽으로 시점을 옮겨도 차량 중앙의 회전축은 유지한다. null이면 처음 시점 */
  focus(cat: CategoryKey | null) {
    this.focusCat = cat;
    this.controls.autoRotate = !cat && !this.reducedMotion;
    this.aim(false);
  }

  /** 걷어낸 정도(peelTo)에 맞춰 카메라 위치·시선을 정한다. keepDirection이면 지금 보는 방향을 유지하고 거리·높이만 바꾼다 */
  private aim(keepDirection: boolean) {
    const { scale, lift } = peelFraming(this.peelTo);
    const lookAt = HOME.target.clone().setY(HOME.target.y + lift);
    const cat = this.focusCat;
    const h = cat ? this.current?.hotspots[cat] : undefined;
    if (cat && !h) return;
    let dir: THREE.Vector3;
    let dist: number;
    let center = lookAt;
    if (h && cat) {
      const point = h.point.clone().add(new THREE.Vector3(...(h.bone ? peelShift(h.bone, this.peelTo) : [0, 0, 0])));
      const size = h.box.getSize(new THREE.Vector3()).length();
      dir = new THREE.Vector3(0.55, 0.42, -0.72).normalize();
      if (point.y < 0.6) dir.set(0.5, 0.25, -0.83).normalize();
      dist = Math.max(6.8, size * 2.2);
      center = point;
      if (keepDirection) dir = this.camera.position.clone().sub(this.controls.target).normalize();
      this.flyTo(center.clone().addScaledVector(dir, dist), lookAt);
      return;
    }
    dir = keepDirection ? this.camera.position.clone().sub(this.controls.target).normalize() : HOME.pos.clone().sub(HOME.target).normalize();
    dist = HOME.pos.distanceTo(HOME.target) * scale;
    this.flyTo(lookAt.clone().addScaledVector(dir, dist), lookAt);
  }

  setAutoRotate(on: boolean) {
    this.controls.autoRotate = on && !this.reducedMotion;
  }

  setPaint(color: string) {
    this.mat.paint.color.set(color);
  }

  /** 핫스팟 요소를 등록한다. 매 프레임 화면 좌표로 옮기고, 카메라 뒤면 data-behind를 단다 */
  bindHotspot(cat: CategoryKey, el: HTMLElement | null) {
    if (el) this.hotspotEls.set(cat, el);
    else this.hotspotEls.delete(cat);
  }

  dispose() {
    this.disposed = true;
    cancelAnimationFrame(this.raf);
    removeEventListener("resize", this.fitView);
    this.controls.dispose();
    this.renderer.dispose();
    this.renderer.forceContextLoss();
    this.renderer.domElement.remove();
  }

  // ------------------------------------------------------------ 모델 준비

  private async loadEntry(key: ModelKey): Promise<Entry> {
    const cfg = MODELS[key];
    const [gltf, parts] = await Promise.all([
      this.loader.loadAsync(cfg.glb),
      fetch(cfg.parts).then((r) => {
        if (!r.ok) throw new Error(`${cfg.parts}: HTTP ${r.status}`);
        return r.json() as Promise<PartsMap>;
      }),
    ]);
    if (this.disposed) throw new Error("Showroom disposed");
    const vehicle = prepareVehicle(gltf.scene, key, parts, this.mat);
    // 추정 도형은 정규화한 차체 좌표계에 추가해 원본 GLB와 분리한다.
    const estimated = createEstimatedParts(vehicle.meshes, this.mat.defect);
    const root = new THREE.Group();
    root.add(vehicle.root, ...estimated);
    root.updateMatrixWorld(true);
    const meshes = [...vehicle.meshes, ...estimated];
    for (const m of vehicle.meshes) if ((m as THREE.SkinnedMesh).isSkinnedMesh) m.frustumCulled = false; // 뼈대를 옮기면 원래 경계 밖으로 나간다
    const hotspots = computeHotspots(meshes);
    for (const [cat, bone] of Object.entries(hotspotBonesOf(vehicle.meshes)) as [CategoryKey, string][]) {
      const h = hotspots[cat];
      if (h) h.bone = bone;
    }
    const entry: Entry = { root, meshes, hotspots, rig: buildPeelRig(vehicle.root) };
    this.entries.set(key, entry);
    return entry;
  }

  // ------------------------------------------------------------ 카메라 · 그리기

  private flyTo(pos: THREE.Vector3, target: THREE.Vector3, ms = 1100) {
    if (this.reducedMotion) {
      this.camera.position.copy(pos);
      this.controls.target.copy(target);
      this.fly = null;
      return;
    }
    this.fly = { p0: this.camera.position.clone(), t0: this.controls.target.clone(), p1: pos, t1: target, start: performance.now(), ms };
  }

  // 넓은 화면에서는 오른쪽 패널(380px)만큼 차를 왼쪽으로
  private fitView = () => {
    const width = this.container.clientWidth;
    const height = this.container.clientHeight;
    this.camera.aspect = width / height;
    const dx = panelOffset(width, this.panelShift);
    this.camera.setViewOffset(width, height, dx, 0, width, height);
    this.camera.updateProjectionMatrix();
    this.renderer.setSize(width, height);
  };

  private tick = (now: number) => {
    const { fly, camera, controls } = this;
    if (fly) {
      const t = Math.min(1, (now - fly.start) / fly.ms);
      camera.position.lerpVectors(fly.p0, fly.p1, ease(t));
      controls.target.lerpVectors(fly.t0, fly.t1, ease(t));
      if (t === 1) this.fly = null;
    }
    const anim = this.peelAnim;
    if (anim) {
      const u = Math.min(1, (now - anim.start) / anim.ms);
      this.peelNow = anim.from + (anim.to - anim.from) * smootherstep(u);
      if (u === 1) { this.peelNow = anim.to; this.peelAnim = null; }
      this.applyPeel();
    }
    this.mat.hot.emissiveIntensity = this.reducedMotion ? 0.7 : 0.7 + 0.35 * Math.sin(now / 260);
    controls.update();
    this.renderer.render(this.scene, camera);
    this.updateHotspots();
    this.raf = requestAnimationFrame(this.tick);
  };

  private updateHotspots() {
    const { v } = this;
    for (const [cat, el] of this.hotspotEls) {
      const h = this.current?.hotspots[cat];
      if (!h) continue;
      v.copy(h.point).project(this.camera);
      el.toggleAttribute("data-behind", v.z > 1);
      el.style.left = `${(v.x * 0.5 + 0.5) * this.container.clientWidth}px`;
      el.style.top = `${(-v.y * 0.5 + 0.5) * this.container.clientHeight}px`;
    }
  }
}

/** 걷어낼 뼈대를 모델에서 찾아 조립 상태의 위치와 좌표 변환값을 기록한다. 모델에 없는 뼈대는 건너뛴다 */
function buildPeelRig(root: THREE.Object3D): PeelBone[] {
  root.updateMatrixWorld(true);
  const rig: PeelBone[] = [];
  const q = new THREE.Quaternion(), s = new THREE.Vector3(), p = new THREE.Vector3();
  for (const name of PEEL_BONES) {
    const bone = root.getObjectByName(name);
    if (!bone?.parent) continue;
    bone.parent.matrixWorld.decompose(p, q, s);
    rig.push({ name, bone, rest: bone.position.clone(), toLocal: q.clone().invert(), scale: s.x });
  }
  return rig;
}

function hotspotBonesOf(meshes: THREE.Mesh[]): Partial<Record<CategoryKey, string>> {
  const out: Partial<Record<CategoryKey, string>> = {};
  for (const m of meshes) {
    const cat = partOf(m).defect;
    if (cat && !out[cat]) out[cat] = boneOfTitle(partOf(m).title);
  }
  return out;
}

// 분류별 핫스팟 위치: 운전석 쪽(-z) 부품이 있으면 그쪽, 없으면 전체의 중심
export function computeHotspots(meshes: THREE.Mesh[]): Entry["hotspots"] {
  const byCat: Partial<Record<CategoryKey, THREE.Mesh[]>> = {};
  for (const m of meshes) {
    const cat = partOf(m).defect;
    if (cat) (byCat[cat] ??= []).push(m);
  }
  const out: Entry["hotspots"] = {};
  for (const [cat, list] of Object.entries(byCat) as [CategoryKey, THREE.Mesh[]][]) {
    const all = new THREE.Box3();
    list.forEach((m) => all.expandByObject(m));
    let b = all;
    if (all.max.z - all.min.z > 0.9) {
      // 외관 모델은 네 바퀴/좌석을 한 메시로 묶기도 한다. 실제 정점에서 가까운 쪽을 고른다.
      const near = new THREE.Box3(), front = new THREE.Box3(), vertex = new THREE.Vector3();
      for (const mesh of list) {
        const count = mesh.geometry.getAttribute("position").count;
        for (let i = 0; i < count; i++) {
          mesh.getVertexPosition(i, vertex).applyMatrix4(mesh.matrixWorld);
          if (vertex.z >= 0) continue;
          near.expandByPoint(vertex);
          if (vertex.x > 0) front.expandByPoint(vertex);
        }
      }
      if (!near.isEmpty()) b = near;
      if (all.max.x - all.min.x > 2 && !front.isEmpty()) b = front;
    }
    out[cat] = { point: b.getCenter(new THREE.Vector3()), box: all };
  }
  return out;
}
