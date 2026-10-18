import { isValidElement, type ReactElement, type ReactNode } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { expect, it } from "vitest";
import fixture from "../search/__fixtures__/search_airbag.json";
import { hasCauseText, type SearchResponse } from "../search/types";
import { D4Reference } from "./D4Reference";
import { D4_EVIDENCE_KEY, d4EvidenceVisible, insertedCount } from "./document";
import { EvidenceCard } from "./EvidenceCard";

const response = fixture as SearchResponse;
const cards = [...response.customer_precedents, ...response.precedents].filter((c) => hasCauseText(c.cause));

/** 함수 컴포넌트가 돌려준 요소 나무에서 조건에 맞는 요소를 모두 모은다(훅이 없는 컴포넌트만 직접 호출해 시험한다) */
function findAll(node: ReactNode, pred: (el: ReactElement<Record<string, unknown>>) => boolean, out: ReactElement<Record<string, unknown>>[] = []) {
  if (Array.isArray(node)) { node.forEach((n) => findAll(n, pred, out)); return out; }
  if (!isValidElement(node)) return out;
  const el = node as ReactElement<Record<string, unknown>>;
  if (pred(el)) out.push(el);
  findAll(el.props.children as ReactNode, pred, out);
  return out;
}

it("본문 버튼은 D4 칸 본문(\"4\")으로, 부록 버튼은 부록(\"4a\")으로 간다 — 서로 바뀌지 않는다", () => {
  const calls: unknown[][] = [];
  const el = D4Reference({ cards: cards.slice(0, 2), response, customers: new Set(), inserted: {}, onToggle: (...args) => { calls.push(args); } }) as ReactElement;
  const evidence = findAll(el, (e) => e.type === EvidenceCard);
  expect(evidence).toHaveLength(2);
  (evidence[0].props.onToggleBody as (b: string) => void)("B1");
  (evidence[0].props.onToggleAppendix as (b: string) => void)("B2");
  (evidence[1].props.onToggleBody as (b: string) => void)("B3");
  expect(calls).toEqual([["4", cards[0].campno, "B1"], ["4a", cards[0].campno, "B2"], ["4", cards[1].campno, "B3"]]);
});
it("넣음 표시는 본문과 부록을 따로 센다", () => {
  const inserted = { [`4|${cards[0].campno}`]: "x", [`4a|${cards[1].campno}`]: "y" };
  const el = D4Reference({ cards: cards.slice(0, 2), response, customers: new Set(), inserted, onToggle: () => {} }) as ReactElement;
  const [a, b] = findAll(el, (e) => e.type === EvidenceCard);
  expect([a.props.inBody, a.props.inAppendix]).toEqual([true, false]);
  expect([b.props.inBody, b.props.inAppendix]).toEqual([false, true]);
  expect(renderToStaticMarkup(el)).toContain("넣음 2건");
});
it("EvidenceCard의 본문 버튼은 본문 콜백만, 부록 버튼은 부록 콜백만 부른다", () => {
  const seen: string[] = [];
  const el = EvidenceCard({ card: cards[0], customer: false, inBody: false, inAppendix: false, onToggleBody: () => { seen.push("body"); }, onToggleAppendix: () => { seen.push("appendix"); } }) as ReactElement;
  const buttons = findAll(el, (e) => e.type === "button");
  expect(buttons).toHaveLength(2);
  expect(buttons[0].props.children).toBe("본문에 텍스트로 넣기");
  expect(buttons[1].props.children).toBe("부록에 텍스트로 넣기");
  (buttons[0].props.onClick as () => void)();
  (buttons[1].props.onClick as () => void)();
  expect(seen).toEqual(["body", "appendix"]);
});
it("선례를 담지 않았으면 D4 참고가 없다", () => {
  expect(D4Reference({ cards: [], response, customers: new Set(), inserted: {}, onToggle: () => {} })).toBeNull();
});
it("근거 데이터 꼬리줄의 기준: D4 본문('4|')과 부록('4a|') 키를 모두 4단계로 세고, D4를 적용하지 않으면 세지 않는다", () => {
  const inserted = { "4|20V000001": "a", "4a|20V000001": "b", "4|draft:q": "c" };
  expect(insertedCount(inserted, new Set([4]))).toBe(3);
  expect(insertedCount({ "4a|20V000001": "b" }, new Set([4]))).toBe(1); // 부록만 넣어도 꼬리줄이 붙는다
  expect(insertedCount(inserted, new Set([2, 3]))).toBe(0);
  expect(insertedCount({}, new Set([4]))).toBe(0);
});
it("D4 근거 칸은 선례를 담았거나 이미 글이 있을 때 보이고, 쓴 글을 가리지 않는다", () => {
  expect(d4EvidenceVisible(0, {})).toBe(false);
  expect(d4EvidenceVisible(2, {})).toBe(true);
  expect(d4EvidenceVisible(0, { [D4_EVIDENCE_KEY]: "남은 글" })).toBe(true);
  expect(d4EvidenceVisible(0, { [D4_EVIDENCE_KEY]: "   " })).toBe(false);
});
