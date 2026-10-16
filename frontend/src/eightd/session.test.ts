import { expect, it } from "vitest";
import fixture from "../search/__fixtures__/search_airbag.json";
import type { SearchResponse } from "../search/types";
import { nextEightdInput, workChanged } from "./session";

const response = fixture as SearchResponse;
const other = { ...response, question: "a different question about brakes" } as SearchResponse;
const rephrased = { ...response, question: `${response.question} again` } as SearchResponse;
const newBundle = { ...response, bundle_sha256: "bundle-y" } as SearchResponse;
const newBuild = { ...response, build_id: "ffffffffffffffff" } as SearchResponse;

it("질문이 바뀌었거나(조금 고쳐도) 서버 판본이 바뀐 검색이면 이전 작업과 다른 작업으로 본다", () => {
  expect(workChanged(response, other)).toBe(true);
  expect(workChanged(response, rephrased)).toBe(true);
  expect(workChanged(response, newBuild)).toBe(true);
});
it("build_id가 같아도 묶음 지문(bundle_sha256)이 다르면 다른 판본이다 — 한쪽만 null이어도 다르다(리뷰 지적)", () => {
  const withBundle = { ...response, bundle_sha256: "bundle-x" } as SearchResponse;
  expect(workChanged(withBundle, newBundle)).toBe(true);
  expect(workChanged(withBundle, { ...response, bundle_sha256: null } as SearchResponse)).toBe(true);
  expect(workChanged({ ...response, bundle_sha256: null } as SearchResponse, { ...response, bundle_sha256: null } as SearchResponse)).toBe(false);
});
it("같은 질문·같은 판본이면 같은 작업이다 — 선례만 더 담은 경우", () => {
  expect(workChanged(response, { ...response })).toBe(false);
});
it("한쪽에 검색 결과가 없으면(선례 없이 쓰던 작업·검색 실패) 다른 작업으로 보지 않는다 — 쓴 글을 묻지 않고 지우지 않는다", () => {
  expect(workChanged(null, response)).toBe(false);
  expect(workChanged(response, null)).toBe(false);
  expect(workChanged(null, null)).toBe(false);
});
it("응답 없이 열면(검색 중·실패) 마지막 응답을 유지하고, 새 응답이 있으면 새것으로 바꾼다", () => {
  const prev = { cards: [], response };
  expect(nextEightdInput(prev, [], null).response).toBe(response);
  expect(nextEightdInput(prev, [], other).response).toBe(other);
  expect(nextEightdInput({ cards: [], response: null }, [], null).response).toBeNull();
});
