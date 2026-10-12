import { afterEach, expect, it, vi } from "vitest";
import { API_BASE, health, search } from "./api";
import fixture from "./search/__fixtures__/search_airbag.json";
import healthFixture from "./search/__fixtures__/health.json";
afterEach(() => vi.unstubAllGlobals());
const reply = (body: unknown, status = 200) => vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify(body), { status })));
it("정상 응답과 질문 하나만 있는 요청 본문", async () => {
  reply(fixture);
  await expect(search(" airbag ")).resolves.toEqual(fixture);
  expect(fetch).toHaveBeenCalledWith(`${API_BASE}/search`, expect.objectContaining({ method: "POST", body: '{"question":" airbag "}' }));
});
it("health는 실제 판본만 사용한다", async () => { reply(healthFixture); await expect(health()).resolves.toEqual(healthFixture); });
it("422는 서버 문구의 접두사만 제거한다", async () => {
  reply({ detail: [{ msg: "Value error, 영어 단어가 들어간 질문이 필요합니다" }] }, 422);
  await expect(search("123")).rejects.toMatchObject({ kind: "validation", status: 422, message: "영어 단어가 들어간 질문이 필요합니다" });
});
it("TypeError는 연결 실패", async () => { vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("fetch failed"))); await expect(search("airbag")).rejects.toMatchObject({ kind: "network" }); });
it("abort는 시간 초과", async () => { vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new DOMException("aborted", "AbortError"))); await expect(search("airbag")).rejects.toMatchObject({ kind: "timeout" }); });
it("500은 서버 오류", async () => { reply({}, 500); await expect(search("airbag")).rejects.toMatchObject({ kind: "server", status: 500 }); });
it("JSON이 아닌 응답은 형식 오류", async () => { vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("<html>"))); await expect(search("airbag")).rejects.toMatchObject({ kind: "shape" }); });
it.each([null, {}, { ...fixture, customer_precedents: null }, { ...fixture, precedents: [{ campno: "x", cause: { status: "filled" } }] }, { ...fixture, precedents: [{ ...fixture.precedents[0], checklist: null }] }])("렌더할 수 없는 응답을 거절한다", async (body) => { reply(body); await expect(search("airbag")).rejects.toMatchObject({ kind: "shape" }); });
it("응답 모양 오류에도 받은 build를 남긴다", async () => { reply({ build_id: "test-build" }); await expect(search("airbag")).rejects.toMatchObject({ kind: "shape", buildId: "test-build" }); });
it("새 원인 상태는 문구로 알릴 수 있도록 받는다", async () => {
  const body = structuredClone(fixture);
  body.precedents[0].cause = { status: "new_status" } as never;
  reply(body); await expect(search("airbag")).resolves.toEqual(body);
});
