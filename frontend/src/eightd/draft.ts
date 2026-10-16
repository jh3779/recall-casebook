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

/** 초안 응답이 검색 응답과 같은 서버 판본(build)에서 나왔는가 — 다르면 서류 꼬리의 출처 표시가 인용의 실제 출처와 어긋난다(리뷰 지적) */
export const sameBuild = (result: Pick<DraftResponse, "build_id" | "bundle_sha256">, search: { build_id: string; bundle_sha256?: string | null } | null): boolean =>
  !search || (result.build_id === search.build_id && (!result.bundle_sha256 || !search.bundle_sha256 || result.bundle_sha256 === search.bundle_sha256));

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
/** 묶음 하나를 본문에 넣을 평문으로 — **도구가 붙인 제목은 본문에 넣지 않는다**(제목은 원문의 의역이라 한정어가 빠질 수 있고, 서류에는 원문 인용만 들어간다. 제목은 화면에서 묶음을 읽는 용도) */
export function groupBlock(group: DraftGroup, cards: readonly Card[]): string {
  const byId = new Map(cards.map((c) => [c.campno, c]));
  return group.items.map((item) => quoteBlock(item, byId.get(item.campno))).join("\n\n");
}
/** 묶음의 이름 — 제목·인용 위치에서 만든다. 같은 순번에 다른 묶음이 와도(다시 묶기) 같은 이름이 되지 않게 한다 */
export function groupId(group: DraftGroup): string {
  const seed = `${group.title}|${group.items.map((i) => `${i.campno}:${i.field}:${i.start}-${i.end}`).join(",")}`;
  let h = 5381;
  for (let i = 0; i < seed.length; i++) h = ((h << 5) + h + seed.charCodeAt(i)) | 0;
  return `draft:g${(h >>> 0).toString(36)}`;
}
const CIRCLED = "①②③④⑤⑥⑦⑧⑨";
export const questionsBlock = (questions: readonly string[]): string =>
  ["[확인 질문 — 도구가 만든 고정 문장]", ...questions.map((q, i) => `${CIRCLED[i] ?? `${i + 1}.`} ${q}`)].join("\n");
