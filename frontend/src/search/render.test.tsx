import { readFileSync } from "node:fs";
import { renderToStaticMarkup } from "react-dom/server";
import { expect, it } from "vitest";
import { PrecedentDetail } from "./PrecedentDetail";
import { CauseBlock } from "./CauseBlock";
import { ResultList } from "./ResultList";
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
