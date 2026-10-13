import { BufferGeometry, Float32BufferAttribute, Vector3 } from "three";
import { describe, expect, it } from "vitest";
import { refineGeometry } from "./geometry";

function geometry(positions: number[], indices: number[]) {
  return new BufferGeometry().setAttribute("position", new Float32BufferAttribute(positions, 3)).setIndex(indices);
}
const triangle = () => geometry([0, 0, 0, 1, 0, 0, 0, 1, 0], [0, 1, 2]);
const normalsAt = (g: BufferGeometry, point: number[]) => {
  const p = g.getAttribute("position"), n = g.getAttribute("normal");
  return Array.from({ length: p.count }, (_, i) => i).filter((i) => point.every((v, j) => p.getComponent(i, j) === v)).map((i) => new Vector3().fromBufferAttribute(n, i));
};

describe("모델 표면 정리", () => {
  it("뒤집힌 중복 면·같은 좌표의 중복 면·면적 0인 면을 제거하고 원본은 보존한다", () => {
    const source = geometry([0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0, 0, 2, 0, 0], [0, 1, 2, 2, 1, 0, 3, 1, 2, 0, 1, 4]);
    const result = refineGeometry(source);
    expect(result.index!.count).toBe(3);
    expect(source.index!.count).toBe(12);
    expect(normalsAt(result, [0, 0, 0])[0].toArray()).toEqual([0, 0, 1]);
  });
  it("완만한 접합부의 두 면은 동일한 매끈한 법선을 쓴다", () => {
    const source = geometry([0, 0, 0, 1, 0, 0, 0, 1, 0, 0, -1, .3], [0, 1, 2, 0, 3, 1]);
    const result = refineGeometry(source);
    const normals = normalsAt(result, [0, 0, 0]);
    expect(normals).toHaveLength(1);
    expect(normals[0].y).toBeGreaterThan(0);
    expect(normals[0].z).toBeGreaterThan(.9);
    expect(normals[0].length()).toBeCloseTo(1);
  });
  it("직각으로 접힌 모서리는 둥글게 뭉개지 않는다", () => {
    const result = refineGeometry(geometry([0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0, 1], [0, 1, 2, 0, 3, 1]));
    const normals = normalsAt(result, [0, 0, 0]);
    expect(normals).toHaveLength(2);
    expect(normals[0].dot(normals[1])).toBeCloseTo(0);
  });
  it("공유 집합 안에서만 다른 메시의 중복을 지우고 빈 결과도 처리한다", () => {
    const shared = new Set<string>();
    expect(refineGeometry(triangle(), shared).index!.count).toBe(3);
    expect(refineGeometry(triangle(), shared).index!.count).toBe(0);
    expect(refineGeometry(triangle(), new Set()).index!.count).toBe(3);
  });
  it("비색인 모델도 처리하며 살아 있는 면의 위치를 바꾸지 않는다", () => {
    const source = triangle().toNonIndexed();
    const result = refineGeometry(source);
    source.computeBoundingBox(); result.computeBoundingBox();
    expect(result.boundingBox).toEqual(source.boundingBox);
    expect(result.index!.count).toBe(3);
    expect(source.getAttribute("normal")).toBeUndefined();
  });
});
