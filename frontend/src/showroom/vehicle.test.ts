import { Box3, BoxGeometry, Group, Mesh, MeshStandardMaterial, Object3D, SphereGeometry, Vector3 } from "three";
import { describe, expect, it } from "vitest";
import { prepareVehicle } from "./vehicle";

const paint = new MeshStandardMaterial({ color: "blue" });
const materials = { paint, glass: paint, tire: paint, rim: paint, chrome: paint, light: paint, under: paint, tailLight: paint };

describe("다운로드한 차량 모델 준비", () => {
  it("회전된 메시의 넓어진 경계 상자 대신 실제 정점을 바닥에 맞춘다", () => {
    const source = new Group();
    const wheel = new Mesh(new SphereGeometry(1, 24, 16), paint);
    wheel.rotation.x = Math.PI / 4;
    source.add(wheel);
    const result = prepareVehicle(source, "sonata", {}, materials);
    expect(new Box3().setFromObject(result.root, true).min.y).toBeCloseTo(0);
  });

  it("원본 재질을 유지하고 지정한 도장면만 바꾸며 중앙·바닥·길이를 맞춘다", () => {
    const source = new Group();
    const original = new MeshStandardMaterial({ color: "red" });
    const body = new Mesh(new BoxGeometry(2, 1, 4), original);
    body.name = "body";
    body.position.set(100, 30, -200);
    const trim = body.clone(); trim.name = "trim";
    source.add(body, trim);
    const result = prepareVehicle(source, "sonata", { body: { title: "도장", defect: null, look: "paint" } }, materials);
    const bounds = new Box3().setFromObject(result.root);
    expect(bounds.getSize(new Vector3()).x).toBeCloseTo(5.2);
    expect(bounds.getCenter(new Vector3()).x).toBeCloseTo(0);
    expect(bounds.getCenter(new Vector3()).z).toBeCloseTo(0);
    expect(bounds.min.y).toBeCloseTo(0);
    expect(body.material).toBe(paint);
    expect(trim.material).toBe(original);
    expect(trim.userData.part.defect).toBeNull();
  });

  it("쏘렌토의 한 바퀴를 파일 안의 나머지 바퀴 지점에 배치하고 오른쪽은 반전한다", () => {
    const source = new Group();
    const wheel = new Group(); wheel.name = "wheel_lfchild"; wheel.position.set(-1, 1, -2);
    const tire = new Mesh(new BoxGeometry(.2, .8, .8), paint); tire.name = "tire"; tire.position.x = -.1;
    wheel.add(tire); source.add(wheel);
    for (const [name, x, y, z] of [["wheel_lr_027", -1, 1, 2], ["wheel_rr_028", 1, 1, 2], ["wheel_rf_029", 1, 1, -2]] as const) {
      const bone = new Object3D(); bone.name = name; bone.position.set(x, y, z); source.add(bone);
    }
    const result = prepareVehicle(source, "sorento", {}, materials);
    expect(result.meshes).toHaveLength(4);
    const centers = result.meshes.map(m => new Box3().setFromObject(m).getCenter(new Vector3()));
    expect(centers.filter(p => p.x < 0)).toHaveLength(2);
    expect(centers.filter(p => p.x > 0)).toHaveLength(2);
    expect(centers.filter(p => p.z < 0)).toHaveLength(2);
    expect(centers.filter(p => p.z > 0)).toHaveLength(2);
  });
});
