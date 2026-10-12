import type { CategoryKey, ModelKey } from "./types";

export const MODELS: Record<ModelKey, { label: string; maker: string; gen: string; glb: string; parts: string }> = {
  silverado: {
    label: "Silverado 1500",
    maker: "Chevrolet · GM",
    gen: "2014–2018 세대",
    glb: "models/silverado.glb",
    parts: "data/silverado_parts.json",
  },
  ram: {
    label: "Ram 1500",
    maker: "Ram · FCA(Stellantis)",
    gen: "2013–2018 세대",
    glb: "models/ram.glb",
    parts: "data/ram_parts.json",
  },
};

export const MODEL_KEYS = Object.keys(MODELS) as ModelKey[];

export const CATEGORIES: Record<CategoryKey, { name: string; sub: string; en: string }> = {
  steering: { en: "steering", name: "조향 장치", sub: "스티어링 랙 · 컬럼 · 전동 파워스티어링" },
  brakes: { en: "brakes", name: "브레이크", sub: "캘리퍼 · 디스크 · 유압/부스터" },
  suspension: { en: "suspension", name: "서스펜션", sub: "컨트롤 암 · 쇼크 업소버 · 스프링" },
  driveline: { en: "drive shaft", name: "구동축 · 차동장치", sub: "액슬 샤프트 · 드라이브샤프트 · 트랜스퍼 케이스" },
  transmission: { en: "transmission", name: "변속기", sub: "자동변속기 · 변속 레버" },
  fuel: { en: "fuel system", name: "연료 계통", sub: "연료탱크 · 연료펌프" },
  seat: { en: "seat belt", name: "좌석 · 안전벨트", sub: "안전벨트는 좌석 위치로 표시" },
  tailgate: { en: "tailgate latch", name: "테일게이트", sub: "래치 · 잠금장치" },
  airbag: { en: "air bag", name: "에어백", sub: "운전석 · 커튼 에어백 위치로 표시" },
};

export const CATEGORY_KEYS = Object.keys(CATEGORIES) as CategoryKey[];

export const PAINTS = [
  { name: "Summit White", color: "#eceef0" },
  { name: "Black", color: "#16181c" },
  { name: "Red", color: "#9e1b22" },
  { name: "Blue", color: "#1f3e66" },
  { name: "Silver", color: "#a9adb3" },
];
