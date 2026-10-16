import { renderToStaticMarkup } from "react-dom/server";
import { expect, it } from "vitest";
import fixture from "../search/__fixtures__/search_airbag.json";
import { hasCauseText, type SearchResponse } from "../search/types";
import { CaseDetail } from "./CaseDetail";
import { CaseList } from "./CaseList";
import CasebookView from "./CasebookView";
import { AppBar } from "../AppBar";
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
  const props = { cards: [cards[0]], caseName: "Case A", notes: {}, onChange: () => {}, storageBlocked: false, onCopy: () => {}, onClear: () => {}, copyMessage: "" };
  expect(renderToStaticMarkup(<NotesPanel {...props} persistent={false} />)).toContain("lost on reload");
  const saved = renderToStaticMarkup(<NotesPanel {...props} persistent />);
  expect(saved).toContain("Saved in this browser under “Case A”. Never sent to the server or an LLM");
  expect(renderToStaticMarkup(<NotesPanel {...props} persistent storageBlocked />)).toContain("could not save the notes");
});
it("처음 화면은 안내 문구를 그린다(서버를 부르지 않는지는 헤드리스 브라우저로 확인)", () => {
  const markup = renderToStaticMarkup(<CasebookView health="loading" />);
  expect(markup).toContain("Recall Casebook.");
  expect(markup).toContain("Describe a defect");
});
it("메모 칸은 합성·비식별 입력만 쓰라고 안내하고 길이를 제한한다", () => {
  const markup = renderToStaticMarkup(<NotesPanel cards={[cards[0]]} caseName="" notes={{}} onChange={() => {}} persistent={false} storageBlocked={false} onCopy={() => {}} onClear={() => {}} copyMessage="" />);
  expect(markup).toContain("synthetic or de-identified");
  expect(markup).toContain('maxLength="10000"');
});
it("선례마다 Remove 버튼을 구분할 수 있고 화면 언어를 밝힌다", () => {
  const markup = renderToStaticMarkup(<CaseDetail card={cards[0]} response={response} onRemove={() => {}} />);
  expect(markup).toContain(`aria-label="Remove ${cards[0].campno}"`);
  expect(markup).toMatch(/lang="ko"[^>]*>[^<]*[가-힣]/); // 한국어 말한 주체 문구
  expect(renderToStaticMarkup(<CasebookView health="loading" />)).toContain('lang="en"');
});
it("앱 바에 케이스북 탭이 있고 현재 화면을 눌린 상태로 보인다", () => {
  const markup = renderToStaticMarkup(<AppBar view="casebook" onView={() => {}} health="loading" />);
  expect(markup).toMatch(/aria-pressed="true"[^>]*>케이스북/);
  expect(markup).toMatch(/aria-pressed="false"[^>]*>선례 검색/);
});
it("케이스북 화면 문구에 영어 판정·단정 표현이 없다", () => {
  const forbidden = /applies|verdict|is_?applicable|recall[_\s-]?required|root\s+cause\s+is\b|is\s+the\s+cause\b|will\s+be\s+recalled/i; // principle-ok: 판정 문구가 화면에 없는지 검사하는 금지 패턴
  const texts = [
    renderToStaticMarkup(<CasebookView health="loading" />),
    renderToStaticMarkup(<NotesPanel cards={[cards[0]]} caseName="Case A" notes={{}} onChange={() => {}} persistent storageBlocked={false} onCopy={() => {}} onClear={() => {}} copyMessage="" />),
    ...cards.map((card) => renderToStaticMarkup(<CaseDetail card={card} response={response} onRemove={() => {}} />)),
  ];
  // 원문(NHTSA 글, `cb-src-text` 문단)은 바꾸지 않으므로 빼고 화면이 붙인 문구만 본다
  for (const markup of texts) expect(markup.replace(/<p class="cb-src-text"[^>]*>.*?<\/p>/gs, "").match(forbidden)).toBeNull();
});
