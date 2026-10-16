import { expect, it } from "vitest";
import { ALL_STEPS, composeDocument, CORE_STEPS, insertBlock, insertedFor, pruneInserted, removeBlock, sameSteps, STEPS, stepParagraphs, TARGET, toggleStep } from "./document";

const prov = { build_id: "abc123", snapshot_date: "2026-10-06" };
it("빈 칸에는 그대로, 글이 있으면 한 줄 띄우고 덧붙인다", () => {
  expect(insertBlock("", "B")).toBe("B");
  expect(insertBlock("내 글\n", "B")).toBe("내 글\n\nB");
});
it("넣은 글을 정확히 빼고 내 글은 남긴다", () => {
  const v = insertBlock("내 글", "[타사 선례 X]\n원문");
  expect(removeBlock(v, "[타사 선례 X]\n원문")).toBe("내 글");
  expect(removeBlock(insertBlock("", "B"), "B")).toBe("");
});
it("넣은 뒤 사용자가 고쳤으면 자동으로 빼지 않는다(null)", () => {
  expect(removeBlock("내 글\n\n[타사 선례 X] 고침", "[타사 선례 X]\n원문")).toBeNull();
});
it("선례를 넣는 칸은 모두 실제 양식의 칸이다", () => {
  const keys = new Set(STEPS.flatMap((s) => s.fields.map((f) => f.key)));
  for (const key of Object.values(TARGET)) expect(keys.has(key)).toBe(true);
});
it("파일 본문은 칸에 쓴 글만 싣고 빈 단계는 (미작성)으로 둔다", () => {
  const text = composeDocument({ subject: "airbag", values: { d2: "  불량 6건  " }, withEvidence: false, prov });
  expect(text).toContain("SUBJECT: airbag");
  expect(text).toContain("DISCIPLINE 2 · PROBLEM DESCRIPTION\nProblem Description — 우리 건의 불량 사실\n불량 6건");
  expect(text).toContain("DISCIPLINE 3 · CONTAINMENT ACTION\n(미작성)");
  expect(text).not.toContain("선례 근거 데이터");
});
it("선례를 넣었을 때만 build·스냅샷 한 줄을 끝에 붙인다", () => {
  const text = composeDocument({ subject: "", values: {}, withEvidence: true, prov });
  expect(text.trimEnd().endsWith("자사 사실이 아닙니다.")).toBe(true);
  expect(text).toContain("build abc123 · 스냅샷 2026-10-06");
  expect(composeDocument({ subject: "", values: {}, withEvidence: true, prov: null })).not.toContain("build");
});
it("적용할 단계: 프리셋은 전체와 D2·D4이고, 토글은 원래 집합을 바꾸지 않는다", () => {
  expect([...ALL_STEPS]).toEqual([1, 2, 3, 4, 5, 6, 7, 8]);
  expect([...CORE_STEPS]).toEqual([2, 4]);
  const after = toggleStep(CORE_STEPS, 3);
  expect([...after].sort()).toEqual([2, 3, 4]);
  expect([...CORE_STEPS]).toEqual([2, 4]);
  expect([...toggleStep(after, 3)]).toEqual([2, 4]);
  expect(sameSteps(CORE_STEPS, new Set([4, 2]))).toBe(true);
  expect(sameSteps(CORE_STEPS, ALL_STEPS)).toBe(false);
});
it("only에 든 단계만 파일 글에 싣고, 빠진 단계에 써 둔 글은 싣지 않는다", () => {
  const values = { d2: "문제", d3: "잠정", d4_root: "원인", d6: "검증" };
  const text = composeDocument({ subject: "s", values, withEvidence: false, prov: null, only: CORE_STEPS });
  expect(text).toContain("DISCIPLINE 2 · PROBLEM DESCRIPTION\nProblem Description — 우리 건의 불량 사실\n문제");
  expect(text).toContain("Root Cause — 우리 건의 근본 원인\n원인");
  for (const dropped of ["DISCIPLINE 1", "DISCIPLINE 3", "잠정", "DISCIPLINE 6", "검증"]) expect(text).not.toContain(dropped);
  expect(composeDocument({ subject: "s", values, withEvidence: false, prov: null })).toContain("DISCIPLINE 3");
});
it("칸이 여럿인 단계의 파일 문단은 칸 이름이 첫 줄에만 붙는다", () => {
  const d4 = STEPS.find((st) => st.n === 4)!;
  expect(stepParagraphs(d4, { d4_escape: "a\nb", d4_root: "c" })).toEqual([{ prefix: "Escape Cause: ", text: "a" }, { text: "b" }, { prefix: "Root Cause: ", text: "c" }]);
  expect(stepParagraphs(STEPS.find((st) => st.n === 2)!, { d2: " x " })).toEqual([{ text: "x" }]);
});

it("단계별로 넣은 것만 접두사를 떼어 돌려준다 — 묶음 화면이 자기 이름으로 찾는다(리뷰 지적: 접두사가 붙은 채로 내려가 '넣음' 표시가 안 켜졌다)", () => {
  const inserted = { "2|draft:gabc": "x", "2|20V001000": "y", "4|draft:gabc": "z", "7|table": "t" };
  expect(insertedFor(inserted, "2")).toEqual({ "draft:gabc": "x", "20V001000": "y" });
  expect(insertedFor(inserted, "4")).toEqual({ "draft:gabc": "z" });
  expect(insertedFor(inserted, "5")).toEqual({});
});

const blockOf = (campno: string) => `[타사 선례 ${campno} · 회사 · 접수 2020-01-05]\n(결함) "원문 ${campno}"`;
it("같은 작업에 선례 목록이 바뀌면 담지 않은 선례의 인용만 본문에서 걷어 내고, 선례에 매이지 않은 글은 남긴다", () => {
  let values: Record<string, string> = {};
  const inserted: Record<string, string> = {};
  for (const [key, field, block] of [["2|20V000001", "d2", blockOf("20V000001")], ["2|20V000002", "d2", blockOf("20V000002")], ["7|table", "d7", "표"], ["4|draft:q", "d4_root", "[확인 질문 — 도구가 만든 고정 문장]\n① 가"]] as const) {
    values = { ...values, [field]: insertBlock(values[field] ?? "", block) };
    inserted[key] = block;
  }
  values.d2 = `내가 쓴 글\n\n${values.d2}`;
  const r = pruneInserted(values, inserted, new Set(["20V000001"])); // 000002는 더는 담지 않음
  expect(r.removed).toEqual(["2|20V000002"]);
  expect(r.values.d2).toContain("20V000001");
  expect(r.values.d2).not.toContain("20V000002");
  expect(r.values.d2).toContain("내가 쓴 글");
  expect(Object.keys(r.inserted).sort()).toEqual(["2|20V000001", "4|draft:q", "7|table"]);
  expect(r.blocked).toEqual([]);
});
it("사용자가 고쳐 더는 그대로 없는 인용은 자동으로 못 빼고 blocked로 알린다", () => {
  const inserted = { "2|20V000002": blockOf("20V000002") };
  const r = pruneInserted({ d2: "내가 고친 글" }, inserted, new Set());
  expect(r.blocked).toEqual(["2|20V000002"]);
  expect(r.values.d2).toBe("내가 고친 글");
  expect(r.inserted).toEqual(inserted);
});
