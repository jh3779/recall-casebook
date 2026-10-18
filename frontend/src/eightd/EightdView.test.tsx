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
  expect(markup).toContain("D4에 넣은 선례 인용 0건");
  expect(markup).not.toContain("선례 참고 열기");
  expect(markup).not.toContain("타사 선례");
  for (let n = 1; n <= 8; n++) expect(markup).toContain(`DISCIPLINE ${n}`);
});
it("담은 선례만 단계별 참고에 나오고, 넣기 전에는 본문이 비어 있다", () => {
  const markup = renderToStaticMarkup(<EightdView cards={picked} response={response} onBack={() => {}} />);
  expect(markup).toContain("8D 근거로 담은 선례 2건");
  for (const c of picked) expect(markup).toContain(c.campno);
  expect(markup).toContain("본문에 텍스트로 넣기");
  expect(markup).toContain("부록에 텍스트로 넣기");
  expect(markup).toContain("D4에 넣은 선례 인용 0건");
  expect(markup).not.toContain("선례 근거 데이터");
  const others = [...response.customer_precedents, ...response.precedents].filter((c) => !picked.includes(c));
  expect(markup).not.toContain(`선례 ${others[0].campno}`);
});
it("선례 참고는 D4에만 있다 — 검색 결과가 있어도 D2·D3·D5·D7에는 선례 참고와 표 참고가 없다(DEC-076)", () => {
  expect(renderToStaticMarkup(<EightdView cards={[]} response={response} onBack={() => {}} />)).not.toContain("표를 텍스트로 본문에 넣기");
  const markup = renderToStaticMarkup(<EightdView cards={picked} response={response} onBack={() => {}} />);
  const section = (n: number) => markup.split(`id="ed-h-${n}"`)[1].split("</section>")[0];
  expect(section(4)).toContain("선례 참고 열기");
  for (const n of [1, 2, 3, 5, 6, 7, 8]) expect(section(n)).not.toContain("선례 참고 열기");
  expect(section(4).match(/선례 참고 열기/g)).toHaveLength(1); // 안내 문장에 같은 말이 들어 있어 D4 구역 안에서 센다
  expect(markup).not.toContain("표를 텍스트로 본문에 넣기");
});
it("내 8D 파일을 올리기 전에는 내려받기가 꺼져 있고 파일이 서버로 가지 않는다고 알린다", () => {
  const markup = renderToStaticMarkup(<EightdView cards={[]} response={null} onBack={() => {}} />);
  expect(markup).toContain('type="file"');
  expect(markup).toContain("accept=\".docx,");
  expect(markup).toContain("파일은 이 기기 밖으로 나가지 않고 원본은 바뀌지 않습니다");
  expect(markup).toMatch(/<button[^>]*disabled=""[^>]*title="위에서 내 8D 파일\(\.docx\)을 올리면 켜집니다"[^>]*>원본 서식 그대로 내려받기 \(\.docx\)<\/button>/);
});
it("적용할 단계 선택이 있고 기본은 전체 적용이며 D4만 프리셋이 있다", () => {
  const markup = renderToStaticMarkup(<EightdView cards={picked} response={response} onBack={() => {}} />);
  expect(markup).toContain("적용할 단계");
  for (let n = 1; n <= 8; n++) expect(markup).toMatch(new RegExp(`<button type="button" aria-pressed="true" class="on" title="[^"]+">D${n}</button>`));
  expect(markup).toMatch(/aria-pressed="true" class="on">전체<\/button>/);
  expect(markup).toMatch(/aria-pressed="false"[^>]*>D4만<\/button>/);
  expect(markup).not.toContain("D2·D4만");
  expect(markup).not.toContain("적용 안 함");
});
it("선례 근거 묶음 초안 버튼은 D4에만, 검색 결과와 담은 선례가 있을 때만 나온다", () => {
  const withDraft = renderToStaticMarkup(<EightdView cards={picked} response={response} onBack={() => {}} />);
  expect(withDraft.match(/선례 근거 묶음 초안/g)).toHaveLength(1);
  expect(withDraft.match(/묶음 초안 만들기/g)).toHaveLength(1);
  const section = (n: number) => withDraft.split(`id="ed-h-${n}"`)[1].split("</section>")[0];
  expect(section(4)).toContain("묶음 초안 만들기");
  for (const n of [2, 3, 5, 7]) expect(section(n)).not.toContain("묶음 초안");
  expect(renderToStaticMarkup(<EightdView cards={picked} response={null} onBack={() => {}} />)).not.toContain("묶음 초안");
  expect(renderToStaticMarkup(<EightdView cards={[]} response={response} onBack={() => {}} />)).not.toContain("묶음 초안 만들기");
});

it("질문만 고쳐 선례 없이 열면 SUBJECT는 새 질문이고, 이전 질문의 검색 결과는 화면에 나오지 않는다(리뷰 지적 — 서류에서 SUBJECT와 선례가 어긋나지 않게)", () => {
  const markup = renderToStaticMarkup(<EightdView cards={[]} response={response} freshQuestion="new brake hose leak" onBack={() => {}} />);
  expect(markup).toContain('value="new brake hose leak"');
  const campno = response.customer_precedents[0]?.campno ?? response.precedents[0].campno;
  expect(markup).not.toContain(campno); // 이전 질문 검색 결과의 리콜 번호가 화면에 나오지 않는다
});

it("D4 선례 참고는 D4 칸 본문과 부록 둘 다 고를 수 있고, 본문 근거 칸과 부록 칸이 따로 있다. 다른 단계에는 넣기 버튼이 없다(DEC-076)", () => {
  const one = response.customer_precedents[0] ?? response.precedents[0];
  const markup = renderToStaticMarkup(<EightdView cards={[one]} response={response} onBack={() => {}} />);
  expect(markup).toMatch(/D4 칸 본문\(엔지니어가 쓴 글 뒤\) 또는 아래 &#x27;선례 근거 부록&#x27;\(8D 표 뒤 별도 문단\)에 넣을 수 있습니다/);
  const d4 = markup.split('id="ed-h-4"')[1].split("</section>")[0]; // 안내 문장에도 같은 말이 있어 구역 안에서 센다
  expect(d4.match(/본문에 텍스트로 넣기/g)).toHaveLength(1); // 담은 선례 1건 × D4 하나뿐
  expect(d4.match(/부록에 텍스트로 넣기/g)).toHaveLength(1);
  for (const n of [1, 2, 3, 5, 6, 7, 8]) expect(markup.split(`id="ed-h-${n}"`)[1].split("</section>")[0]).not.toContain("텍스트로 넣기");
  expect(markup).toContain("선례 근거 — D4 칸에 들어가는 타사 원문");
  expect(markup).toContain("선례 근거 부록 — D4 타사 원인");
  expect(markup).toContain("선례 내용은 <b>D4에만</b> 넣습니다");
});
