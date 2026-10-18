import { expect, it } from "vitest";
import { ALL_STEPS, composeDocument, CORE_STEPS, D4_EVIDENCE_KEY, D4_EVIDENCE_TITLE, d4EvidenceParagraphs, insertBlock, insertedFor, pruneInserted, removeBlock, sameSteps, STEPS, stepParagraphs, TARGET, toggleStep, APPENDIX_KEY, APPENDIX_TITLE, appendixParagraphs } from "./document";

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
it("선례 내용은 D4에만 들어간다 — D4 칸 본문('4')과 8D 표 뒤 부록('4a')뿐이고, 'Root Cause' 칸이나 D2·D3·D5·D7에는 넣지 않는다(DEC-076)", () => {
  expect(Object.keys(TARGET).sort()).toEqual(["4", "4a"]);
  const keys = new Set(STEPS.flatMap((s) => s.fields.map((f) => f.key)));
  expect(TARGET["4"]).toBe(D4_EVIDENCE_KEY);
  expect(TARGET["4a"]).toBe(APPENDIX_KEY);
  for (const key of Object.values(TARGET)) { expect(keys.has(key)).toBe(false); expect(key).not.toBe("d4_root"); expect(key).not.toBe("d4_escape"); } // 엔지니어가 쓰는 칸과 섞이지 않는 별도 칸
});
it("D4 칸 본문의 선례 근거는 엔지니어가 쓴 글 뒤에 타사 원문 제목과 함께 붙고, 다른 단계 문단은 바뀌지 않는다(DEC-076)", () => {
  const d4 = STEPS.find((st) => st.n === 4)!;
  const values = { d4_escape: "a", d4_root: "c", [D4_EVIDENCE_KEY]: "[타사 선례 20V000001]\n(원인 원문) \"원문\"" };
  expect(stepParagraphs(d4, values)).toEqual([
    { prefix: "Escape Cause: ", text: "a" }, { prefix: "Root Cause: ", text: "c" },
    { text: D4_EVIDENCE_TITLE, bold: true }, { text: "[타사 선례 20V000001]" }, { text: "(원인 원문) \"원문\"" },
  ]);
  expect(stepParagraphs(d4, { d4_root: "c" })).toEqual([{ prefix: "Root Cause: ", text: "c" }]); // 선례를 넣지 않으면 달라지는 것이 없다
  expect(d4EvidenceParagraphs({})).toEqual([]);
  for (const step of STEPS.filter((st) => st.n !== 4)) expect(stepParagraphs(step, { ...values, d2: "x", d3: "y" }).some((p) => p.text.includes("타사 선례"))).toBe(false); // 다른 단계에는 선례 글이 섞이지 않는다
  const text = composeDocument({ subject: "s", values: { d4_root: "자사 원인", [D4_EVIDENCE_KEY]: "[타사 선례 20V000001]\n원문" }, withEvidence: true, prov });
  const at = (s: string) => text.indexOf(s);
  expect(at("Root Cause — 우리 건의 근본 원인\n자사 원인")).toBeGreaterThan(-1);
  expect(at(D4_EVIDENCE_TITLE)).toBeGreaterThan(at("자사 원인")); // 엔지니어 글 뒤
  expect(at(D4_EVIDENCE_TITLE)).toBeLessThan(at("DISCIPLINE 5")); // D4 칸 안
  expect(composeDocument({ subject: "s", values: { [D4_EVIDENCE_KEY]: "x" }, withEvidence: true, prov, only: new Set([2, 3]) })).not.toContain(D4_EVIDENCE_TITLE); // D4를 적용하지 않으면 빠진다
});
it("선례 근거 부록은 D4를 적용했을 때만, 글이 있을 때만 8D 표 뒤에 별도 제목과 함께 나오고 칸 본문에는 섞이지 않는다", () => {
  const values = { d4_root: "자사 원인", [APPENDIX_KEY]: "[타사 선례 20V000001]\n(원인 원문) \"원문\"" };
  const text = composeDocument({ subject: "s", values, withEvidence: true, prov });
  expect(text).toContain(APPENDIX_TITLE);
  expect(text.indexOf("Root Cause — 우리 건의 근본 원인\n자사 원인")).toBeGreaterThan(-1);
  expect(text.slice(0, text.indexOf(APPENDIX_TITLE))).not.toContain("타사 선례"); // 부록 앞(8D 칸들)에는 타사 원문이 없다
  expect(text.indexOf(APPENDIX_TITLE)).toBeLessThan(text.indexOf("※ 선례 근거 데이터"));
  expect(composeDocument({ subject: "s", values, withEvidence: false, prov, only: new Set([2]) })).not.toContain(APPENDIX_TITLE); // D4 미적용
  expect(composeDocument({ subject: "s", values: { d2: "x" }, withEvidence: false, prov })).not.toContain(APPENDIX_TITLE); // 글 없음
  expect(appendixParagraphs(values)[0]).toEqual({ text: APPENDIX_TITLE, bold: true });
  expect(appendixParagraphs({})).toEqual([]);
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
it("적용할 단계: 프리셋은 전체와 D4(선례 내용이 들어가는 단계)이고, 토글은 원래 집합을 바꾸지 않는다", () => {
  expect([...ALL_STEPS]).toEqual([1, 2, 3, 4, 5, 6, 7, 8]);
  expect([...CORE_STEPS]).toEqual([4]);
  const after = toggleStep(CORE_STEPS, 3);
  expect([...after].sort()).toEqual([3, 4]);
  expect([...CORE_STEPS]).toEqual([4]);
  expect([...toggleStep(after, 3)]).toEqual([4]);
  expect(sameSteps(CORE_STEPS, new Set([4]))).toBe(true);
  expect(sameSteps(CORE_STEPS, ALL_STEPS)).toBe(false);
});
it("only에 든 단계만 파일 글에 싣고, 빠진 단계에 써 둔 글은 싣지 않는다", () => {
  const values = { d2: "문제", d3: "잠정", d4_root: "원인", d6: "검증" };
  const text = composeDocument({ subject: "s", values, withEvidence: false, prov: null, only: new Set([2, 4]) });
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

it("단계별로 넣은 것만 접두사를 떼어 돌려준다 — 묶음 화면이 자기 이름으로 찾는다(리뷰 지적: 접두사가 붙은 채로 내려가 '넣음' 표시가 안 켜졌다). D4 본문 '4|'와 부록 '4a|'는 서로 섞이지 않는다", () => {
  const inserted = { "4|draft:gabc": "z", "4|20V001000": "y", "4a|20V001000": "w" };
  expect(insertedFor(inserted, "4")).toEqual({ "draft:gabc": "z", "20V001000": "y" });
  expect(insertedFor(inserted, "4a")).toEqual({ "20V001000": "w" });
  expect(insertedFor(inserted, "5")).toEqual({});
});

const blockOf = (campno: string) => `[타사 선례 ${campno} · 회사 · 접수 2020-01-05]\n(원인 원문) "원문 ${campno}"`;
it("선례 목록만 바뀌면 담지 않은 선례의 인용(D4 본문·부록)과 확인 질문을 걷어 내고, 사용자가 쓴 글은 남긴다", () => {
  let values: Record<string, string> = {};
  const inserted: Record<string, string> = {};
  for (const [key, field, block] of [["4|20V000001", D4_EVIDENCE_KEY, blockOf("20V000001")], ["4|20V000002", D4_EVIDENCE_KEY, blockOf("20V000002")], ["4a|20V000002", APPENDIX_KEY, blockOf("20V000002")], ["4|draft:q", D4_EVIDENCE_KEY, "[확인 질문 — 도구가 만든 고정 문장]\n① 가"]] as const) {
    values = { ...values, [field]: insertBlock(values[field] ?? "", block) };
    inserted[key] = block;
  }
  values[D4_EVIDENCE_KEY] = `내가 쓴 글\n\n${values[D4_EVIDENCE_KEY]}`;
  const r = pruneInserted(values, inserted, new Set(["20V000001"])); // 000002는 더는 담지 않음
  expect(r.removed.sort()).toEqual(["4a|20V000002", "4|20V000002", "4|draft:q"].sort()); // 인용을 걷어 냈으니 그 묶음에서 나왔을 수 있는 고정 확인 질문도 함께(리뷰 지적)
  expect(r.values[D4_EVIDENCE_KEY]).toContain("20V000001");
  expect(r.values[D4_EVIDENCE_KEY]).not.toContain("20V000002");
  expect(r.values[D4_EVIDENCE_KEY]).toContain("내가 쓴 글");
  expect(r.values[APPENDIX_KEY]).toBe(""); // 부록에서도 빠진다
  expect(Object.keys(r.inserted)).toEqual(["4|20V000001"]);
  expect(r.blocked).toEqual([]);
});
it("사용자가 고쳐 더는 그대로 없는 인용은 자동으로 못 빼고 blocked로 알린다", () => {
  const inserted = { "4|20V000002": blockOf("20V000002") };
  const r = pruneInserted({ [D4_EVIDENCE_KEY]: "내가 고친 글" }, inserted, new Set());
  expect(r.blocked).toEqual(["4|20V000002"]);
  expect(r.values[D4_EVIDENCE_KEY]).toBe("내가 고친 글");
});

it("리콜 번호 모양을 가정하지 않는다 — 21V00F000처럼 실제 데이터에 있는 모양도 걷어 낸다(리뷰 지적)", () => {
  const block = blockOf("21V00F000");
  const r = pruneInserted({ [D4_EVIDENCE_KEY]: insertBlock("", block) }, { "4|21V00F000": block }, new Set());
  expect(r.removed).toEqual(["4|21V00F000"]);
  expect(r.values[D4_EVIDENCE_KEY]).toBe("");
});
it("질문이 바뀌면(dropUnlinked) 선례에 매이지 않은 글(고정 확인 질문)도 걷어 낸다", () => {
  const question = "[확인 질문 — 도구가 만든 고정 문장]\n① 가";
  const inserted = { "4|20V000001": blockOf("20V000001"), "4|draft:q": question };
  const values = { [D4_EVIDENCE_KEY]: [inserted["4|20V000001"], question].join("\n\n") };
  const same = pruneInserted(values, inserted, new Set(["20V000001"])); // 질문 그대로, 선례도 그대로: 아무것도 안 걷는다
  expect(Object.keys(same.inserted).sort()).toEqual(["4|20V000001", "4|draft:q"]);
  const changed = pruneInserted(values, inserted, new Set(["20V000001"]), true); // 질문이 바뀜: 선례에 매이지 않은 질문을 걷고 선례 인용은 남긴다
  expect(Object.keys(changed.inserted)).toEqual(["4|20V000001"]);
  expect(changed.values[D4_EVIDENCE_KEY]).not.toContain("확인 질문");
});
it("직접 고쳐 못 뺀 인용은 넣은 목록에서는 빼서 개수·꼬리줄이 사실과 맞게 하고, 칸의 글은 그대로 둔다", () => {
  const r = pruneInserted({ [D4_EVIDENCE_KEY]: "내가 고친 글" }, { "4|20V000002": blockOf("20V000002") }, new Set());
  expect(r.blocked).toEqual(["4|20V000002"]);
  expect(r.inserted).toEqual({});
  expect(r.values[D4_EVIDENCE_KEY]).toBe("내가 고친 글");
});
it("같은 렌더에서 두 번 걷어 낼 때 첫 번째 결과(글·넣은 목록)를 이어 쓰면 두 번째는 아무것도 못 뺀 것으로 잘못 세지 않는다(13차 리뷰 지적)", () => {
  const values = { [D4_EVIDENCE_KEY]: insertBlock("", "[타사 선례 20V000002]\n원문"), [APPENDIX_KEY]: insertBlock("", "[타사 선례 20V000002]\n원문") };
  const inserted = { "4|20V000002": "[타사 선례 20V000002]\n원문", "4a|20V000002": "[타사 선례 20V000002]\n원문" };
  const first = pruneInserted(values, inserted, new Set(), true);
  expect(first.removed.length).toBe(2);
  const again = pruneInserted(first.values, first.inserted, new Set(), true);
  expect(again.removed).toEqual([]);
  expect(again.blocked).toEqual([]);
  expect(pruneInserted(first.values, inserted, new Set(), true).blocked.length).toBe(2); // 옛 목록을 쓰면 이미 지운 글이 "못 뺀 것"으로 잡힌다 — 그래서 화면은 갱신한 목록을 쓴다
});
