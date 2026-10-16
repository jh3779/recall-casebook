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
it("선례 근거 묶음 초안 버튼은 D2·D4에만, 검색 결과와 담은 선례가 있을 때만 나온다", () => {
  const withDraft = renderToStaticMarkup(<EightdView cards={picked} response={response} onBack={() => {}} />);
  expect(withDraft.match(/선례 근거 묶음 초안/g)).toHaveLength(2);
  expect(withDraft.match(/묶음 초안 만들기/g)).toHaveLength(2);
  const section = (n: number) => withDraft.split(`id="ed-h-${n}"`)[1].split("</section>")[0];
  for (const n of [2, 4]) expect(section(n)).toContain("묶음 초안 만들기");
  for (const n of [3, 5, 7]) expect(section(n)).not.toContain("묶음 초안");
  expect(renderToStaticMarkup(<EightdView cards={picked} response={null} onBack={() => {}} />)).not.toContain("묶음 초안");
  expect(renderToStaticMarkup(<EightdView cards={[]} response={response} onBack={() => {}} />)).not.toContain("묶음 초안 만들기");
});

it("질문만 고쳐 선례 없이 열면 SUBJECT는 새 질문이고, 이전 질문의 D7 검색 결과 표는 제안하지 않고 안내한다(리뷰 지적 — 서류에서 SUBJECT와 표가 어긋나지 않게)", () => {
  const markup = renderToStaticMarkup(<EightdView cards={[]} response={response} freshQuestion="new brake hose leak" onBack={() => {}} />);
  expect(markup).toContain('value="new brake hose leak"');
  expect(markup).not.toContain("표를 텍스트로 본문에 넣기");
  expect(markup).toContain("지금 질문과 다른 질문의 검색 결과라 제안하지 않습니다");
  const campno = response.customer_precedents[0]?.campno ?? response.precedents[0].campno;
  expect(markup).not.toContain(campno); // 이전 질문 검색 결과의 리콜 번호가 화면에 나오지 않는다
});
it("선례 없이 연 질문이 검색 응답의 질문과 같으면(앞뒤 공백 무시) D7 표를 그대로 제안한다", () => {
  const markup = renderToStaticMarkup(<EightdView cards={[]} response={response} freshQuestion={`  ${response.question} `} onBack={() => {}} />);
  expect(markup).toContain("표를 텍스트로 본문에 넣기");
  expect(markup).not.toContain("지금 질문과 다른 질문의 검색 결과");
});
