import type { Card, CauseSource } from "../search/types";
import { file573, header } from "./evidenceText";

/** 8D 초안 묶음(DEC-065) — 서버가 선례 원문을 묶은 결과. 인용은 서버가 원문에서 잘라 낸 글자이고 제목만 도구가 붙인 문장이다 */
export type DraftStep = "d2" | "d4";
export interface DraftItem {
  campno: string;
  field: "defect" | "consequence" | "cause";
  quote: string;
  start: number;
  end: number;
  speaker: string;
  dataset?: string | null;
  snapshot_date?: string | null;
  cause_status?: "filled" | "stated_unknown" | null;
  cause_source?: CauseSource | null;
}
export interface DraftGroup { title: string; items: DraftItem[] }
export interface DraftResponse {
  build_id: string;
  bundle_sha256: string | null;
  snapshot_date: string;
  question: string;
  step: DraftStep;
  titles_generated: true;
  model: string | null;
  degraded: "disabled" | "llm_failed" | null;
  reason?: string | null;
  groups: DraftGroup[];
  ungrouped: DraftItem[];
  questions: string[];
  rejected: Record<string, number>;
  relocated?: number; // 공백만 달라 원문 구간으로 되짚은 인용 수 — 싣는 글자는 원문 것
}

const FIELD_LABEL = { defect: "결함", consequence: "결과", cause: "원인 원문" } as const;

/** 인용 하나를 본문에 넣을 평문으로 — 선례 카드를 넣을 때와 같은 머리줄·원문 줄·꼬리줄(말한 주체·출처) */
export function quoteBlock(item: DraftItem, card: Card | undefined): string {
  const lines = [card ? header(card) : `[타사 선례 ${item.campno}]`, `(${FIELD_LABEL[item.field]}) "${item.quote}"`];
  if (item.cause_status === "stated_unknown") lines.push("(미보고·조사 중 표현이 적힌 글이며, 원인을 모른다는 뜻으로 단정하지 않음)");
  lines.push(item.field === "cause" && item.cause_source
    ? `— 말한 주체: ${item.speaker} · ${file573(item.cause_source)}`
    : `— 말한 주체: ${item.speaker} · ${item.dataset} 스냅샷 ${item.snapshot_date}`);
  return lines.join("\n");
}
/** 묶음 하나 — 제목은 도구가 붙인 문장이라 첫 줄에 그렇게 밝힌다 */
export function groupBlock(group: DraftGroup, cards: readonly Card[]): string {
  const byId = new Map(cards.map((c) => [c.campno, c]));
  return [`〈묶음 — 도구가 붙인 제목: ${group.title}〉`, ...group.items.map((item) => quoteBlock(item, byId.get(item.campno)))].join("\n\n");
}
const CIRCLED = "①②③④⑤⑥⑦⑧⑨";
export const questionsBlock = (questions: readonly string[]): string =>
  ["[확인 질문 — 도구가 만든 고정 문장]", ...questions.map((q, i) => `${CIRCLED[i] ?? `${i + 1}.`} ${q}`)].join("\n");
