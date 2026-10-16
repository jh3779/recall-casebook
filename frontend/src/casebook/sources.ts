import { hasCauseText, type Card, type CauseSource, type CheckItem, type ProductionCheckItem } from "../search/types";

/** 573 보고서 판본 — 파일·sha256·제출일로 같은 판본인지 가른다 */
export type ReportSource = Pick<CauseSource, "campaign" | "file" | "pdf_sha256" | "submission_date">;
const same = (a: ReportSource, b: ReportSource) => a.file === b.file && a.pdf_sha256 === b.pdf_sha256 && a.submission_date === b.submission_date;

export const productionItem = (card: Card): ProductionCheckItem | undefined =>
  card.checklist.find((item): item is ProductionCheckItem => item.item === "production_period");

/**
 * 공급사 표시 규칙(DEC-067 결정 ⑧): 공급사 항목에는 573 판본 출처가 없다. 원인 원문의 출처(`cause.source`)나 생산 기간의 출처가
 * 있어 같은 판본임을 확인할 수 있을 때만 그 출처와 함께 보이고, 확인할 수 없으면 숨긴다("출처 미표시"로는 보이지 않는다).
 */
export function supplierView(card: Card): { names: string[]; source: ReportSource } | null {
  const item: CheckItem | undefined = card.checklist.find((c) => c.item === "supplier");
  const names = item?.evidence.map((e) => e.text).filter(Boolean) ?? [];
  if (!names.length) return null;
  const fromCause = hasCauseText(card.cause) ? card.cause.source : null;
  const fromProduction = productionItem(card)?.source ?? null;
  if (fromCause && fromProduction && !same(fromCause, fromProduction)) return null;
  const found = fromCause ?? fromProduction;
  if (!found) return null;
  const { campaign, file, pdf_sha256, submission_date } = found; // 글 정리 방식 등 원인 글에만 해당하는 값은 공급사에 붙이지 않는다
  return { names, source: { campaign, file, pdf_sha256, submission_date } };
}

/** 원인 칸의 상태를 영어 한 줄로 — 글이 있는지만 알리고 판단하지 않는다 */
export function causeLine(card: Card): string {
  const cause = card.cause;
  const campaign = "campaign" in cause && cause.campaign ? ` (${cause.campaign})` : "";
  const lines: Record<string, string> = {
    filled: "Part 573 cause field, verbatim.",
    stated_unknown: "Part 573 cause field, verbatim. Classified as text that opens with a not-reported / under-investigation expression; this does not mean the cause is unknown.",
    no_573_report: "Filed before 2014-08-20, outside the collected Part 573 range. No cause text is shown.",
    report_unreadable: `The Part 573 report${campaign} could not be read.`,
    report_status_unknown: `Whether the Part 573 report${campaign} was collected could not be confirmed.`,
    version_unresolved: `The Part 573 report${campaign} has several versions and the latest could not be chosen. No cause text is shown.`,
    cause_empty: `The cause field of the Part 573 report${campaign} is empty.`,
    cause_no_field: `No cause field was found in the Part 573 report${campaign}.`,
    verify_failed: `The cause text${campaign} did not pass the character check and is not shown.`,
  };
  return Object.hasOwn(lines, cause.status) ? lines[cause.status] : `Cause status: ${cause.status}`;
}
export const causeBadge = (card: Card): { level: "text" | "stated" | "none"; label: string } =>
  card.cause.status === "filled" ? { level: "text", label: "Cause text" }
    : card.cause.status === "stated_unknown" ? { level: "stated", label: "Not reported / under investigation" }
      : { level: "none", label: "No cause text" };
