import { expect, it } from "vitest";
import fixture from "../search/__fixtures__/search_airbag.json";
import { hasCauseText, type SearchResponse } from "../search/types";
import { groupBlock, groupId, questionsBlock, quoteBlock, sameBuild, type DraftItem } from "./draft";

const response = fixture as SearchResponse;
const cards = [...response.customer_precedents, ...response.precedents];
const filled = cards.find((c) => hasCauseText(c.cause) && c.cause.status === "filled")!;
const cause = filled.cause as Extract<typeof filled.cause, { text: string }>;

const d2item = (card = cards[0], quote = card.defect.slice(0, 20)): DraftItem => ({ campno: card.campno, field: "defect", quote, start: 0, end: quote.length, speaker: card.source.speaker, dataset: card.source.dataset, snapshot_date: card.source.snapshot_date });
const d4item = (): DraftItem => ({ campno: filled.campno, field: "cause", quote: cause.text, start: 0, end: cause.text.length, speaker: cause.speaker, cause_status: "filled", cause_source: cause.source });

it("D2 인용은 머리줄·원문 줄·꼬리줄(말한 주체·스냅샷)로 평문이 된다", () => {
  const item = d2item();
  expect(quoteBlock(item, cards[0]).split("\n")).toEqual([
    `[타사 선례 ${cards[0].campno} · ${cards[0].maker} · 접수 ${cards[0].received_date.slice(0, 4)}-${cards[0].received_date.slice(4, 6)}-${cards[0].received_date.slice(6, 8)}]`,
    `(결함) "${item.quote}"`,
    `— 말한 주체: ${cards[0].source.speaker} · ${cards[0].source.dataset} 스냅샷 ${cards[0].source.snapshot_date}`,
  ]);
});
it("D4 인용은 원인 원문 줄과 말한 주체·출처 파일·sha256 꼬리줄을 붙이고 글자를 바꾸지 않는다", () => {
  const block = quoteBlock(d4item(), filled);
  expect(block).toContain(`(원인 원문) "${cause.text}"`);
  expect(block).toContain(`— 말한 주체: ${cause.speaker} · 출처: ${cause.source.file}`);
  expect(block).toContain(cause.source.pdf_sha256.slice(0, 12));
});
it("미보고·조사 중 표현은 단정하지 않는다는 줄이 붙는다", () => {
  expect(quoteBlock({ ...d4item(), cause_status: "stated_unknown" }, filled)).toContain("원인을 모른다는 뜻으로 단정하지 않음");
  expect(quoteBlock(d4item(), filled)).not.toContain("단정하지 않음");
});
it("카드를 못 찾아도 번호는 남기고 출처 줄을 지우지 않는다", () => {
  const block = quoteBlock(d2item(), undefined);
  expect(block.split("\n")[0]).toBe(`[타사 선례 ${cards[0].campno}]`);
  expect(block).toContain("— 말한 주체:");
});
it("묶음을 본문에 넣을 때 도구가 붙인 제목은 빼고 인용마다 머리·꼬리줄을 유지한다(리뷰 지적 — 제목은 의역이라 한정어가 빠질 수 있다)", () => {
  const block = groupBlock({ title: "회로 단락을 적은 선례", items: [d2item(cards[0]), d2item(cards[1])] }, cards);
  expect(block).not.toContain("회로 단락을 적은 선례");
  expect(block).not.toContain("도구가 붙인 제목");
  const parts = block.split("\n\n");
  expect(parts).toHaveLength(2);
  expect(parts[0]).toContain(cards[0].campno);
  expect(parts[1]).toContain(cards[1].campno);
  expect(parts.every((r) => r.startsWith("[타사 선례 ") && r.includes("— 말한 주체:"))).toBe(true);
});
it("묶음 이름은 내용에서 만들어 같은 순번에 다른 묶음이 와도 달라진다", () => {
  const a = { title: "가", items: [d2item(cards[0])] };
  expect(groupId(a)).toBe(groupId({ ...a }));
  expect(groupId(a)).not.toBe(groupId({ title: "나", items: a.items }));
  expect(groupId(a)).not.toBe(groupId({ title: "가", items: [d2item(cards[1])] }));
});
it("확인 질문은 고정 문장임을 밝히고 번호를 붙인다", () => {
  expect(questionsBlock(["가", "나"])).toBe("[확인 질문 — 도구가 만든 고정 문장]\n① 가\n② 나");
  expect(questionsBlock(Array.from({ length: 10 }, (_, i) => `q${i}`)).split("\n")[10]).toBe("10. q9");
});

it("초안 응답의 build가 검색 응답과 다르면 같은 서버 판본이 아니라고 본다(검색 응답이 없으면 비교하지 않는다)", () => {
  expect(sameBuild({ build_id: "aaa" }, { build_id: "aaa" })).toBe(true);
  expect(sameBuild({ build_id: "aaa" }, { build_id: "bbb" })).toBe(false);
  expect(sameBuild({ build_id: "aaa" }, null)).toBe(true);
});
