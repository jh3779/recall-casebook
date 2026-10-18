import { causeStatus } from "../search/causeStatus";
import { hasCauseText, type Card } from "../search/types";

export const isoDate = (d: string) => `${d.slice(0, 4)}-${d.slice(4, 6)}-${d.slice(6, 8)}`;
export const header = (card: Card) => `[타사 선례 ${card.campno} · ${card.maker} · 접수 ${isoDate(card.received_date)}]`;
export const file573 = (s: { file: string; submission_date: string; pdf_sha256: string }) => `출처: ${s.file} · 제출일 ${isoDate(s.submission_date)} · sha256 ${s.pdf_sha256.slice(0, 12)}…`;
/**
 * 한 선례가 D4에 들어갈 글(평문) — 선례 내용은 D4(타사 원인 원문)에만 넣는다(DEC-076). 줄 구성: 머리줄 · 원문 줄(따옴표로 감쌈, 글자는 바꾸지 않는다) · 꼬리줄(말한 주체·출처).
 * 그 단계에 넣을 원문이 없으면 null — 없는 말을 채우지 않는다(AGENTS.md 서비스 원칙 3).
 */
export function evidenceBlock(card: Card): string | null {
  const cause = card.cause;
  if (!hasCauseText(cause)) return null;
  const lines = [header(card), `(원인 원문) "${cause.text}"`];
  if (cause.status === "stated_unknown") lines.push("(미보고·조사 중 표현이 적힌 글이며, 원인을 모른다는 뜻으로 단정하지 않음)");
  lines.push(`— 말한 주체: ${cause.speaker} · ${file573(cause.source)}`);
  return lines.join("\n");
}

/** 본문에 넣을 글이 없을 때 화면에 보이는 사유 — 서버가 준 원인 상태 문장을 그대로 쓴다 */
export function missingReason(card: Card): string {
  return `원인 원문 없음 — ${causeStatus(card.cause).message}`;
}
