import type { Card, CheckItem } from "../search/types";

/** 서버 확인 항목 6종 중 케이스북이 따로 그리는 둘(생산 기간·공급사) 말고 나머지 — 근거 원문을 항목 이름·칸 이름과 함께 그대로 보인다(PRD FR-7) */
export const plainItems = (card: Card): Exclude<CheckItem, { item: "production_period" }>[] =>
  card.checklist.filter((item): item is Exclude<CheckItem, { item: "production_period" }> => item.item !== "production_period" && item.item !== "supplier");

const ITEM_LABELS: Record<string, string> = { same_part: "Same part", failure_mode: "Failure mode", remedy: "Remedy", cause_speaker: "Who said the cause" };
const FIELD_LABELS: Record<string, string> = { components: "Components", defect: "Defect", consequence: "Consequence", remedy: "Remedy", "cause.speaker": "Cause said by" };
export const itemLabel = (item: string) => (Object.hasOwn(ITEM_LABELS, item) ? ITEM_LABELS[item] : item);
export const fieldLabel = (field: string) => (Object.hasOwn(FIELD_LABELS, field) ? FIELD_LABELS[field] : field);
