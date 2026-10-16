import { expect, it } from "vitest";
import { isPicked, togglePick } from "./picks";
import fixture from "./__fixtures__/search_airbag.json";
import type { SearchResponse } from "./types";

const [a, b, c] = (fixture as SearchResponse).precedents;
it("담은 순서를 지키고 같은 선례는 한 번만 담는다", () => {
  let picked = togglePick([], b);
  picked = togglePick(picked, a);
  expect(picked.map((card) => card.campno)).toEqual([b.campno, a.campno]);
  expect(isPicked(picked, a)).toBe(true);
  expect(isPicked(picked, c)).toBe(false);
});
it("다시 누르면 빼고 나머지 순서는 그대로다", () => {
  const picked = togglePick(togglePick(togglePick([], a), b), c);
  expect(togglePick(picked, b).map((card) => card.campno)).toEqual([a.campno, c.campno]);
});
it("리콜 번호가 같으면 같은 선례로 본다(다른 객체여도)", () => {
  expect(isPicked([a], structuredClone(a))).toBe(true);
  expect(togglePick([a], structuredClone(a))).toEqual([]);
});
it("원래 목록을 바꾸지 않는다", () => {
  const before = [a];
  togglePick(before, b);
  expect(before).toEqual([a]);
});
