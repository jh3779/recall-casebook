import { renderToStaticMarkup } from "react-dom/server";
import { expect, it } from "vitest";
import fixture from "../search/__fixtures__/search_airbag.json";
import type { SearchResponse } from "../search/types";
import { groupId, questionsBlock, type DraftItem, type DraftResponse } from "./draft";
import { DraftResult } from "./DraftResult";

const response = fixture as SearchResponse;
const card = response.precedents[0];
const item: DraftItem = { campno: card.campno, field: "defect", quote: 'The <b>inflator</b> may "rupture" & crack', start: 0, end: 40, speaker: card.source.speaker, dataset: card.source.dataset, snapshot_date: card.source.snapshot_date };
const base: DraftResponse = { build_id: "b1", bundle_sha256: null, snapshot_date: "2026-10-06", question: "q", step: "d2", titles_generated: true, model: "gpt-6-luna", degraded: null, groups: [{ title: "파열을 적은 선례", items: [item] }], ungrouped: [], questions: ["질문 하나", "질문 둘"], rejected: {} };
const render = (r: DraftResponse, inserted: Record<string, string> = {}) => renderToStaticMarkup(<DraftResult result={r} cards={[card]} inserted={inserted} onToggle={() => {}} />);

it("묶음은 중립 번호와 원문 인용만 보이고 도구가 붙인 제목은 화면 어디에도 없으며, 인용은 글자 그대로(HTML 이스케이프만) 보인다(리뷰 지적 — 제목이 한정어를 잃은 채 선택을 이끌지 않게)", () => {
  const markup = render(base);
  expect(markup).toContain("<b>묶음 1</b>");
  expect(markup).not.toContain("파열을 적은 선례");
  expect(markup).not.toContain("도구가 붙인 제목");
  expect(markup).toContain("The &lt;b&gt;inflator&lt;/b&gt; may &quot;rupture&quot; &amp; crack");
  expect(markup).not.toContain("<b>inflator</b>");
  expect(markup).toContain(card.campno);
  expect(markup).toContain(card.maker);
  expect(markup).toContain(`말한 주체: ${card.source.speaker}`);
});
it("묶음과 확인 질문에 본문에 넣기 버튼이 있고 넣은 것은 누른 상태로 보인다", () => {
  expect(render(base)).toContain("이 묶음을 본문에 넣기");
  expect(render(base)).toContain("확인 질문을 본문에 넣기");
  const on = render(base, { [groupId(base.groups[0])]: "x", "draft:q": questionsBlock(base.questions) });
  expect(on.match(/본문에 넣음 ✓ \(다시 누르면 뺌\)/g)).toHaveLength(2);
  expect(on).toContain('aria-pressed="true"');
});
it("꺼짐·실패는 묶음 없이 원문 카드를 쓰라고 알린다", () => {
  const off = render({ ...base, degraded: "disabled", groups: [], model: null, ungrouped: [item] });
  expect(off).toContain("묶음 초안 기능이 꺼져 있습니다.");
  expect(off).toContain("선례 참고");
  expect(off).not.toContain("이 묶음을 본문에 넣기");
  expect(render({ ...base, degraded: "llm_failed", groups: [] })).toContain("묶음을 만들지 못했습니다.");
});
it("서버가 원문과 대조해 버린 인용이 있으면 수를 알린다", () => {
  expect(render({ ...base, rejected: { not_in_source: 2, bad_title: 0 } })).toContain("원문에 없어서 2건");
  expect(render(base)).not.toContain("버린 항목");
});
it("묶이지 않은 원문이 있으면 카드에서 직접 넣을 수 있다고 알린다", () => {
  expect(render({ ...base, ungrouped: [item, item] })).toContain("묶이지 않은 원문 2건");
});
it("쓸 원문이 있는 선례가 없을 때 D4는 원인 원문이 있는 선례만 묶는다고 알린다", () => {
  const empty = render({ ...base, step: "d4", groups: [], ungrouped: [], questions: [] });
  expect(empty).toContain("원인 원문이 있는 선례만 묶습니다");
});
