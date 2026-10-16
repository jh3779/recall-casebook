import { afterEach, expect, it, vi } from "vitest";
import { API_BASE, draft } from "../api";
import type { DraftResponse } from "./draft";

afterEach(() => vi.unstubAllGlobals());
const reply = (body: unknown, status = 200, headers: Record<string, string> = {}) =>
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify(body), { status, headers })));

const item = { campno: "24V412000", field: "defect", quote: "The circuit board may short circuit", start: 10, end: 46, speaker: "NHTSA 리콜 기록 요약", dataset: "NHTSA FLAT_RCL", snapshot_date: "2026-10-06" };
const cause = { campno: "24V412000", field: "cause", quote: "Contaminated flux.", start: 0, end: 18, speaker: "리콜 제조사", cause_status: "filled", cause_source: { campaign: "24V412", file: "x.PDF", pdf_sha256: "ab".repeat(32), submission_date: "20240605", text_basis: "b" } };
const ok = (over: Record<string, unknown> = {}): DraftResponse => ({ build_id: "b1", bundle_sha256: null, snapshot_date: "2026-10-06", model: "gpt-6-luna", question: "q", step: "d2", titles_generated: true, degraded: null, reason: null, groups: [{ title: "회로 단락을 적은 선례", items: [item] }], ungrouped: [], questions: ["질문"], rejected: {}, ...over } as unknown as DraftResponse);

it("질문·담은 번호·단계만 POST로 보내고 정상 응답을 돌려준다", async () => {
  reply(ok());
  await expect(draft("q", ["24V412000"], "d2")).resolves.toEqual(ok());
  expect(fetch).toHaveBeenCalledWith(`${API_BASE}/draft`, expect.objectContaining({ method: "POST", body: '{"question":"q","campnos":["24V412000"],"step":"d2"}' }));
});
it("꺼져 있거나 실패해 묶음이 없는 응답(degraded)도 받는다", async () => {
  reply(ok({ degraded: "disabled", groups: [], model: null, ungrouped: [item] }));
  await expect(draft("q", ["24V412000"], "d2")).resolves.toMatchObject({ degraded: "disabled", groups: [] });
  reply(ok({ step: "d4", groups: [{ title: "원인 묶음", items: [cause] }] }));
  await expect(draft("q", ["24V412000"], "d4")).resolves.toMatchObject({ step: "d4" });
});
it("말한 주체·출처가 빠진 인용이 든 응답은 받지 않는다(서비스 원칙 2)", async () => {
  const noSpeaker = { ...item, speaker: undefined };
  const noSnapshot = { ...item, snapshot_date: undefined };
  const noCauseSource = { ...cause, cause_source: undefined };
  for (const bad of [noSpeaker, noSnapshot, noCauseSource, { ...item, quote: "" }, { ...item, field: "remedy" }]) {
    reply(ok({ groups: [{ title: "t", items: [bad] }] }));
    await expect(draft("q", ["24V412000"], "d2")).rejects.toMatchObject({ kind: "shape" });
  }
  reply(ok({ groups: [{ title: "t", items: [] }] }));
  await expect(draft("q", ["24V412000"], "d2")).rejects.toMatchObject({ kind: "shape" });
  reply(ok({ titles_generated: false }));
  await expect(draft("q", ["24V412000"], "d2")).rejects.toMatchObject({ kind: "shape" });
});
it("422는 서버가 문장으로 준 사유를 그대로 보인다(검색 결과 밖 번호)", async () => {
  reply({ detail: "이 질문의 검색 결과에 없는 리콜 번호입니다: 99V999000" }, 422);
  await expect(draft("q", ["99V999000"], "d2")).rejects.toMatchObject({ kind: "validation", status: 422, message: "이 질문의 검색 결과에 없는 리콜 번호입니다: 99V999000" });
});
it("422의 기존 배열 형식은 그대로 접두사만 뗀다", async () => {
  reply({ detail: [{ msg: "Value error, 영어 단어가 들어간 질문이 필요합니다" }] }, 422);
  await expect(draft("123", ["24V412000"], "d2")).rejects.toMatchObject({ kind: "validation", message: "영어 단어가 들어간 질문이 필요합니다" });
});
it("429는 호출 상한으로 알리고 대기 초를 읽는다", async () => {
  reply({ detail: "x" }, 429, { "Retry-After": "12" });
  await expect(draft("q", ["24V412000"], "d2")).rejects.toMatchObject({ kind: "rate_limit", status: 429, retryAfter: 12 });
});
