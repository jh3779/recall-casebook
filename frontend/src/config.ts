import type { CategoryKey, ModelKey } from "./types";

export const MODELS: Record<ModelKey, { label: string; maker: string; gen: string; glb: string; parts: string; credit: string; source: string }> = {
  sonata: {
    label: "쏘나타",
    maker: "현대 · Hyundai",
    gen: "2014년형 YF 외관 · 리콜 범위 2011–2014",
    glb: "models/sonata.glb",
    parts: "data/sonata_parts.json",
    credit: "DR1KING100K",
    source: "https://sketchfab.com/3d-models/hyundai-sonata-2014-7a0e4fa5122e4cc1b57d8b9149916558",
  },
  sorento: {
    label: "쏘렌토",
    maker: "기아 · Kia",
    gen: "2022년형 외관 · 리콜 범위 2021–2023",
    glb: "models/sorento.glb",
    parts: "data/sorento_parts.json",
    credit: "MattDoesBlender",
    source: "https://sketchfab.com/3d-models/kia-sorento-47a0016ba8b842c780d79ded8fa0a891",
  },
};

export const MODEL_KEYS = Object.keys(MODELS) as ModelKey[];

export const CATEGORIES: Record<CategoryKey, { name: string; sub: string; en: string }> = {
  steering: { en: "steering", name: "조향 장치", sub: "스티어링 랙 · 컬럼 · 전동 파워스티어링" },
  brakes: { en: "brakes", name: "브레이크", sub: "캘리퍼 · 디스크 · 유압/부스터" },
  suspension: { en: "suspension", name: "서스펜션", sub: "컨트롤 암 · 쇼크 업소버 · 스프링" },
  driveline: { en: "drive shaft", name: "구동축 · 차동장치", sub: "액슬 샤프트 · 드라이브샤프트 · 트랜스퍼 케이스" },
  transmission: { en: "transmission", name: "변속기", sub: "자동변속기 · 변속 레버" },
  fuel: { en: "fuel system", name: "연료 계통", sub: "연료 공급 배관 · 연결부 · 펌프" },
  seat: { en: "seat belt", name: "좌석 · 안전벨트", sub: "안전벨트는 좌석 위치로 표시" },
  tailgate: { en: "tailgate latch", name: "테일게이트", sub: "래치 · 잠금장치" },
  airbag: { en: "air bag", name: "에어백", sub: "운전석 · 커튼 에어백 위치로 표시" },
  engine: { en: "engine", name: "엔진 계통", sub: "엔진 · 냉각 · 윤활 계통" },
  electrical: { en: "electrical system", name: "전기 · 배터리", sub: "배터리 · 배선 · 전기 제어" },
  lighting: { en: "brake light switch", name: "제동등 스위치", sub: "브레이크 페달 부근의 스위치" },
  latches: { en: "door latch", name: "도어 잠금장치", sub: "도어 래치 · 잠금 링크" },
  other: { en: "vehicle equipment", name: "기타 장비", sub: "라벨 · 견인 장치 · 카메라 등" },
};

export const CATEGORY_KEYS = Object.keys(CATEGORIES) as CategoryKey[];

export const PAINTS = [
  { name: "White", color: "#eceef0" },
  { name: "Black", color: "#16181c" },
  { name: "Red", color: "#9e1b22" },
  { name: "Blue", color: "#1f3e66" },
  { name: "Silver", color: "#a9adb3" },
];
