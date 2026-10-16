import { expect, it } from "vitest";
import fixture from "../search/__fixtures__/search_airbag.json";
import type { SearchResponse } from "../search/types";
import { emptySession, startEightd } from "./session";

const response = fixture as SearchResponse;
it("8D 작성을 누를 때마다 작업 번호가 올라가 화면 상태가 새로 시작되고, 선례·응답은 새 값으로 바뀐다", () => {
  const a = startEightd(emptySession, [response.precedents[0]], response);
  const b = startEightd(a, [response.precedents[1]], response);
  expect(b.nonce).toBe(a.nonce + 1);
  expect(b.cards).toEqual([response.precedents[1]]);
  const none = startEightd(b, [], null); // "선례 없이 8D 작성하기"도 새 작업이다
  expect(none.nonce).toBe(b.nonce + 1);
  expect(none.cards).toEqual([]);
});
it("같은 입력을 다시 눌러도 새 작업이다(이전 인용이 남지 않는다)", () => {
  const a = startEightd(emptySession, [response.precedents[0]], response);
  expect(startEightd(a, [response.precedents[0]], response).nonce).not.toBe(a.nonce);
});
