import type { ProvenanceData } from "../search/types";

export interface Field { key: string; label: string; hint?: string }
export interface Step { n: number; name: string; fields: Field[] }

/** 예시 8D 양식(영문 8D 순서). 실제 고객사 양식 맞춤은 다음 단계(DEC-064) */
export const STEPS: Step[] = [
  { n: 1, name: "TEAM", fields: [{ key: "team_chair", label: "CHAIR PERSON" }, { key: "team_members", label: "MEMBERS" }] },
  { n: 2, name: "PROBLEM DESCRIPTION", fields: [{ key: "d2", label: "Problem Description — 우리 건의 불량 사실", hint: "6하 원칙, 계량 가능한 표현(건수·일시·장소·조건)" }] },
  { n: 3, name: "CONTAINMENT ACTION", fields: [{ key: "d3", label: "Containment Action — 우리 건의 잠정 조치", hint: "누가·언제·어떻게, 선별 범위" }] },
  { n: 4, name: "DEFINE THE PROBLEM CAUSE", fields: [{ key: "d4_escape", label: "Escape Cause — 탐지 못 한 이유" }, { key: "d4_root", label: "Root Cause — 우리 건의 근본 원인", hint: "서비스는 이 칸을 채우거나 제안하지 않습니다" }] },
  { n: 5, name: "PERMANENT ACTION", fields: [{ key: "d5", label: "Permanent Action — 우리 건의 상용 조치", hint: "개선의 종류·시기·방법" }] },
  { n: 6, name: "VERIFICATION OF EFFECTIVENESS", fields: [{ key: "d6", label: "Verification — 효과 검증", hint: "계량한 검증 결과" }] },
  { n: 7, name: "PREVENTIVE RECURRENCE", fields: [{ key: "d7", label: "Preventive Recurrence — 우리 건의 수평 전개", hint: "4M 기준으로 다른 제품 점검, 표준화" }] },
  { n: 8, name: "CLOSE", fields: [{ key: "d8_received", label: "CAR Received" }, { key: "d8_review", label: "Review" }, { key: "d8_approval", label: "Approval" }] },
];

export const ALL_STEPS: ReadonlySet<number> = new Set(STEPS.map((s) => s.n));
/** 선례 근거가 들어가는 단계 — 원인(D4)만 적용하는 프리셋. 선례 내용은 D4에만 넣는다(DEC-076) */
export const CORE_STEPS: ReadonlySet<number> = new Set([4]);
export const toggleStep = (applied: ReadonlySet<number>, n: number): Set<number> => { const next = new Set(applied); if (!next.delete(n)) next.add(n); return next; };
export const sameSteps = (a: ReadonlySet<number>, b: ReadonlySet<number>) => a.size === b.size && [...a].every((n) => b.has(n));

/** 이 단계에서 넣은 것만, 단계 접두사("2|")를 뗀 이름으로 — 묶음 화면이 자기 이름(draft:…)으로 찾는다 */
export const insertedFor = (inserted: Readonly<Record<string, string>>, step: string): Record<string, string> =>
  Object.fromEntries(Object.entries(inserted).filter(([k]) => k.startsWith(`${step}|`)).map(([k, v]) => [k.slice(step.length + 1), v]));
export const shortLabel = (label: string) => label.split(" — ")[0];

/** 양식 칸에 들어갈 한 문단 — prefix는 칸이 여럿인 단계에서 굵게 붙는 칸 이름 */
export interface ParaSpec { prefix?: string; text: string; bold?: boolean }
/** 한 단계의 칸 글을 문단(줄 단위)으로 — 칸이 여럿이면 각 칸 첫 줄 앞에 칸 이름을 붙인다(양식 미리보기와 같은 모양) */
export function stepParagraphs(step: Step, values: Record<string, string>): ParaSpec[] {
  const own = step.fields.flatMap((f) => {
    const value = values[f.key]?.trim();
    if (!value) return [];
    return value.split("\n").map((text, i) => ({ text, ...(i === 0 && step.fields.length > 1 ? { prefix: `${shortLabel(f.label)}: ` } : {}) }));
  });
  return step.n === 4 ? [...own, ...d4EvidenceParagraphs(values)] : own;
}

/**
 * D4 칸 안의 선례 근거 — 사용자가 "본문에 텍스트로 넣기"를 누른 타사 원인 원문. 엔지니어가 쓴 Escape·Root Cause 글 뒤에 제목 한 줄(굵게)을 두고 붙인다.
 * 제목과 각 인용의 머리줄 "[타사 선례 …]"이 타사 원문임을 밝혀, 서류를 훑는 사람이 타사 원인을 이 건의 근본 원인으로 읽지 않게 한다(DEC-076).
 */
export const D4_EVIDENCE_KEY = "d4_evidence";
export const D4_EVIDENCE_TITLE = "[선례 근거 — 타사 공개 원문이며 자사 사실이 아닙니다]";
export function d4EvidenceParagraphs(values: Record<string, string>): ParaSpec[] {
  const value = values[D4_EVIDENCE_KEY]?.trim();
  return value ? [{ text: D4_EVIDENCE_TITLE, bold: true }, ...value.split("\n").map((text) => ({ text }))] : [];
}

