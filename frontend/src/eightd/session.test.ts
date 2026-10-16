import { expect, it } from "vitest";
import fixture from "../search/__fixtures__/search_airbag.json";
import type { SearchResponse } from "../search/types";
import { emptySession, startEightd } from "./session";

const response = fixture as SearchResponse;
const other = { ...response, question: "a different question about brakes" } as SearchResponse;
const newBuild = { ...response, build_id: "ffffffffffffffff" } as SearchResponse;
const [a, b] = [response.precedents[0], response.precedents[1]];

it("질문이 바뀐 새 검색이면 새 작업이다 — 이전 질문의 글·인용·파일이 다음 서류에 섞이지 않게 작업 번호가 오른다", () => {
  const s1 = startEightd(emptySession, [a], response);
  const s2 = startEightd(s1, [b], other);
  expect(s2.nonce).toBe(s1.nonce + 1);
  expect(s2.cards).toEqual([b]);
  expect(s2.response).toBe(other);
});
it("서버 판본(build)이 바뀐 검색도 새 작업이다", () => {
  const s1 = startEightd(emptySession, [a], response);
  expect(startEightd(s1, [a], newBuild).nonce).toBe(s1.nonce + 1);
});
it("같은 질문에서 선례를 더 담아 돌아오면 같은 작업이 이어진다 — 쓴 글·올린 파일을 지우지 않는다(리뷰 지적)", () => {
  const s1 = startEightd(emptySession, [a], response);
  const s2 = startEightd(s1, [a, b], response);
  expect(s2.nonce).toBe(s1.nonce);
  expect(s2.cards).toEqual([a, b]);
});
it("선례 없이 쓰던 작업에 선례를 더하거나, 선례 없이 다시 열어도 쓴 글은 이어진다", () => {
  const none = startEightd(emptySession, [], null);
  const withPicks = startEightd(none, [a], response);
  expect(withPicks.nonce).toBe(none.nonce);
  const back = startEightd(withPicks, [], null);
  expect(back.nonce).toBe(withPicks.nonce);
  expect(back.cards).toEqual([]);
  expect(back.response).toBe(response); // 마지막 검색 응답은 유지(서류 꼬리의 출처 표시용)
});
