import { Box3, BoxGeometry, BufferGeometry, CatmullRomCurve3, CylinderGeometry, Material, Mesh, SphereGeometry, TorusGeometry, TubeGeometry, Vector3 } from "three";
import type { CategoryKey } from "../types";
import { RoundedBoxGeometry } from "three/addons/geometries/RoundedBoxGeometry.js";

/** 일반적인 전륜구동 차량 배치를 단순화한 설명용 도형. 제조사 도면·결함 위치 근거가 아니다. */
export function createEstimatedParts(original: Mesh[], material: Material): Mesh[] {
  const present = new Set(original.map(m => m.userData.part.defect));
  const bounds = new Box3();
  original.forEach(m => bounds.expandByObject(m, true));
  const size = bounds.getSize(new Vector3());
  const scale = new Vector3(size.x / 5.2, size.y / 1.7, size.z / 2.1);
  const parts: Mesh[] = [];
  function add(cat: CategoryKey, title: string, geometry: BufferGeometry, x: number, y: number, z: number) {
    if (present.has(cat)) { geometry.dispose(); return; }
    const mesh = new Mesh(geometry, material);
    mesh.name = `estimated_${cat}_${parts.length}`;
    mesh.position.set(x, y, z).multiply(scale);
    mesh.scale.copy(scale);
    mesh.userData = { estimated: true, part: { title: `${title} (추정 형상)`, defect: cat, look: null }, base: material };
    mesh.visible = false;
    mesh.updateMatrixWorld(true);
    parts.push(mesh);
  }
  add("engine", "엔진 블록", new RoundedBoxGeometry(.65, .38, .78, 3, .05), 1.3, .69, 0);
  add("engine", "엔진 상부", new RoundedBoxGeometry(.66, .14, .66, 3, .055), 1.3, .98, 0);
  add("engine", "오일 팬", new RoundedBoxGeometry(.47, .14, .55, 3, .05), 1.3, .44, 0);
  for (const z of [-.24, -.08, .08, .24]) {
    add("engine", "엔진 상부 리브", new RoundedBoxGeometry(.48, .035, .045, 2, .015), 1.3, 1.06, z);
  }
  add("engine", "벨트 풀리", new CylinderGeometry(.14, .14, .07, 20).rotateX(Math.PI / 2), 1.4, .7, .44);
  for (const z of [-.27, -.09, .09, .27]) {
    add("engine", "흡기 계통", new CylinderGeometry(.06, .06, .36, 12).rotateZ(Math.PI / 2), 1.65, .88, z);
  }
  add("transmission", "변속기 하우징", new CylinderGeometry(.23, .3, .5, 16).rotateX(Math.PI / 2), 1.15, .58, -.53);
  add("electrical", "전원·배선 대표 영역", new BoxGeometry(.36, .27, .3), 1.28, 1.02, -.66);
  const fuelPath = new CatmullRomCurve3([
    new Vector3(-1.1, .35, .3), new Vector3(0, .32, .3), new Vector3(.9, .4, .3), new Vector3(1.4, .87, .3),
  ]);
  add("fuel", "연료 공급 배관", new TubeGeometry(fuelPath, 24, .035, 8, false), 0, 0, 0);
  add("fuel", "연료 계통 연결부", new CylinderGeometry(.075, .075, .3, 12).rotateZ(Math.PI / 2), 1.3, .87, .3);
  add("steering", "조향 랙", new CylinderGeometry(.045, .045, 1.25, 12).rotateX(Math.PI / 2), 1.4, .45, 0);
  add("steering", "조향 컬럼", new CylinderGeometry(.04, .04, .64, 12).rotateZ(.8), .7, .74, -.53);
  for (const x of [-1.35, 1.55]) for (const z of [-.8, .8]) {
    add("brakes", "브레이크 디스크", new CylinderGeometry(.18, .18, .05, 24).rotateX(Math.PI / 2), x, .43, z);
    add("suspension", "쇼크 업소버", new CylinderGeometry(.045, .045, .48, 12), x, .68, z * .87);
    for (const y of [.58, .65, .72, .79]) {
      add("suspension", "코일 스프링", new TorusGeometry(.09, .018, 8, 16).rotateX(Math.PI / 2), x, y, z * .87);
    }
  }
  add("airbag", "운전석 에어백 영역", new SphereGeometry(.18, 16, 12), .46, 1.01, -.53);
  for (const z of [-.79, .79]) {
    add("airbag", "커튼 에어백 영역", new BoxGeometry(1.5, .09, .08), -.1, 1.42, z);
    add("seat", "앞좌석·벨트 영역", new BoxGeometry(.5, .68, .45), -.05, .85, z * .65);
    for (const x of [-.72, .32]) add("latches", "도어 래치", new BoxGeometry(.09, .16, .06), x, .85, z * 1.13);
  }
  add("lighting", "제동등 스위치", new BoxGeometry(.12, .11, .12), .65, .56, -.55);
  return parts;
}
