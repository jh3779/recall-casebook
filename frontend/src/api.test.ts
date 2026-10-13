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
const filledIndex = fixture.precedents.findIndex((c) => c.cause.status === "filled");
const drop = (path: string[]) => {
  const body = structuredClone(fixture) as Record<string, any>;
  const target = path.slice(0, -1).reduce((o, k) => o[k], body);
  delete target[path[path.length - 1]];
  return body;
};
const P = (...k: (string | number)[]) => k.join(".");
it.each([
  P("build_id"), P("bundle_sha256"), P("snapshot_date"), P("model"), P("question"), P("customer_precedents"), P("precedents"),
  ...["rank", "campno", "maker", "maker_group", "received_date", "defect", "consequence", "remedy", "components", "source", "cause", "investigations", "checklist"].map((k) => P("precedents", 0, k)),
  ...["dataset", "snapshot_date", "speaker"].map((k) => P("precedents", 0, "source", k)),
  P("precedents", filledIndex, "cause", "status"),
  ...["text", "speaker", "source", "flags"].map((k) => P("precedents", filledIndex, "cause", k)),
  ...["campaign", "file", "pdf_sha256", "submission_date", "text_basis"].map((k) => P("precedents", filledIndex, "cause", "source", k)),
])("필수 칸 %s가 없으면 형식 오류", async (path) => { reply(drop(path.split("."))); await expect(search("airbag")).rejects.toMatchObject({ kind: "shape" }); });
it.each(["bundle_sha256", "maker_group"])("%s의 자료형이 다르면 형식 오류(null은 허용)", async (key) => {
  const body = structuredClone(fixture) as Record<string, any>;
  if (key === "bundle_sha256") body.bundle_sha256 = 1; else body.precedents[0].maker_group = 1;
  reply(body); await expect(search("airbag")).rejects.toMatchObject({ kind: "shape" });
});
const withInv = fixture.precedents.findIndex((c) => c.investigations.length > 0);
const withEv = fixture.precedents.findIndex((c) => c.checklist.some((i) => i.evidence.length > 0));
it("시험 픽스처에 조사·근거 원소가 있다", () => { expect(withInv).toBeGreaterThanOrEqual(0); expect(withEv).toBeGreaterThanOrEqual(0); });
it.each([
  ...["action", "speaker", "subject", "summary", "open_date", "close_date"].map((k) => P("precedents", withInv, "investigations", 0, k)),
  ...["item", "label", "evidence"].map((k) => P("precedents", withEv, "checklist", 0, k)),
])("배열 원소 안의 필수 칸 %s가 없으면 형식 오류", async (path) => { reply(drop(path.split("."))); await expect(search("airbag")).rejects.toMatchObject({ kind: "shape" }); });
it("근거 원문(evidence.text)이 없으면 형식 오류", async () => {
  const body = structuredClone(fixture) as Record<string, any>;
  const item = body.precedents[withEv].checklist.find((i: Record<string, any>) => i.evidence.length > 0);
  delete item.evidence[0].text;
  reply(body); await expect(search("airbag")).rejects.toMatchObject({ kind: "shape" });
});
const filledCause = fixture.precedents[filledIndex].cause as Record<string, any>;
const withFlag = () => ({ ...structuredClone(filledCause), flags: [{ kind: "unknown_expression", label: "원인 미확인 표현", spans: [{ start: 0, end: 1, text: [...filledCause.text][0] }] }] });
const causeCases: Record<string, () => Record<string, any>> = {
  filled: withFlag,
  stated_unknown: () => ({ ...withFlag(), status: "stated_unknown" }),
  report_unreadable: () => ({ status: "report_unreadable", campaign: "SYNTHETIC", reason: "no_confirmable_date" }),
  ...Object.fromEntries(["report_status_unknown", "version_unresolved", "cause_empty", "cause_no_field", "verify_failed"].map((st) => [st, () => ({ status: st, campaign: "SYNTHETIC" })])),
};
const withCause = (cause: Record<string, any>) => { const body = structuredClone(fixture) as Record<string, any>; body.precedents[0].cause = cause; return body; };
it.each(Object.keys(causeCases))("상태 %s의 올바른 원인은 통과한다", async (status) => { const body = withCause(causeCases[status]()); reply(body); await expect(search("airbag")).resolves.toEqual(body); });
const causeDrops: [string, (c: Record<string, any>) => void][] = [
  ...["text", "speaker", "source", "flags"].flatMap((k) => ["filled", "stated_unknown"].map((st) => [`${st}.${k}`, (c: Record<string, any>) => { delete c[k]; }] as [string, (c: Record<string, any>) => void])),
  ...["kind", "label", "spans"].map((k) => [`filled.flags[0].${k}`, (c: Record<string, any>) => { delete c.flags[0][k]; }] as [string, (c: Record<string, any>) => void]),
  ...["start", "end", "text"].map((k) => [`filled.flags[0].spans[0].${k}`, (c: Record<string, any>) => { delete c.flags[0].spans[0][k]; }] as [string, (c: Record<string, any>) => void]),
  ["filled.flags[0].spans[0].start 자료형", (c) => { c.flags[0].spans[0].start = "0"; }],
  ["filled.flags[0].kind 모르는 값", (c) => { c.flags[0].kind = "other"; }],
  ...["campaign", "reason"].map((k) => [`report_unreadable.${k}`, (c: Record<string, any>) => { delete c[k]; }] as [string, (c: Record<string, any>) => void]),
  ...["report_status_unknown", "version_unresolved", "cause_empty", "cause_no_field", "verify_failed"].map((st) => [`${st}.campaign`, (c: Record<string, any>) => { delete c.campaign; }] as [string, (c: Record<string, any>) => void]),
  ["status 자료형", (c) => { c.status = 1; }],
];
it.each(causeDrops)("원인 %s가 없거나 틀리면 형식 오류", async (name, mutate) => {
  const cause = causeCases[name.split(/[.\s]/)[0]]?.() ?? causeCases.filled();
  mutate(cause); reply(withCause(cause)); await expect(search("airbag")).rejects.toMatchObject({ kind: "shape" });
});
it("dup_group이 없으면 형식 오류", async () => { reply(drop(["precedents", "0", "dup_group"])); await expect(search("airbag")).rejects.toMatchObject({ kind: "shape" }); });
it.each(["build_id", "bundle_sha256", "snapshot_date", "cards", "model"])("health의 %s가 없으면 형식 오류", async (key) => {
  const body = structuredClone(healthFixture) as Record<string, any>; delete body[key];
  reply(body); await expect(health()).rejects.toMatchObject({ kind: "shape" });
});
it("500은 서버 오류", async () => { reply({}, 500); await expect(search("airbag")).rejects.toMatchObject({ kind: "server", status: 500 }); });
it("JSON이 아닌 응답은 형식 오류", async () => { vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("<html>"))); await expect(search("airbag")).rejects.toMatchObject({ kind: "shape" }); });
it.each([null, {}, { ...fixture, customer_precedents: null }, { ...fixture, precedents: [{ campno: "x", cause: { status: "filled" } }] }, { ...fixture, precedents: [{ ...fixture.precedents[0], checklist: null }] }])("렌더할 수 없는 응답을 거절한다", async (body) => { reply(body); await expect(search("airbag")).rejects.toMatchObject({ kind: "shape" }); });
it("응답 모양 오류에도 받은 build를 남긴다", async () => { reply({ build_id: "test-build" }); await expect(search("airbag")).rejects.toMatchObject({ kind: "shape", buildId: "test-build" }); });
it("새 원인 상태는 문구로 알릴 수 있도록 받는다", async () => {
  const body = structuredClone(fixture);
  body.precedents[0].cause = { status: "new_status" } as never;
  reply(body); await expect(search("airbag")).resolves.toEqual(body);
});
