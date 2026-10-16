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
