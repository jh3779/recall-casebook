import { expect, it } from "vitest";
import { composeDocument, insertBlock, removeBlock, STEPS, TARGET } from "./document";

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
