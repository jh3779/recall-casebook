import { causeStatus } from "../search/causeStatus";
import { hasCauseText, type Card, type ProductionCheckItem, type SearchResponse } from "../search/types";

/** 8D에서 선례 원문을 참고로 보여 주는 단계 — D7은 검색 결과 표(resultsBlock)로 따로 다룬다 */
export type EvidenceStep = "2" | "3" | "4" | "5";

export const isoDate = (d: string) => `${d.slice(0, 4)}-${d.slice(4, 6)}-${d.slice(6, 8)}`;
export const header = (card: Card) => `[타사 선례 ${card.campno} · ${card.maker} · 접수 ${isoDate(card.received_date)}]`;
const flatSource = (card: Card) => `— 말한 주체: ${card.source.speaker} · ${card.source.dataset} 스냅샷 ${card.source.snapshot_date}`;
export const file573 = (s: { file: string; submission_date: string; pdf_sha256: string }) => `출처: ${s.file} · 제출일 ${isoDate(s.submission_date)} · sha256 ${s.pdf_sha256.slice(0, 12)}…`;
const productionItem = (card: Card) => card.checklist.find((item): item is ProductionCheckItem => item.item === "production_period");
export const supplierName = (card: Card) => card.checklist.find((item) => item.item === "supplier")?.evidence[0]?.text;

/**
 * 한 선례가 해당 단계에서 본문에 들어갈 글(평문). 줄 구성: 머리줄 · 원문 줄(따옴표로 감쌈, 글자는 바꾸지 않는다) · 꼬리줄(말한 주체·출처).
 * 그 단계에 넣을 원문이 없으면 null — 없는 말을 채우지 않는다(AGENTS.md 서비스 원칙 3).
 */
export function evidenceBlock(step: EvidenceStep, card: Card): string | null {
  if (step === "2") return [header(card), `(결함) "${card.defect}"`, `(결과) "${card.consequence}"`, flatSource(card)].join("\n");
  if (step === "5") return [header(card), `(시정) "${card.remedy}"`, flatSource(card)].join("\n");
  if (step === "3") {
    const item = productionItem(card);
    if (!item) return null;
    const lines = [header(card), ...item.evidence.map((e) => e.text)];
    if (item.omitted > 0) lines.push(`(싣지 못한 블록 ${item.omitted}개)`);
    if (item.unread > 0) lines.push(`(날짜까지 읽히지 않아 싣지 않은 블록 ${item.unread}개)`);
    const supplier = supplierName(card);
    if (supplier) lines.push(`Supplier (Part 573): ${supplier}`);
    lines.push(`— ${file573(item.source)}`);
    return lines.join("\n");
  }
  const cause = card.cause;
  if (!hasCauseText(cause)) return null;
  const lines = [header(card), `(원인 원문) "${cause.text}"`];
  if (cause.status === "stated_unknown") lines.push("(미보고·조사 중 표현이 적힌 글이며, 원인을 모른다는 뜻으로 단정하지 않음)");
  lines.push(`— 말한 주체: ${cause.speaker} · ${file573(cause.source)}`);
  return lines.join("\n");
}

/** 본문에 넣을 글이 없을 때 화면에 보이는 사유 — 서버가 준 원인 상태 문장을 그대로 쓴다 */
export function missingReason(step: "3" | "4", card: Card): string {
  const { message } = causeStatus(card.cause);
  return step === "3" ? `생산 기간 정보 없음 — ${message}` : `원인 원문 없음 — ${message}`;
}

/** D7 참고: 같은 질문의 검색 결과 전부를 줄 단위 표로 */
export function resultsBlock(response: SearchResponse): string {
  const customers = new Set(response.customer_precedents.map((c) => c.campno));
  const all = [...response.customer_precedents, ...response.precedents];
  const rows = all.map((c) => `${c.campno} | ${c.maker} | ${isoDate(c.received_date)} | ${customers.has(c.campno) ? "고객사" : "다른 회사"} | 573 ${c.cause.status === "no_573_report" ? "범위 밖" : "있음"} | ${supplierName(c) ?? "-"}`);
  return [`[참고 · 같은 부품 검색 결과 ${all.length}건 · 공급사는 원문 그대로]`, ...rows].join("\n");
}
