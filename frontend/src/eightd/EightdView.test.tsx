import { renderToStaticMarkup } from "react-dom/server";
import { expect, it } from "vitest";
import fixture from "../search/__fixtures__/search_airbag.json";
import type { SearchResponse } from "../search/types";
import EightdView from "./EightdView";

const response = fixture as SearchResponse;
const picked = [response.customer_precedents[0], response.precedents[1]];
it("선례 없이 열면 빈 양식이고 선례 참고·타사 선례 표시가 없다", () => {
  const markup = renderToStaticMarkup(<EightdView cards={[]} response={null} onBack={() => {}} />);
  expect(markup).toContain("선례 없이 작성합니다");
  expect(markup).toContain("본문에 넣은 선례 0건");
  expect(markup).not.toContain("선례 참고 열기");
  expect(markup).not.toContain("타사 선례");
  for (let n = 1; n <= 8; n++) expect(markup).toContain(`DISCIPLINE ${n}`);
});
it("담은 선례만 단계별 참고에 나오고, 넣기 전에는 본문이 비어 있다", () => {
  const markup = renderToStaticMarkup(<EightdView cards={picked} response={response} onBack={() => {}} />);
  expect(markup).toContain("8D 근거로 담은 선례 2건");
  for (const c of picked) expect(markup).toContain(c.campno);
  expect(markup).toContain("본문에 텍스트로 넣기");
  expect(markup).toContain("본문에 넣은 선례 0건");
  expect(markup).not.toContain("선례 근거 데이터");
  const others = [...response.customer_precedents, ...response.precedents].filter((c) => !picked.includes(c));
  expect(markup).not.toContain(`선례 ${others[0].campno}`);
});
it("검색 결과가 있으면 D7에 표 참고가 나온다", () => {
  expect(renderToStaticMarkup(<EightdView cards={[]} response={response} onBack={() => {}} />)).toContain("표를 텍스트로 본문에 넣기");
});
it("내 8D 파일을 올리기 전에는 내려받기가 꺼져 있고 파일이 서버로 가지 않는다고 알린다", () => {
  const markup = renderToStaticMarkup(<EightdView cards={[]} response={null} onBack={() => {}} />);
  expect(markup).toContain('type="file"');
  expect(markup).toContain("accept=\".docx,");
  expect(markup).toContain("파일은 이 기기 밖으로 나가지 않고 원본은 바뀌지 않습니다");
  expect(markup).toMatch(/<button[^>]*disabled=""[^>]*title="위에서 내 8D 파일\(\.docx\)을 올리면 켜집니다"[^>]*>원본 서식 그대로 내려받기 \(\.docx\)<\/button>/);
});
it("적용할 단계 선택이 있고 기본은 전체 적용이며 D2·D4만 프리셋이 있다", () => {
  const markup = renderToStaticMarkup(<EightdView cards={picked} response={response} onBack={() => {}} />);
  expect(markup).toContain("적용할 단계");
  for (let n = 1; n <= 8; n++) expect(markup).toMatch(new RegExp(`<button type="button" aria-pressed="true" class="on" title="[^"]+">D${n}</button>`));
  expect(markup).toMatch(/aria-pressed="true" class="on">전체<\/button>/);
  expect(markup).toMatch(/aria-pressed="false"[^>]*>D2·D4만<\/button>/);
  expect(markup).not.toContain("적용 안 함");
});
