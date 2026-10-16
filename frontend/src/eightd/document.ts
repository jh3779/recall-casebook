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
/** 선례 근거가 핵심인 단계 — 문제 기술(D2)과 원인(D4)만 적용하는 프리셋 */
export const CORE_STEPS: ReadonlySet<number> = new Set([2, 4]);
export const toggleStep = (applied: ReadonlySet<number>, n: number): Set<number> => { const next = new Set(applied); if (!next.delete(n)) next.add(n); return next; };
export const sameSteps = (a: ReadonlySet<number>, b: ReadonlySet<number>) => a.size === b.size && [...a].every((n) => b.has(n));

/** 이 단계에서 넣은 것만, 단계 접두사("2|")를 뗀 이름으로 — 묶음 화면이 자기 이름(draft:…)으로 찾는다 */
export const insertedFor = (inserted: Readonly<Record<string, string>>, step: string): Record<string, string> =>
  Object.fromEntries(Object.entries(inserted).filter(([k]) => k.startsWith(`${step}|`)).map(([k, v]) => [k.slice(step.length + 1), v]));
export const shortLabel = (label: string) => label.split(" — ")[0];

/** 양식 칸에 들어갈 한 문단 — prefix는 칸이 여럿인 단계에서 굵게 붙는 칸 이름 */
export interface ParaSpec { prefix?: string; text: string }
/** 한 단계의 칸 글을 문단(줄 단위)으로 — 칸이 여럿이면 각 칸 첫 줄 앞에 칸 이름을 붙인다(양식 미리보기와 같은 모양) */
export function stepParagraphs(step: Step, values: Record<string, string>): ParaSpec[] {
  return step.fields.flatMap((f) => {
    const value = values[f.key]?.trim();
    if (!value) return [];
    return value.split("\n").map((text, i) => ({ text, ...(i === 0 && step.fields.length > 1 ? { prefix: `${shortLabel(f.label)}: ` } : {}) }));
  });
}

/** 선례 인용이 들어가는 칸 — D4는 "근본 원인" 칸 하나뿐이고, 그 안에서 머리줄로만 자사 글과 구분된다(DEC-064 알려진 한계 ④) */
export const TARGET: Record<string, string> = { "2": "d2", "3": "d3", "4": "d4_root", "5": "d5", "7": "d7" };

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
 * 같은 작업에 선례 목록이 바뀌어 돌아왔을 때, 더는 담지 않은 선례의 인용을 본문에서 걷어 낸다(리뷰 지적 — 화면에서 뺄 버튼이 없는 인용이 남지 않게).
 * 인용 머리줄의 리콜 번호로 판단하고, D7 검색 결과 표와 고정 확인 질문은 선례에 매이지 않아 남긴다. 사용자가 고쳐 자동으로 못 빼는 글은 blocked로 알린다.
 */
export function pruneInserted(values: Record<string, string>, inserted: Record<string, string>, keep: ReadonlySet<string>): { values: Record<string, string>; inserted: Record<string, string>; removed: string[]; blocked: string[] } {
  const nextValues = { ...values };
  const nextInserted = { ...inserted };
  const removed: string[] = [];
  const blocked: string[] = [];
  for (const [key, block] of Object.entries(inserted)) {
    const refs = [...block.matchAll(/\[타사 선례 (\d{2}[A-Z]\d{6})/g)].map((m) => m[1]);
    if (!refs.length || refs.every((c) => keep.has(c))) continue;
    const field = TARGET[key.split("|")[0]];
    const next = field ? removeBlock(nextValues[field] ?? "", block) : null;
    if (next === null) { blocked.push(key); continue; }
    nextValues[field] = next;
    delete nextInserted[key];
    removed.push(key);
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
    out.push(`DISCIPLINE ${step.n} · ${step.name}\n${parts.length ? parts.join("\n\n") : "(미작성)"}\n`);
  }
  if (withEvidence && prov) out.push(evidenceFooter(prov));
  return out.join("\n");
}
