import { APPENDIX_KEY, appendixParagraphs, composeDocument, evidenceFooter, STEPS, stepParagraphs, type ParaSpec } from "../eightd/document";
import { evidenceBlock } from "../eightd/evidenceText";
import type { Card, ProvenanceData } from "../search/types";

/**
 * D4 엔지니어 작성 칸(DEC-069). 메모와 같은 저장 장치를 쓰되 리콜 번호와 겹치지 않게 `@d4:` 접두어 키로 둔다 —
 * 그래서 메모와 똑같이 이 브라우저에만 저장되고(사건 이름이 있을 때) 서버·LLM에는 가지 않는다.
 */
export const D4_KEYS = { escape: "@d4:escape", root: "@d4:root", verify: "@d4:verify" } as const;
export interface D4Values { escape: string; root: string; verify: string }
export const d4Values = (notes: Readonly<Record<string, string>>): D4Values => ({ escape: notes[D4_KEYS.escape] ?? "", root: notes[D4_KEYS.root] ?? "", verify: notes[D4_KEYS.verify] ?? "" });

export interface D4Export {
  /** 8D 양식의 D4 칸에 들어갈 문단 — 엔지니어가 쓴 글만(Escape Cause·Root Cause). 검증 방법은 양식에 칸이 없어 내보내지 않는다 */
  steps: Record<number, ParaSpec[]>;
  /** 8D 표 뒤 부록 문단 — 타사 원인 원문(DEC-064 ③ 형식: 머리줄 + 원문 + 말한 주체·출처 파일·sha256 꼬리줄). 부록을 고르지 않았으면 비어 있다 */
  appendix: ParaSpec[];
  /** 부록을 넣었을 때만 붙는 근거 데이터 한 줄(build·스냅샷) */
  footer: string | null;
  /** 복사용 평문(파일에 들어갈 글과 같은 내용) */
  text: string;
  /** 부록에 실제로 들어간 선례 수, 원인 글이 없어 부록에서 빠진 선례 번호 */
  appendixCount: number;
  skipped: string[];
  /** 내보낼 글이 있는가(D4 글 또는 부록) */
  hasContent: boolean;
}

/** 체크한 선례의 원인 원문을 부록으로 — 원인 글이 없는 선례는 없는 말을 채우지 않고 건너뛴다(AGENTS.md 서비스 원칙 3) */
export function d4Export({ values, cards, includeAppendix, subject, prov }: { values: D4Values; cards: readonly Card[]; includeAppendix: boolean; subject: string; prov: Pick<ProvenanceData, "build_id" | "snapshot_date"> | null }): D4Export {
  const step = STEPS.find((s) => s.n === 4)!;
  const own = { d4_escape: values.escape, d4_root: values.root };
  const pairs = includeAppendix ? cards.map((c) => [c.campno, evidenceBlock("4", c)] as const) : [];
  const blocks = pairs.flatMap(([, b]) => (b ? [b] : []));
  const skipped = pairs.filter(([, b]) => !b).map(([n]) => n);
  const appendixText = blocks.join("\n\n");
  const withAppendix = blocks.length > 0;
  const paras = stepParagraphs(step, own);
  const appendix = withAppendix ? appendixParagraphs({ [APPENDIX_KEY]: appendixText }) : [];
  return {
    steps: paras.length ? { 4: paras } : {},
    appendix,
    footer: withAppendix && prov ? evidenceFooter(prov) : null,
    text: composeDocument({ subject, values: { ...own, [APPENDIX_KEY]: appendixText }, withEvidence: withAppendix, prov, only: new Set([4]) }),
    appendixCount: blocks.length,
    skipped,
    hasContent: paras.length > 0 || withAppendix,
  };
}
