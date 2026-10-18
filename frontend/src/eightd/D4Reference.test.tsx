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

it("선례 버튼 하나가 그 선례의 번호와 블록으로 본문·부록 함께 넣기 콜백을 부른다", () => {
  const calls: unknown[][] = [];
  const el = D4Reference({ cards: cards.slice(0, 2), response, customers: new Set(), inserted: {}, onToggle: (...args) => { calls.push(args); } }) as ReactElement;
  const evidence = findAll(el, (e) => e.type === EvidenceCard);
  expect(evidence).toHaveLength(2);
  (evidence[0].props.onToggle as (b: string) => void)("B1");
  (evidence[1].props.onToggle as (b: string) => void)("B2");
  expect(calls).toEqual([[cards[0].campno, "B1"], [cards[1].campno, "B2"]]);
});
it("넣음 표시는 본문이나 부록 중 하나라도 들어 있으면 켜지고, 같은 선례는 한 건으로 센다", () => {
  const inserted = { [`4|${cards[0].campno}`]: "x", [`4a|${cards[0].campno}`]: "x", [`4a|${cards[1].campno}`]: "y" };
  const el = D4Reference({ cards: cards.slice(0, 3), response, customers: new Set(), inserted, onToggle: () => {} }) as ReactElement;
  const [a, b, c] = findAll(el, (e) => e.type === EvidenceCard);
  expect([a.props.inserted, b.props.inserted, c.props.inserted]).toEqual([true, true, false]);
  expect(renderToStaticMarkup(el)).toContain("넣음 2건");
});
it("EvidenceCard는 버튼 하나이고 누르면 콜백을 부른다 — 본문·부록을 따로 고르는 버튼이 없다", () => {
  const seen: string[] = [];
  const el = EvidenceCard({ card: cards[0], customer: false, inserted: false, onToggle: (b) => { seen.push(b); } }) as ReactElement;
  const buttons = findAll(el, (e) => e.type === "button");
  expect(buttons).toHaveLength(1);
  expect(buttons[0].props.children).toBe("D4 본문·부록에 넣기");
  (buttons[0].props.onClick as () => void)();
  expect(seen).toHaveLength(1);
  expect(seen[0]).toContain(`[타사 선례 ${cards[0].campno}`);
  const on = EvidenceCard({ card: cards[0], customer: false, inserted: true, onToggle: () => {} }) as ReactElement;
  expect(findAll(on, (e) => e.type === "button")[0].props.children).toBe("D4 본문·부록에 넣음 ✓ (다시 누르면 뺌)");
});
it("선례를 담지 않았으면 D4 참고가 없다", () => {
  expect(D4Reference({ cards: [], response, customers: new Set(), inserted: {}, onToggle: () => {} })).toBeNull();
});
it("근거 데이터 꼬리줄의 기준: D4 본문('4|')과 부록('4a|') 키를 4단계로 세되 같은 선례는 한 건이고, D4를 적용하지 않으면 세지 않는다", () => {
  const inserted = { "4|20V000001": "a", "4a|20V000001": "b", "4|draft:q": "c" };
  expect(insertedCount(inserted, new Set([4]))).toBe(2);
  expect(insertedCount({ "4a|20V000001": "b" }, new Set([4]))).toBe(1); // 부록만 남아 있어도 꼬리줄이 붙는다
  expect(insertedCount(inserted, new Set([2, 3]))).toBe(0);
  expect(insertedCount({}, new Set([4]))).toBe(0);
});
it("D4 근거 칸은 선례를 담았거나 이미 글이 있을 때 보이고, 쓴 글을 가리지 않는다", () => {
  expect(d4EvidenceVisible(0, {})).toBe(false);
  expect(d4EvidenceVisible(2, {})).toBe(true);
  expect(d4EvidenceVisible(0, { [D4_EVIDENCE_KEY]: "남은 글" })).toBe(true);
  expect(d4EvidenceVisible(0, { [D4_EVIDENCE_KEY]: "   " })).toBe(false);
});
