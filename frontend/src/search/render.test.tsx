import { readFileSync } from "node:fs";
import { renderToStaticMarkup } from "react-dom/server";
import { expect, it } from "vitest";
import { PrecedentDetail } from "./PrecedentDetail";
import { CauseBlock } from "./CauseBlock";
import { ResultList } from "./ResultList";
import { Checklist } from "./Checklist";
import { hasCauseText, type SearchResponse } from "./types";
import fixture from "./__fixtures__/search_airbag.json";
import synthetic from "./__fixtures__/cause_statuses_synthetic.json";

const response = fixture as SearchResponse;
const escaped = (text: string) => renderToStaticMarkup(<span>{text}</span>).slice(6, -7);
it.each([...response.customer_precedents, ...response.precedents])("$campno의 원문·주체·출처를 그대로 렌더한다", (card) => {
  const markup = renderToStaticMarkup(<PrecedentDetail card={card} response={response} />);
  for (const text of [card.defect, card.consequence, card.remedy, card.source.speaker, card.campno, response.build_id, ...card.investigations.flatMap((inv) => [inv.summary, inv.speaker, inv.action])]) expect(markup).toContain(escaped(text));
  if (hasCauseText(card.cause)) {
    expect(markup.replace(/<\/?span[^>]*>/g, "")).toContain(escaped(card.cause.text));
    expect(markup).toContain(escaped(card.cause.source.text_basis));
    expect(markup).toContain(escaped(card.cause.speaker));
    expect(markup).toContain(escaped(card.cause.source.file));
    expect(markup).toContain(card.cause.source.pdf_sha256);
  }
});
it("고객사 결과가 없더라도 구역과 안내를 남긴다", () => {
  const markup = renderToStaticMarkup(<ResultList response={{ ...response, customer_precedents: [] }} onSelect={() => {}} />);
  expect(markup).toContain("고객사 선례 · 현대·기아");
  expect(markup).toContain("검색 상위 100건 안에 현대·기아 리콜이 없습니다.");
});
it.each(synthetic)("합성 상태 $status도 빈 블록으로 남지 않는다", (cause) => {
  const markup = renderToStaticMarkup(<CauseBlock cause={cause} />);
  expect(markup).toContain("원인 원문 없음");
  expect(markup).toMatch(/<p class="status-line">[^<]+<\/p>/);
});
it("HTML과 U+0092도 텍스트 노드로 보존한다", () => {
  const text = '<script>alert("test")</script> GM\u0092s';
  const markup = renderToStaticMarkup(<PrecedentDetail card={{ ...response.precedents[0], defect: text }} response={{ ...response, bundle_sha256: null }} />);
  expect(markup).toContain(escaped(text));
  expect(markup).not.toContain("<script>");
  expect(markup).toContain("묶음 없음(로컬 파일로 띄운 서버)");
});
it("판본 자세히에 묶음 sha256 64자 전체가 들어 있다", () => {
  const markup = renderToStaticMarkup(<PrecedentDetail card={response.precedents[0]} response={response} />);
  expect(response.bundle_sha256).toHaveLength(64);
  expect(markup).toMatch(new RegExp("<details[^>]*>[\\s\\S]*판본 자세히[\\s\\S]*" + response.bundle_sha256 + "[\\s\\S]*</details>"));
});
it("목업 응답 픽스처를 글자 그대로 보관한다", () => {
  const html = readFileSync(new URL("../../../docs/design-system/mockup.html", import.meta.url), "utf8");
  for (const [id, file] of [["data-search", "search_airbag.json"], ["data-health", "health.json"]]) {
    const body = html.match(new RegExp('<script[^>]*id="' + id + '"[^>]*>([\\s\\S]*?)</script>'))![1];
    expect(readFileSync(new URL(`./__fixtures__/${file}`, import.meta.url), "utf8")).toBe(body);
  }
});
it("생산 기간 항목은 블록 원문·싣지 못한 수·출처 보고서를 판정 없이 보여 준다", () => {
  const source = { campaign: "24V001", file: "odi/rcl/2024/RCLRPT-24V001-0001.PDF", pdf_sha256: "cd".repeat(32), submission_date: "20240201" };
  const markup = renderToStaticMarkup(<Checklist items={[{
    item: "production_period", label: "생산 기간", omitted: 3, source,
    evidence: [{ field: "573.production_dates", text: "Vehicle 1: 2023-2023 FOO BAR | Jan 02, 2023 - Feb 03, 2023" }],
  }]} />);
  expect(markup).toContain("573 생산 기간 칸");
  expect(markup).toContain("Vehicle 1: 2023-2023 FOO BAR | Jan 02, 2023 - Feb 03, 2023");
  expect(markup).toContain("외 3개 블록은 싣지 않았습니다");
  expect(markup).toContain(source.file);
  expect(markup).toContain(source.pdf_sha256);
  expect(markup).not.toMatch(/겹칩니다|일치|같습니다/); // 같다·다르다를 말하지 않는다(AGENTS.md 2-1)
});
it("싣지 못한 블록이 없으면 안내를 그리지 않는다", () => {
  const source = { campaign: "24V001", file: "f.PDF", pdf_sha256: "cd".repeat(32), submission_date: "20240201" };
  const markup = renderToStaticMarkup(<Checklist items={[{ item: "production_period", label: "생산 기간", omitted: 0, source, evidence: [{ field: "573.production_dates", text: "x" }] }]} />);
  expect(markup).not.toContain("싣지 않았습니다");
});
it("호출 상한(429)은 기다릴 시간을 알리고 그동안 다시 시도를 막는다", async () => {
  const { ApiError } = await import("../api");
  const { Feedback } = await import("./Feedback");
  const markup = renderToStaticMarkup(<Feedback error={new ApiError("rate_limit", "x", 429, undefined, 7)} onRetry={() => {}} />);
  expect(markup).toContain("호출이 너무 잦습니다 (429)");
  // 남은 초는 화면에만 보이고 알림(role=alert) 밖·aria-hidden이라 화면 낭독기가 매초 다시 읽지 않는다
  const alert = markup.match(/<div role="alert">.*?<\/div>/)![0];
  expect(alert).not.toMatch(/\d+초/);
  expect(markup).toContain('<p aria-hidden="true">7초 남음</p>');
  expect(markup).toMatch(/<button[^>]*disabled=""[^>]*>다시 시도<span aria-hidden="true"> \(7\)<\/span><\/button>/);
  // 끝났을 때 알릴 영역은 기다리는 동안에도 비어 있는 채로 먼저 있어야 한다(live 영역은 생긴 뒤의 변화만 읽힌다)
  expect(markup).toContain('<p role="status" class="sr-only"></p>');
});
