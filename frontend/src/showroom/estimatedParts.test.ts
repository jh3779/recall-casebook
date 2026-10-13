import { Box3, BoxGeometry, Mesh, MeshStandardMaterial, Vector3 } from "three";
import { describe, expect, it } from "vitest";
import { createEstimatedParts } from "./estimatedParts";

const material = new MeshStandardMaterial();
function body() {
  const mesh = new Mesh(new BoxGeometry(5.2, 1.7, 2.1), material);
  mesh.position.y = .85;
  mesh.userData.part = { defect: null };
  mesh.updateMatrixWorld(true);
  return mesh;
}

describe("설명용 추정 부품", () => {
  it("없는 엔진·변속기·연료 배관을 차체 범위 안에 배치하고 추정 형상으로 구분한다", () => {
    const exterior = body();
    const bounds = new Box3().setFromObject(exterior);
    const parts = createEstimatedParts([exterior], material);
    const cats = new Set(parts.map(m => m.userData.part.defect));
    for (const cat of ["engine", "transmission", "fuel", "electrical", "airbag"]) expect(cats.has(cat)).toBe(true);
    for (const m of parts) {
      expect(m.userData.estimated).toBe(true);
      expect(m.visible).toBe(false);
      expect(bounds.containsPoint(new Box3().setFromObject(m).getCenter(new Vector3()))).toBe(true);
    }
    expect(exterior.userData.estimated).toBeUndefined();
  });

  it("원본에 연결된 분류는 도형으로 중복 생성하지 않는다", () => {
    const mesh = body(); mesh.userData.part.defect = "engine";
    const parts = createEstimatedParts([mesh], material);
    expect(parts.some(m => m.userData.part.defect === "engine")).toBe(false);
  });
});
