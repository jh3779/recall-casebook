import { BufferGeometry, Float32BufferAttribute, Mesh, Vector3 } from "three";
import { describe, expect, it } from "vitest";
import { computeHotspots } from "./Showroom";

describe("여러 부품이 한 메시로 묶인 모델", () => {
  it("네 바퀴의 브레이크가 한 메시여도 표시는 차체 가운데가 아닌 앞쪽 브레이크에 놓는다", () => {
    const positions = [];
    for (const x of [-2, 2]) for (const z of [-1, 1]) {
      positions.push(x - .1, .3, z, x + .1, .3, z, x, .5, z);
    }
    const mesh = new Mesh(new BufferGeometry().setAttribute("position", new Float32BufferAttribute(positions, 3)));
    mesh.userData.part = { title: "brakes", defect: "brakes", look: null };
    mesh.updateMatrixWorld(true);
    const point = computeHotspots([mesh]).brakes!.point;
    expect(point.distanceTo(new Vector3(2, .4, -1))).toBeLessThan(.01);
  });
});
