import { Box3, Vector3 } from "three";
import type { Mesh } from "three";
import type { CategoryKey, PartInfo } from "../types";
import { displayName } from "./partNames";
import { boneOfTitle } from "./peel";

/** 3D 위의 부품 이름 마커. point는 조립 상태의 월드 좌표이고, bone이 있으면 걷어낼 때 그 뼈대를 따라간다 */
export interface MarkerDef {
  id: string;
  label: string;
  /** 모델에 없어 설명용으로 만든 도형인지 */
  estimated: boolean;
  point: Vector3;
  bone?: string;
}

export type MarkersByCategory = Partial<Record<CategoryKey, MarkerDef[]>>;

/**
 * 분류별 마커를 만든다. 이름이 같은 부품(코일 스프링 여러 개 등)은 한 번만 보이고, 첫 번째 부품의 중심에 놓는다.
 * 이름 표에 없는 부품은 건너뛴다(이름을 지어내지 않는다).
 */
export function computeMarkers(meshes: readonly Mesh[]): MarkersByCategory {
  const out: MarkersByCategory = {};
  const seen = new Set<string>();
  for (const m of meshes) {
    const part = m.userData.part as PartInfo;
    const cat = part.defect;
    if (!cat) continue;
    const estimated = !!m.userData.estimated;
    const label = displayName(part, estimated);
    if (!label) continue;
    const id = `${cat}:${label}`;
    if (seen.has(id)) continue;
    seen.add(id);
    const point = new Box3().setFromObject(m).getCenter(new Vector3());
    (out[cat] ??= []).push({ id, label, estimated, point, bone: estimated ? undefined : boneOfTitle(part.title) });
  }
  return out;
}
