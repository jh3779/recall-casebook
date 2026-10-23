import { expect, it } from "vitest";
import fixture from "../search/__fixtures__/search_airbag.json";
import { hasCauseText, type Card, type SearchResponse } from "../search/types";
import { causeBadge, causeLine, groupCandidates, langOf, supplierView } from "./sources";

const cards = [...(fixture as SearchResponse).customer_precedents, ...(fixture as SearchResponse).precedents];
const withSupplier = cards.find((c) => hasCauseText(c.cause) && c.checklist.some((i) => i.item === "supplier"))!;
const supplierItem = withSupplier.checklist.find((i) => i.item === "supplier")!;

it("원인 원문 출처가 있으면 공급사를 그 573 판본 출처와 함께 보인다", () => {
  const view = supplierView(withSupplier)!;
  expect(view.evidence.map((e) => e.text)).toEqual(supplierItem.evidence.map((e) => e.text));
  expect(Object.keys(view.source).sort()).toEqual(["campaign", "file", "pdf_sha256", "submission_date"]);
  expect(view.source.pdf_sha256).toBe((withSupplier.cause as { source: { pdf_sha256: string } }).source.pdf_sha256);
});
it("판본을 확인할 수 없는 공급사는 숨긴다(출처 미표시로 보이지 않는다)", () => {
  const noCause: Card = { ...withSupplier, cause: { status: "cause_empty", campaign: "X" } };
  expect(supplierView(noCause)).toBeNull();
});
it("생산 기간 출처만 있어도 그 판본으로 공급사를 보인다", () => {
  const source = { campaign: "X", file: "p.pdf", pdf_sha256: "a".repeat(64), submission_date: "20200101" };
  const card: Card = { ...withSupplier, cause: { status: "cause_empty", campaign: "X" }, checklist: [supplierItem, { item: "production_period", label: "p", evidence: [], omitted: 0, unread: 0, source }] };
  expect(supplierView(card)?.source).toEqual(source);
});
it("원인 출처와 생산 기간 출처의 판본이 다르면 공급사를 숨긴다", () => {
  const source = { campaign: "X", file: "other.pdf", pdf_sha256: "b".repeat(64), submission_date: "20190101" };
  const card: Card = { ...withSupplier, checklist: [supplierItem, { item: "production_period", label: "p", evidence: [], omitted: 0, unread: 0, source }] };
  expect(supplierView(card)).toBeNull();
});
it("공급사 항목이 없거나 비어 있으면 null", () => {
  expect(supplierView({ ...withSupplier, checklist: [] })).toBeNull();
  expect(supplierView({ ...withSupplier, checklist: [{ ...supplierItem, evidence: [] }] })).toBeNull();
});
it("원인 상태 문구는 글이 있는지만 말한다", () => {
  expect(causeBadge(withSupplier).level).toBe("text");
  for (const card of cards) {
    const line = causeLine(card);
    expect(line.length).toBeGreaterThan(0);
    expect(causeBadge(card).label).not.toMatch(/applies|root cause is/i); // principle-ok: 라벨에 판정 문구가 없는지 검사하는 금지 패턴
  }
});
it("묶기 후보는 원인 글이 있는 선례만 고른 뒤 앞 6건이다(원인 없는 선례가 자리를 차지하지 않는다)", () => {
  const noCause: Card = { ...withSupplier, cause: { status: "no_573_report" } };
  const many = [...Array.from({ length: 6 }, (_, i) => ({ ...noCause, campno: `N${i}` })), withSupplier];
  expect(groupCandidates(many).map((c) => c.campno)).toEqual([withSupplier.campno]);
  const withCause = Array.from({ length: 8 }, (_, i) => ({ ...withSupplier, campno: `C${i}` }));
  expect(groupCandidates(withCause)).toHaveLength(6);
  expect(groupCandidates(withCause, Infinity)).toHaveLength(8);
  expect(groupCandidates([])).toEqual([]);
});
it("한글이 있는 글은 ko로 표시한다", () => {
  expect(langOf("리콜 제조사 (Part 573)")).toBe("ko");
  expect(langOf("Hyundai Motor America")).toBe("en");
});
