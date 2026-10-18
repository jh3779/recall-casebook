import type { CategoryKey } from "../types";

/**
 * 3D 창 "안내 보기"의 4단계(Parts)에 쓰는 부품 이름(DEC-073). 영어 UI용 이름이고 이름만 보인다 — 설명 문장은 만들지 않는다.
 * 부품 구성은 일반 차량을 단순화한 설명용이며 이 리콜 차량의 실제 구조나 결함 위치가 아니다.
 */

/** 쏘렌토 모델에 실제로 있는 부품(뼈대 이름 → 이름). `sorento_parts.json`에서 분류(defect)가 붙은 뼈대와 같아야 한다(시험이 대조) */
const MODEL_PARTS: Readonly<Record<string, string>> = {
  boot_080: "Tailgate",
  motor_010: "Engine bay",
  seats_09: "Seats",
  steeringwheel_053: "Steering wheel",
  suspension_lf_013: "Suspension",
  suspension_rf_014: "Suspension",
  suspension_lr_012: "Suspension",
  suspension_rr_015: "Suspension",
};

/** 모델에 없어 설명용으로 만든 도형(`estimatedParts.ts`의 한국어 제목 → 이름) */
const ESTIMATED_PARTS: Readonly<Record<string, string>> = {
  "엔진 블록": "Engine block",
  "엔진 상부": "Engine top cover",
  "오일 팬": "Oil pan",
  "엔진 상부 리브": "Engine top rib",
  "벨트 풀리": "Belt pulley",
  "흡기 계통": "Intake system",
  "변속기 하우징": "Transmission housing",
  "전원·배선 대표 영역": "Power and wiring area",
  "연료 공급 배관": "Fuel supply line",
  "연료 계통 연결부": "Fuel system joint",
  "조향 랙": "Steering rack",
  "조향 컬럼": "Steering column",
  "브레이크 디스크": "Brake disc",
  "쇼크 업소버": "Shock absorber",
  "코일 스프링": "Coil spring",
  "운전석 에어백 영역": "Driver air bag area",
  "커튼 에어백 영역": "Curtain air bag area",
  "앞좌석·벨트 영역": "Front seat and belt area",
  "도어 래치": "Door latch",
  "제동등 스위치": "Brake light switch",
};

const ESTIMATED_SUFFIX = " (추정 형상)";

/** 3D에 표시할 수 있는 부품 한 개의 이름. 이름 표에 없으면 null — 모르는 이름을 지어내지 않는다 */
export function displayName(part: { title: string }, estimated: boolean): string | null {
  if (estimated) {
    const base = part.title.endsWith(ESTIMATED_SUFFIX) ? part.title.slice(0, -ESTIMATED_SUFFIX.length) : part.title;
    return ESTIMATED_PARTS[base] ?? null;
  }
  return MODEL_PARTS[part.title.split(" / ")[0]] ?? null;
}

export const MODEL_PART_BONES: readonly string[] = Object.keys(MODEL_PARTS);
export const ESTIMATED_TITLES: readonly string[] = Object.keys(ESTIMATED_PARTS);

/**
 * 분류별 일반적인 구성 이름(모델에 그려져 있지 않을 수 있다). 일반 차량 배치를 단순화한 설명용이고 이 리콜 차량의 실제 구조가 아니다.
 * `estimatedParts.ts`가 만드는 도형의 이름과 같은 범위다(시험이 대조).
 */
export const TYPICAL_COMPONENTS: Readonly<Record<CategoryKey, readonly string[]>> = {
  engine: ["Engine block", "Engine top cover", "Engine top rib", "Oil pan", "Belt pulley", "Intake system"],
  transmission: ["Transmission housing"],
  electrical: ["Power and wiring area"],
  fuel: ["Fuel supply line", "Fuel system joint"],
  steering: ["Steering wheel", "Steering column", "Steering rack"],
  brakes: ["Brake disc"],
  suspension: ["Shock absorber", "Coil spring"],
  airbag: ["Driver air bag area", "Curtain air bag area"],
  seat: ["Seats", "Front seat and belt area"],
  latches: ["Door latch"],
  lighting: ["Brake light switch"],
  tailgate: ["Tailgate"],
  driveline: [],
  other: [],
};
