import { renderToStaticMarkup } from "react-dom/server";
import { expect, it } from "vitest";
import fixture from "../search/__fixtures__/search_airbag.json";
import { hasCauseText, type SearchResponse } from "../search/types";
import { CaseDetail } from "./CaseDetail";
import { CaseList } from "./CaseList";
import CasebookView from "./CasebookView";
import { NotesPanel } from "./NotesPanel";

const response = fixture as SearchResponse;
const cards = [...response.customer_precedents, ...response.precedents];
const escaped = (text: string) => renderToStaticMarkup(<span>{text}</span>).slice(6, -7);
const plain = (markup: string) => markup.replace(/<\/?span[^>]*>/g, "");

it.each(cards)("$campno: 원문·말한 주체·출처를 접지 않고 그대로 보인다", (card) => {
  const markup = renderToStaticMarkup(<CaseDetail card={card} response={response} onRemove={() => {}} />);
  for (const text of [card.defect, card.consequence, card.remedy, card.source.speaker, card.campno, response.build_id]) expect(markup).toContain(escaped(text));
  expect(markup).not.toContain("<details");
  if (hasCauseText(card.cause)) {
    expect(plain(markup)).toContain(escaped(card.cause.text));
    for (const text of [card.cause.speaker, card.cause.source.file, card.cause.source.text_basis]) expect(markup).toContain(escaped(text));
    expect(markup).toContain(card.cause.source.pdf_sha256);
  } else {
    expect(markup).toContain("No cause text");
  }
});
it("출처를 확인할 수 없는 공급사는 선례 상세에 나오지 않는다", () => {
  const noCause = cards.find((c) => !hasCauseText(c.cause))!;
  const forged = { ...noCause, checklist: [{ item: "supplier" as const, label: "Supplier", evidence: [{ field: "573.supplier_names", text: "SECRET SUPPLIER CO" }] }] };
  expect(renderToStaticMarkup(<CaseDetail card={forged} response={response} onRemove={() => {}} />)).not.toContain("SECRET SUPPLIER CO");
});
it("목록은 체크한 선례를 눌린 상태로 보인다", () => {
  const markup = renderToStaticMarkup(<CaseList response={response} checked={[cards[0]]} onToggle={() => {}} />);
  expect(markup).toContain('aria-pressed="true"');
  expect(markup).toContain('aria-pressed="false"');
});
it("메모 칸은 사건 이름이 없으면 잃을 수 있다고 알리고 서버로 보내지 않는다고 밝힌다", () => {
  const props = { cards: [cards[0]], notes: {}, onChange: () => {}, storageBlocked: false, onCopy: () => {}, onClear: () => {}, copyMessage: "" };
  expect(renderToStaticMarkup(<NotesPanel {...props} persistent={false} />)).toContain("lost on reload");
  const saved = renderToStaticMarkup(<NotesPanel {...props} persistent />);
  expect(saved).toContain("Never sent to the server or an LLM");
  expect(renderToStaticMarkup(<NotesPanel {...props} persistent storageBlocked />)).toContain("blocks storage");
});
it("처음 화면은 안내만 보이고 서버를 부르지 않는다", () => {
  const markup = renderToStaticMarkup(<CasebookView health="loading" />);
  expect(markup).toContain("Recall Casebook.");
  expect(markup).toContain("Describe a defect");
});