/** 선례 근거 부록 — D4 타사 원인 원문을 8D 표 뒤 별도 문단으로도 둘 수 있다(DEC-064 ④·DEC-076: D4 본문과 부록 둘 다 선택). 둘 다 기본은 꺼짐이다 */
export const APPENDIX_KEY = "appendix";
export const APPENDIX_TITLE = "[선례 근거 부록 — 타사 공개 원문과 도구 안내문이며 자사 사실이 아닙니다]";
/** 선례 인용이 들어가는 곳 — 선례 내용은 D4에만 넣는다(DEC-076). "4"는 D4 칸 본문(엔지니어 글 뒤), "4a"는 8D 표 뒤 부록. 나머지 단계에는 선례 내용을 넣지 않는다 */
export const TARGET: Record<string, string> = { "4": D4_EVIDENCE_KEY, "4a": APPENDIX_KEY };
/** 부록의 문단 — 제목 한 줄(굵게) 뒤에 부록 글을 줄 단위로. 글이 없으면 부록 자체가 없다 */
export function appendixParagraphs(values: Record<string, string>): ParaSpec[] {
  const value = values[APPENDIX_KEY]?.trim();
  return value ? [{ text: APPENDIX_TITLE, bold: true }, ...value.split("\n").map((text) => ({ text }))] : [];
}

/** 칸 끝에 한 줄 띄우고 덧붙인다 */
export function insertBlock(value: string, block: string): string {
  return (value.trim() ? `${value.replace(/\s+$/, "")}\n\n` : "") + block;
}
/** 넣었던 글을 뺀다. 사용자가 그 글을 고쳐 더는 그대로 없으면 null(자동으로 못 뺀다) */
export function removeBlock(value: string, block: string): string | null {
  if (!value.includes(block)) return null;
  return value.replace(`\n\n${block}`, "").replace(block, "").trim();
}

/**
 * 선례 목록이나 검색 결과가 바뀌어 돌아왔을 때, 더는 담지 않은 선례의 인용을 본문에서 걷어 낸다(리뷰 지적 — 화면에서 뺄 버튼이 없는 인용이 남지 않게).
 * 인용 머리줄의 리콜 번호로 판단한다(번호 모양을 가정하지 않는다). dropUnlinked면 선례에 매이지 않은 글(D7 검색 결과 표·고정 확인 질문)도 걷어 낸다 — 질문이 바뀐 경우.
 * 걷어 낸 인용이 있으면 고정 확인 질문도 함께 걷어 낸다(그 인용에서 나온 질문일 수 있다). 사용자가 고쳐 자동으로 못 빼는 글은 blocked로 알리고 넣은 목록에서만 뺀다(칸의 글은 그대로).
 */
export function pruneInserted(values: Record<string, string>, inserted: Record<string, string>, keep: ReadonlySet<string>, dropUnlinked = false): { values: Record<string, string>; inserted: Record<string, string>; removed: string[]; blocked: string[] } {
  const nextValues = { ...values };
  const nextInserted = { ...inserted };
  const removed: string[] = [];
  const blocked: string[] = [];
  const drop = (key: string, block: string) => {
    const field = TARGET[key.split("|")[0]];
    const next = field ? removeBlock(nextValues[field] ?? "", block) : null;
    delete nextInserted[key];
    if (next === null) { blocked.push(key); return; }
    nextValues[field] = next;
    removed.push(key);
  };
  for (const [key, block] of Object.entries(inserted)) {
    const refs = [...block.matchAll(/\[타사 선례 ([^\s·\]]+)/g)].map((m) => m[1]);
    if (refs.length ? !refs.every((c) => keep.has(c)) : dropUnlinked) drop(key, block);
  }
  if (removed.length || blocked.length) {
    for (const [key, block] of Object.entries(nextInserted)) if (key.endsWith("|draft:q")) drop(key, block);
  }
  return { values: nextValues, inserted: nextInserted, removed, blocked };
}

/** 선례를 하나라도 넣었을 때 문서 끝에 붙는 근거 데이터 한 줄 */
export const evidenceFooter = (prov: Pick<ProvenanceData, "build_id" | "snapshot_date">) => `※ 선례 근거 데이터: build ${prov.build_id} · 스냅샷 ${prov.snapshot_date} · 대괄호 [타사 선례 …] 글은 타사 공개 원문이며 자사 사실이 아닙니다.`;

/** 파일 본문에 들어갈 글 — 칸에 쓴 글만 그대로(only에 든 단계만). 선례를 하나라도 넣었으면 근거 데이터 한 줄을 끝에 붙인다 */
export function composeDocument({ subject, values, withEvidence, prov, only = ALL_STEPS }: { subject: string; values: Record<string, string>; withEvidence: boolean; prov: Pick<ProvenanceData, "build_id" | "snapshot_date"> | null; only?: ReadonlySet<number> }): string {
  const out = [`8D REPORT\nSUBJECT: ${subject}\n`];
  for (const step of STEPS.filter((st) => only.has(st.n))) {
    const parts = step.fields.flatMap((f) => (values[f.key]?.trim() ? [`${f.label}\n${values[f.key].trim()}`] : []));
    if (step.n === 4 && values[D4_EVIDENCE_KEY]?.trim()) parts.push(`${D4_EVIDENCE_TITLE}\n${values[D4_EVIDENCE_KEY].trim()}`);
    out.push(`DISCIPLINE ${step.n} · ${step.name}\n${parts.length ? parts.join("\n\n") : "(미작성)"}\n`);
  }
  if (only.has(4) && values[APPENDIX_KEY]?.trim()) out.push(`${APPENDIX_TITLE}\n${values[APPENDIX_KEY].trim()}\n`);
  if (withEvidence && prov) out.push(evidenceFooter(prov));
  return out.join("\n");
}
