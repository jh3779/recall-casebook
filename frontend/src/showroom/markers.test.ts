import { BoxGeometry, Mesh, MeshStandardMaterial } from "three";
import { describe, expect, it } from "vitest";
import { createEstimatedParts } from "./estimatedParts";
import { computeMarkers } from "./markers";
import { TYPICAL_COMPONENTS, displayName } from "./partNames";

const material = new MeshStandardMaterial();

function body(defect: string | null = null) {
  const mesh = new Mesh(new BoxGeometry(5.2, 1.7, 2.1), material);
  mesh.position.y = 0.85;
  mesh.userData.part = { title: "bodyshell_030 / xromat", defect, look: null };
  mesh.updateMatrixWorld(true);
  return mesh;
}
function real(title: string, defect: string, x: number) {
  const mesh = new Mesh(new BoxGeometry(0.2, 0.2, 0.2), material);
  mesh.position.set(x, 1, 0);
  mesh.userData.part = { title, defect, look: null };
  mesh.updateMatrixWorld(true);
  return mesh;
}

describe("부품 이름 마커", () => {
  it("설명용 도형을 모두 만들었을 때 각 도형의 이름이 이름 표에 있다(영어 이름이 빠진 도형이 없다)", () => {
    const parts = createEstimatedParts([body()], material);
    expect(parts.length).toBeGreaterThan(20);
    for (const m of parts) expect(displayName(m.userData.part, true), m.userData.part.title).not.toBeNull();
  });
  it("설명용 도형이 만드는 이름은 모두 분류별 일반 구성 목록에 들어 있다", () => {
    const parts = createEstimatedParts([body()], material);
    for (const m of parts) {
      const name = displayName(m.userData.part, true)!;
      expect(TYPICAL_COMPONENTS[m.userData.part.defect as keyof typeof TYPICAL_COMPONENTS], `${m.userData.part.defect}: ${name}`).toContain(name);
    }
  });
  it("같은 이름의 부품은 한 번만 마커로 만들고 첫 부품의 중심에 놓는다", () => {
    const meshes = [real("suspension_lf_013 / a", "suspension", -1), real("suspension_rf_014 / a", "suspension", 1), real("suspension_lr_012 / a", "suspension", 2)];
    const markers = computeMarkers(meshes);
    expect(markers.suspension).toHaveLength(1);
    expect(markers.suspension![0]).toMatchObject({ id: "suspension:Suspension", label: "Suspension", estimated: false, bone: "suspension_lf_013" });
    expect(markers.suspension![0].point.x).toBeCloseTo(-1, 6);
  });
  it("이름 표에 없는 부품·분류가 없는 부품은 마커를 만들지 않는다(이름을 지어내지 않는다)", () => {
    const shell = body();
    const unknown = real("wheel_lf_024 / x", "suspension", 0);
    const markers = computeMarkers([shell, unknown]);
    expect(markers).toEqual({});
  });
  it("실제 부품은 뼈대 이름을 달고 설명용 도형은 뼈대 없이 estimated로 표시한다", () => {
    const estimated = createEstimatedParts([body()], material);
    const markers = computeMarkers([real("seats_09 / x", "seat", 0), ...estimated]);
    expect(markers.seat!.find((m) => m.label === "Seats")).toMatchObject({ estimated: false, bone: "seats_09" });
    expect(markers.transmission![0]).toMatchObject({ label: "Transmission housing", estimated: true });
    expect(markers.transmission![0].bone).toBeUndefined();
    expect(new Set(Object.values(markers).flat().map((m) => m!.id)).size).toBe(Object.values(markers).flat().length); // id는 유일하다
  });
});
