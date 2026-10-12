export type ModelKey = "silverado" | "ram";

export type CategoryKey =
  | "steering"
  | "brakes"
  | "suspension"
  | "driveline"
  | "transmission"
  | "fuel"
  | "seat"
  | "tailgate"
  | "airbag";

export type Mode = "exterior" | "xray";

/** 부품 표면 재질 (data/*_parts.json의 look) */
export type Look = "glass" | "tire" | "rim" | "chrome" | "light";

/** NHTSA 리콜 한 건 (public/data/recalls.json). 문장 칸은 NHTSA 원문 그대로다. */
export interface Recall {
  campno: string;
  maker: string;
  /** 접수일 YYYYMMDD */
  received: string;
  /** 대상 대수 */
  potaff: number;
  defect: string;
  consequence: string;
  remedy: string;
  years: number[];
  components: string[];
  /** 3D 모델에서 표시할 부품 분류. 비어 있으면 3D 형상이 없는 부품 */
  categories: CategoryKey[];
  /** 제조사 부품명. 없으면 빈 문자열 */
  mfr_part: string;
}

export type RecallsByModel = Record<ModelKey, Recall[]>;

/** 3D 모델 메시 이름(p2000001 …) → 부품 정보 (public/data/*_parts.json) */
export interface PartInfo {
  title: string;
  defect: CategoryKey | null;
  look: Look | null;
}

export type PartsMap = Record<string, PartInfo>;
