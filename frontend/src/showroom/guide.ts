import type { CategoryKey, Mode } from "../types";
import { CATEGORY_LAYER } from "./peel";

/**
 * 3D 창 "안내 보기"(DEC-073, DEC-078): 완성 모델 → 부품이 풀림 → 선택한 부품 확대 → 부품 이름. 한 단계씩 Next/Back으로 넘긴다.
 * 차체를 투명하게 만드는 단계는 없다 — 불투명한 차에서 층을 하나씩 걷어내고, 드러난 선택 분류만 주황으로 보인다.
 * 모두 설명용 연출이다 — 이 리콜 차량의 실제 구조나 결함 위치가 아니고, 설명 문장은 부품 이름 외에 만들지 않는다.
 */
export const GUIDE_STEPS = [
  { id: "assembled", title: "Assembled", text: "The finished vehicle as one model." },
  { id: "unfold", title: "Unfold", text: "Parts are taken away layer by layer until the part category of this recall comes into view, highlighted in orange." },
  { id: "zoom", title: "Zoom", text: "The view moves in on the part category." },
  { id: "parts", title: "Parts", text: "The names of the parts that make up this part category." },
] as const;

export const GUIDE_LAST = GUIDE_STEPS.length - 1;
/** 자동 재생에서 단계를 넘기는 간격(ms) */
export const GUIDE_PLAY_MS = 3000;

export interface GuideView {
  mode: Mode;
  /** 선택한 부품 분류를 주황으로 보일지(외관 그대로) */
  highlight: boolean;
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
    mode: "exterior",
    highlight: s >= 1 && category !== null,
    layer: s >= 1 ? reveal : 0,
    zoom: s >= 2,
    markers: s === GUIDE_LAST,
  };
}

/** 안내 보기를 멈추고 직접 조작으로 넘어갈 때 이어받는 화면 상태(모드·층은 따로 넘긴다) */
export interface Held {
  highlight: boolean;
  zoom: boolean;
}
export const NOT_HELD: Held = { highlight: false, zoom: false };
export const holdOf = (view: GuideView): Held => ({ highlight: view.highlight, zoom: view.zoom });

/** 직접 조작이 시작점으로 이어받는 화면(모드·층·이어받은 강조·확대) */
export interface Handoff {
  mode: Mode;
  layer: number;
  held: Held;
}

/**
 * 안내 보기를 멈추고 직접 조작으로 넘어갈 때 이어받을 화면. 안내 중이 아니면(null) 넘길 것이 없다 — 지금 직접 조작 상태를 그대로 둔다.
 * `ModelOverlay`의 `manual()`이 이 값을 `setMode`·`setLayer`·`setHeld`에 그대로 넣는다.
 */
export const handOff = (view: GuideView | null): Handoff | null =>
  view ? { mode: view.mode, layer: view.layer, held: holdOf(view) } : null;

/** 모드 버튼(See-through·Exterior)을 눌렀을 때의 상태 — 고른 모드로 바꾸고 안내에서 이어받은 강조·확대를 비운다 */
export const afterModeButton = (mode: Mode): { mode: Mode; held: Held } => ({ mode, held: NOT_HELD });

/**
 * 지금 3D에 보여 줄 모드·강조·확대. 안내 중이면 단계 화면이고, 직접 조작 중이면 사용자가 고른 모드에 안내에서 이어받은 강조·확대를 더한다
 * (안내 도중 층을 만졌다고 주황과 확대가 사라지지 않게 한다). 결함 투시는 늘 부품 가까이 본다.
 */
export function effectiveLook(view: GuideView | null, mode: Mode, held: Held): { mode: Mode; highlight: boolean; zoom: boolean } {
  return view ? { mode: view.mode, highlight: view.highlight, zoom: view.zoom } : { mode, highlight: held.highlight, zoom: mode === "xray" || held.zoom };
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
