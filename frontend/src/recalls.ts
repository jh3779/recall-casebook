import { CATEGORIES, CATEGORY_KEYS } from "./config";
import type { CategoryKey, ModelKey, Recall, RecallsByModel } from "./types";

/** 그 부품 분류의 리콜. cat이 null이면 3D 형상이 없는(분류가 빈) 리콜 */
export function recallsFor(recalls: RecallsByModel, model: ModelKey, cat: CategoryKey | null): Recall[] {
  return recalls[model].filter((r) => (cat ? r.categories.includes(cat) : !r.categories.length));
}

export interface CategoryRow {
  key: CategoryKey;
  name: string;
  sub: string;
  count: number;
  /** 3D 모델에 위치가 있어 고를 수 있는가 */
  has3d: boolean;
}

/** 패널의 "결함이 기록된 부품" 목록: 0건은 빼고 건수 내림차순 */
export function categoryRows(
  recalls: RecallsByModel,
  model: ModelKey,
  cats3d: ReadonlySet<CategoryKey>,
): CategoryRow[] {
  return CATEGORY_KEYS.map((key) => ({
    key,
    ...CATEGORIES[key],
    count: recallsFor(recalls, model, key).length,
    has3d: cats3d.has(key),
  }))
    .filter((r) => r.count > 0)
    .sort((a, b) => b.count - a.count);
}

export function heroStats(list: Recall[]) {
  const units = list.reduce((s, r) => s + r.potaff, 0);
  return {
    total: list.length,
    in3d: list.filter((r) => r.categories.length).length,
    unitsM: (units / 1e6).toFixed(1),
  };
}

export const otherModel = (m: ModelKey): ModelKey => (m === "silverado" ? "ram" : "silverado");

export const fmtDate = (d: string) => `${d.slice(0, 4)}.${d.slice(4, 6)}.${d.slice(6, 8)}`;

export const yearLabel = (years: number[]) => (years.length > 1 ? `${years[0]}–${years.at(-1)}` : `${years[0]}`);
