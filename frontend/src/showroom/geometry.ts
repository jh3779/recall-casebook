import { BufferGeometry, Vector3 } from "three";
import { mergeVertices, toCreasedNormals } from "three/addons/utils/BufferGeometryUtils.js";

/** 정적 차량 메시용. 위치·외곽선은 유지하고 겹친 면과 음영만 정리한다. */
export function refineGeometry(source: BufferGeometry, sharedFaces = new Set<string>()): BufferGeometry {
  const geometry = source.clone();
  const position = source.getAttribute("position");
  const index = source.index;
  const count = index?.count ?? position.count;
  const keys = Array.from({ length: position.count }, (_, i) => `${position.getX(i)},${position.getY(i)},${position.getZ(i)}`);
  const kept: number[] = [];
  const a = new Vector3(), b = new Vector3(), c = new Vector3();
  for (let i = 0; i < count; i += 3) {
    const ia = index ? index.getX(i) : i;
    const ib = index ? index.getX(i + 1) : i + 1;
    const ic = index ? index.getX(i + 2) : i + 2;
    a.fromBufferAttribute(position, ia); b.fromBufferAttribute(position, ib); c.fromBufferAttribute(position, ic);
    if (b.sub(a).cross(c.sub(a)).lengthSq() === 0) continue;
    // 양면 재질이므로 방향만 반대인 같은 면도 하나만 그린다.
    const key = [keys[ia], keys[ib], keys[ic]].sort().join("|");
    if (sharedFaces.has(key)) continue;
    sharedFaces.add(key);
    kept.push(ia, ib, ic);
  }
  geometry.setIndex(kept);
  // 쇼룸은 부품마다 단일 재질을 쓰며, 기존 그룹의 범위는 제거한 면과 맞지 않는다.
  geometry.clearGroups();
  if (!kept.length) return geometry;
  const smooth = toCreasedNormals(geometry, Math.PI / 4);
  const result = mergeVertices(smooth, 1e-5);
  geometry.dispose();
  smooth.dispose();
  return result;
}
