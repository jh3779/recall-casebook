export type ModelKey = "sonata" | "sorento";

export type CategoryKey =
  | "steering"
  | "brakes"
  | "suspension"
  | "driveline"
  | "transmission"
  | "fuel"
  | "seat"
  | "tailgate"
  | "airbag"
  | "engine"
  | "electrical"
  | "lighting"
  | "latches"
  | "other";

export type Mode = "exterior" | "xray";

/** 부품 표면 재질 (data/*_parts.json의 look) */
export type Look = "glass" | "tire" | "rim" | "chrome" | "light" | "paint" | "under" | "tailLight";

/** NHTSA 리콜 한 건 (public/data/hyundai-kia-recalls.json). 문장 칸은 NHTSA 원문 그대로다. */
export interface Recall {
  /** NHTSA 리콜 원본 조회 링크 */
  source?: string;
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
  /** 기록의 부품 분류. 3D 위치 확인 여부는 모델의 PartsMap으로 따로 확인한다. */
  categories: CategoryKey[];
  /** 제조사 부품명. 없으면 빈 문자열 */
  mfr_part: string;
}

export type RecallsByModel = Record<ModelKey, Recall[]>;

/** 3D 모델 메시 이름 → 부품 정보 (public/data/*_parts.json) */
export interface PartInfo {
  title: string;
  defect: CategoryKey | null;
  look: Look | null;
}

export type PartsMap = Record<string, PartInfo>;
