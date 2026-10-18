import type { CategoryKey, Mode } from "../types";

export type LookMaterial = "base" | "hot" | "defect" | "ghost";
export interface Look {
  mode: Mode;
  category: CategoryKey | null;
  activeCats: ReadonlySet<CategoryKey>;
  /** 외관 모드에서도 선택한 분류만 주황으로 보인다(안내 보기, DEC-078) — 차체를 투명하게 하지 않고 걷어낸 자리에 그 부품이 드러난다 */
  highlight: boolean;
}

/**
 * 부품 하나(메시)의 보임 여부와 재질.
 * 외관: 도장·재질 그대로이고 설명용 추정 도형은 숨긴다. 단 highlight이면 선택한 분류의 부품(추정 도형 포함)만 주황으로 보인다.
 * 결함 투시(xray): 고른 부품은 주황, 나머지 결함 부품은 회색, 그 밖은 반투명.
 */
export function meshLook(look: Look, part: { cat: CategoryKey | null | undefined; estimated: boolean }): { visible: boolean; material: LookMaterial } {
  const { mode, category, activeCats, highlight } = look;
  const cat = part.cat ?? null;
  if (mode === "exterior") {
    const lit = highlight && !!category && cat === category;
    return { visible: !part.estimated || lit, material: lit ? "hot" : "base" };
  }
  return {
    visible: !part.estimated || (!!cat && activeCats.has(cat) && (!category || cat === category)),
    material: cat && cat === category ? "hot" : cat && !category && activeCats.has(cat) ? "defect" : "ghost",
  };
}
