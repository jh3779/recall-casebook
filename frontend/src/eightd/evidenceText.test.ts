import { expect, it } from "vitest";
import fixture from "../search/__fixtures__/search_airbag.json";
import { hasCauseText, type ProductionCheckItem, type SearchResponse } from "../search/types";
import { evidenceBlock, isoDate, missingReason, resultsBlock, supplierName } from "./evidenceText";

const response = fixture as SearchResponse;
const cards = [...response.customer_precedents, ...response.precedents];
const production = (c: (typeof cards)[number]) => c.checklist.find((i): i is ProductionCheckItem => i.item === "production_period");

it.each(cards)("$campno: D2·D5 본문은 결함·결과·시정 원문을 한 글자도 바꾸지 않고 머리줄·꼬리줄을 붙인다", (card) => {
  const d2 = evidenceBlock("2", card)!;
  expect(d2).toContain(`(결함) "${card.defect}"`);
  expect(d2).toContain(`(결과) "${card.consequence}"`);
  expect(d2.split("\n")[0]).toBe(`[타사 선례 ${card.campno} · ${card.maker} · 접수 ${isoDate(card.received_date)}]`);
  expect(d2).toContain(`— 말한 주체: ${card.source.speaker}`);
  expect(evidenceBlock("5", card)).toContain(`(시정) "${card.remedy}"`);
});
it.each(cards)("$campno: D4는 원인 원문이 있을 때만 만들고 말한 주체·출처 파일·sha256을 붙인다", (card) => {
  const d4 = evidenceBlock("4", card);
  if (!hasCauseText(card.cause)) { expect(d4).toBeNull(); return; }
  expect(d4).toContain(`(원인 원문) "${card.cause.text}"`);
  expect(d4).toContain(`— 말한 주체: ${card.cause.speaker}`);
  expect(d4).toContain(card.cause.source.file);
  expect(d4).toContain(card.cause.source.pdf_sha256.slice(0, 12));
  expect(d4!.includes("원인을 모른다는 뜻으로 단정하지 않음")).toBe(card.cause.status === "stated_unknown");
});
it.each(cards)("$campno: D3은 생산 기간 항목이 있을 때만 만들고 원문 줄을 그대로 싣는다", (card) => {
  const d3 = evidenceBlock("3", card);
  const item = production(card);
  if (!item) { expect(d3).toBeNull(); return; }
  for (const e of item.evidence) expect(d3).toContain(e.text);
  expect(d3).toContain(item.source.pdf_sha256.slice(0, 12));
  const supplier = supplierName(card);
  if (supplier) expect(d3).toContain(`Supplier (Part 573): ${supplier}`);
});
it("본문에 넣을 글이 없는 이유는 서버가 준 원인 상태 문장을 그대로 쓴다", () => {
  const none = cards.find((c) => c.cause.status === "no_573_report")!;
  expect(missingReason("4", none)).toContain("접수일이 2014-08-20 이전이라 Part 573 원문 수집 범위 밖입니다");
  expect(missingReason("3", none)).toContain("생산 기간 정보 없음");
});
it("D7 표는 검색 결과 전부를 한 줄씩 싣고 고객사 구분과 공급사 원문을 보인다", () => {
  const block = resultsBlock(response);
  expect(block.split("\n")).toHaveLength(cards.length + 1);
  for (const c of cards) expect(block).toContain(c.campno);
  for (const c of response.customer_precedents) expect(block).toContain(`${c.campno} | ${c.maker} | ${isoDate(c.received_date)} | 고객사`);
});
it("판정 문구를 만들지 않는다", () => {
  for (const c of cards) for (const step of ["2", "3", "4", "5"] as const) expect(evidenceBlock(step, c) ?? "").not.toMatch(/리콜 대상입니다|원인은 이것입니다|해당합니다/);
});
