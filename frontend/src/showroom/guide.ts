import type { CategoryKey, Mode } from "../types";
import { CATEGORY_LAYER } from "./peel";

/**
 * 3D 창 "안내 보기"(DEC-073): 완성 모델 → 투시 → 부품이 풀림 → 선택한 부품 확대 → 부품 이름. 한 단계씩 Next/Back으로 넘긴다.
 * 모두 설명용 연출이다 — 이 리콜 차량의 실제 구조나 결함 위치가 아니고, 설명 문장은 부품 이름 외에 만들지 않는다.
 */
export const GUIDE_STEPS = [
  { id: "assembled", title: "Assembled", text: "The finished vehicle as one model." },
  { id: "seethrough", title: "See-through", text: "The model turns transparent. The part category of this recall is highlighted in orange." },
  { id: "unfold", title: "Unfold", text: "Parts are taken away layer by layer until that part category comes into view." },
  { id: "zoom", title: "Zoom", text: "The view moves in on the part category." },
  { id: "parts", title: "Parts", text: "The names of the parts that make up this part category." },
] as const;

export const GUIDE_LAST = GUIDE_STEPS.length - 1;
/** 자동 재생에서 단계를 넘기는 간격(ms) */
export const GUIDE_PLAY_MS = 3000;

export interface GuideView {
  mode: Mode;
  /** 걷어내기 층(0~4) */
  layer: number;
  /** 선택한 부품 분류로 확대할지 */
  zoom: boolean;
  /** 부품 이름 마커를 보일지 */
  markers: boolean;
}

export const clampGuide = (step: number) => (Number.isFinite(step) ? Math.min(GUIDE_LAST, Math.max(0, Math.round(step))) : 0);

/** 단계 → 화면 상태. 분류가 없으면 걷어내지 않는다(안내는 3D에 위치가 있는 분류에서만 쓴다) */
export function guideView(step: number, category: CategoryKey | null): GuideView {
  const s = clampGuide(step);
  const reveal = category ? CATEGORY_LAYER[category] : 0;
  return {
    mode: s === 0 ? "exterior" : "xray",
    layer: s >= 2 ? reveal : 0,
    zoom: s >= 3,
    markers: s === GUIDE_LAST,
  };
}

/** Next/Back가 닿을 수 있는지 */
export const guideMoves = (step: number) => ({ canBack: clampGuide(step) > 0, canNext: clampGuide(step) < GUIDE_LAST });

/** 안내 보기에서 쓰는 부품 이름 마커의 겉모습(이름·추정 여부) */
export interface GuideMarker {
  id: string;
  label: string;
  estimated: boolean;
}

/** 마커의 이름 표기. 설명용 도형은 호버로 읽어도 추정 표시가 따라간다 */
export const markerTitle = (m: GuideMarker) => (m.estimated ? `${m.label} (estimated shape)` : m.label);
