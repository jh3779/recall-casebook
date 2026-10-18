import { APPENDIX_KEY, appendixParagraphs, composeDocument, D4_EVIDENCE_KEY, evidenceFooter, STEPS, stepParagraphs, type ParaSpec } from "../eightd/document";
import type { ExportContent, Place } from "../eightd/docxPatch";
import { evidenceBlock } from "../eightd/evidenceText";
import type { Card, ProvenanceData } from "../search/types";

/** `composeDocument`가 맨 앞에 붙이는 SUBJECT 줄 — D4 복사문에는 필요 없다(빈 subject일 때의 모양) */
const SUBJECT_HEADER = "8D REPORT\nSUBJECT: \n\n";

/**
 * D4 엔지니어 작성 칸(DEC-069). 메모와 같은 저장 장치를 쓰되 리콜 번호와 겹치지 않게 `@d4:` 접두어 키로 둔다 —
 * 그래서 메모와 똑같이 이 브라우저에만 저장되고(사건 이름이 있을 때) 서버·LLM에는 가지 않는다.
 */
export const D4_KEYS = { escape: "@d4:escape", root: "@d4:root", verify: "@d4:verify" } as const;
export interface D4Values { escape: string; root: string; verify: string }
export const d4Values = (notes: Readonly<Record<string, string>>): D4Values => ({ escape: notes[D4_KEYS.escape] ?? "", root: notes[D4_KEYS.root] ?? "", verify: notes[D4_KEYS.verify] ?? "" });

export interface D4Export {
  /** 8D 양식의 D4 칸에 들어갈 문단 — 엔지니어가 쓴 글(Escape Cause·Root Cause) 뒤에, 본문 삽입을 고른 경우에만 타사 선례 인용이 "[선례 근거 — 타사 공개 원문…]" 제목과 함께 붙는다. 검증 방법은 양식에 칸이 없어 내보내지 않는다 */
  steps: Record<number, ParaSpec[]>;
  /** 8D 표 뒤 부록 문단 — 타사 원인 원문(DEC-064 ③ 형식: 머리줄 + 원문 + 말한 주체·출처 파일·sha256 꼬리줄). 부록을 고르지 않았으면 비어 있다 */
  appendix: ParaSpec[];
  /** 선례 인용을 하나라도 넣었을 때(D4 본문 또는 부록)만 붙는 근거 데이터 한 줄(build·스냅샷) */
  footer: string | null;
  /** 복사용 평문(파일에 들어갈 글과 같은 내용) */
  text: string;
  /** D4 칸 본문·부록에 각각 실제로 들어간 선례 수, 원인 글이 없어 빠진 선례 번호 */
  bodyCount: number;
  appendixCount: number;
  skipped: string[];
  /** 내보낼 글이 있는가(D4 글·D4 본문의 선례 인용·부록) */
  hasContent: boolean;
}

/**
 * 체크한 선례의 원인 원문을 D4 칸 본문(`includeBody`)과 8D 표 뒤 부록(`includeAppendix`)에 넣는다 — 둘 다 기본 꺼짐이고 둘 다 고를 수도 있다(DEC-076).
 * 원인 글이 없는 선례는 없는 말을 채우지 않고 건너뛴다(AGENTS.md 서비스 원칙 3). 선례 내용은 D4에만 넣고 다른 단계에는 넣지 않는다.
 * SUBJECT는 다루지 않는다 — 검색 문장을 양식의 SUBJECT 칸에 말없이 넣지 않는다
 */
export function d4Export({ values, cards, includeBody = false, includeAppendix, prov }: { values: D4Values; cards: readonly Card[]; includeBody?: boolean; includeAppendix: boolean; prov: Pick<ProvenanceData, "build_id" | "snapshot_date"> | null }): D4Export {
  const step = STEPS.find((s) => s.n === 4)!;
  const pairs = includeBody || includeAppendix ? cards.map((c) => [c.campno, evidenceBlock(c)] as const) : [];
  const blocks = pairs.flatMap(([, b]) => (b ? [b] : []));
  const skipped = pairs.filter(([, b]) => !b).map(([n]) => n);
  const evidenceText = blocks.join("\n\n");
  const withBody = includeBody && blocks.length > 0;
  const withAppendix = includeAppendix && blocks.length > 0;
  const own = { d4_escape: values.escape, d4_root: values.root, [D4_EVIDENCE_KEY]: withBody ? evidenceText : "" };
  const paras = stepParagraphs(step, own);
  const appendix = withAppendix ? appendixParagraphs({ [APPENDIX_KEY]: evidenceText }) : [];
  const withEvidence = withBody || withAppendix;
  return {
    steps: paras.length ? { 4: paras } : {},
    appendix,
    footer: withEvidence && prov ? evidenceFooter(prov) : null,
    text: composeDocument({ subject: "", values: { ...own, [APPENDIX_KEY]: withAppendix ? evidenceText : "" }, withEvidence, prov, only: new Set([4]) }).replace(SUBJECT_HEADER, ""),
    bodyCount: withBody ? blocks.length : 0,
    appendixCount: withAppendix ? blocks.length : 0,
    skipped,
    hasContent: paras.length > 0 || withAppendix,
  };
}

/** patchDocx에 넘길 내용 — SUBJECT는 비워 둔다(검색 문장을 양식의 SUBJECT 칸에 넣지 않는다). 컴포넌트가 아니라 여기서 정해야 시험이 이 연결을 지킨다 */
export function docxContent(out: D4Export, place: Place | null): ExportContent {
  return { subject: "", steps: out.steps, footer: out.footer, cells: place ? { 4: place } : undefined, appendix: out.appendix };
}

/** 내려받은 뒤의 안내 — 실제로 칸에 들어갔는지(`filled`)와 부록이 표 뒤에 놓였는지(`appendixPlaced`)를 patchDocx 결과 그대로 말한다. 못 넣은 것을 넣었다고 하지 않는다. `wroteD4`가 false면 쓴 D4 글이 없었던 것이다 */
export function exportMessage(r: { filled: readonly number[]; missing: readonly number[]; ambiguous: readonly number[]; appendixPlaced: boolean | null }, name: string, appendixCount: number, wroteD4: boolean, bodyCount = 0): string {
  const appendix = !appendixCount ? "not added" : r.appendixPlaced ? `${appendixCount} precedent(s) placed after the 8D table` : "could not be placed (no table found in the file) — the file has no appendix, use Copy and paste it yourself";
  const notFilled = wroteD4 && r.missing.includes(4) ? " The D4 cell was not found in the file, so your D4 text was not inserted — pick the cell above or use Copy." : wroteD4 && r.ambiguous.includes(4) ? " Several cells match D4 — pick the cell above; your D4 text was not inserted." : "";
  const d4 = !wroteD4 ? "no D4 text written" : r.filled.includes(4) ? `D4 text inserted${bodyCount ? ` (including ${bodyCount} precedent quote(s) after your text)` : ""}` : "D4 text not inserted";
  return `Downloaded ${name}. ${d4}; appendix ${appendix}. The SUBJECT cell is left as it was.${notFilled}`;
}
