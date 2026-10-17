import { renderToStaticMarkup } from "react-dom/server";
import { expect, it } from "vitest";
import fixture from "../search/__fixtures__/search_airbag.json";
import { hasCauseText, type SearchResponse } from "../search/types";
import { CaseDetail } from "./CaseDetail";
import { CaseList } from "./CaseList";
import CasebookView from "./CasebookView";
import { AppBar } from "../AppBar";
import type { DraftResponse } from "../eightd/draft";
import { fmtDate } from "../recalls";
import { GroupPanel, GroupResult } from "./GroupPanel";
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
  expect(renderToStaticMarkup(<NotesPanel {...props} caseName="" persistent={false} />)).toContain("No case name");
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
    renderToStaticMarkup(<CaseList response={response} checked={[]} onToggle={() => {}} />),
    renderToStaticMarkup(<GroupPanel question="airbag" build={response} cards={cards} />),
    renderToStaticMarkup(<GroupPanel question="airbag" build={response} cards={[]} />),
    renderToStaticMarkup(<NotesPanel cards={[cards[0]]} caseName="Case A" notes={{}} onChange={() => {}} persistent storageBlocked={false} onCopy={() => {}} onClear={() => {}} copyMessage="" />),
    ...cards.map((card) => renderToStaticMarkup(<CaseDetail card={card} response={response} onRemove={() => {}} />)),
  ];
  // 원문(NHTSA 글, `cb-src-text` 문단)은 바꾸지 않으므로 빼고 화면이 붙인 문구만 본다
  for (const markup of texts) expect(markup.replace(/<p class="cb-src-text"[^>]*>.*?<\/p>/gs, "").match(forbidden)).toBeNull();
});

const draftBase: DraftResponse = { build_id: response.build_id, bundle_sha256: response.bundle_sha256 ?? null, snapshot_date: response.snapshot_date, question: "airbag", step: "d4", titles_generated: true, model: "mock", degraded: null, groups: [], ungrouped: [], questions: [], rejected: {} };
const withText = cards.filter((c) => hasCauseText(c.cause));
const item = (c: (typeof cards)[number]) => ({ campno: c.campno, field: "cause" as const, quote: hasCauseText(c.cause) ? c.cause.text : "", start: 0, end: 1, speaker: hasCauseText(c.cause) ? c.cause.speaker : "", cause_status: hasCauseText(c.cause) ? c.cause.status as "filled" | "stated_unknown" : null, cause_source: hasCauseText(c.cause) ? c.cause.source : null });
it("묶기 결과: 묶음은 'Group N'이고 제목·출처·제출일이 보이며 원문은 그대로다", () => {
  const result: DraftResponse = { ...draftBase, groups: [{ title: "서버 제목은 보이지 않는다", items: withText.slice(0, 2).map(item) }], ungrouped: [item(withText[2])], rejected: { not_in_source: 1, bad_title: 3 } };
  const markup = renderToStaticMarkup(<GroupResult result={result} cards={cards} />);
  expect(markup).toContain("Group 1");
  expect(markup).not.toContain("서버 제목은 보이지 않는다");
  for (const c of withText.slice(0, 2)) {
    const cause = c.cause as Extract<typeof c.cause, { text: string }>;
    expect(markup).toContain(escaped(cause.text));
    expect(markup).toContain(cause.source.pdf_sha256);
    expect(markup).toContain(escaped(cause.source.file));
  }
  expect(markup).toContain("submitted ");
  expect(markup).toContain("not in the source 1");
  expect(markup).not.toContain("bad_title");
  expect(markup).toContain("1 cause text(s) were not grouped");
});
it("묶기 결과 문구: 꺼짐·실패·묶음 없음·원인 없음 안내에도 판정 표현이 없다", () => {
  const forbidden = /applies|verdict|is_?applicable|recall[_\s-]?required|root\s+cause\s+is\b|is\s+the\s+cause\b|will\s+be\s+recalled/i; // principle-ok: 판정 문구가 화면에 없는지 검사하는 금지 패턴
  const variants: DraftResponse[] = [
    { ...draftBase, degraded: "disabled" }, { ...draftBase, degraded: "llm_failed" }, draftBase,
    { ...draftBase, ungrouped: [item(withText[0]), item(withText[1])] },
    { ...draftBase, groups: [{ title: "t", items: [item(withText[0])] }], rejected: { unknown_source: 1, duplicate_source: 2 } },
  ];
  for (const result of variants) {
    const markup = renderToStaticMarkup(<GroupResult result={result} cards={cards} />).replace(/<q[^>]*>.*?<\/q>/gs, "");
    expect(markup.match(forbidden)).toBeNull();
  }
  expect(renderToStaticMarkup(<GroupResult result={{ ...draftBase, degraded: "disabled" }} cards={cards} />)).toContain("switched off");
  expect(renderToStaticMarkup(<GroupResult result={{ ...draftBase, ungrouped: [item(withText[0])] }} cards={cards} />)).toContain("No similar wording found");
  expect(renderToStaticMarkup(<GroupResult result={draftBase} cards={cards} />)).toContain("None of the checked precedents has a cause text");
});
it("stated_unknown 묶음 인용에는 '원인을 모른다는 뜻이 아니다' 안내가 붙는다", () => {
  const unknown = cards.find((c) => c.cause.status === "stated_unknown");
  if (!unknown) return;
  const markup = renderToStaticMarkup(<GroupResult result={{ ...draftBase, groups: [{ title: "t", items: [item(unknown)] }] }} cards={cards} />);
  expect(markup).toContain("does not mean the cause is unknown");
});
it("체크한 선례의 메모가 없으면 전체 복사 버튼이 꺼져 있다(저장소에서 불러온 다른 선례 메모만 있어도)", () => {
  const base = { cards: [cards[0]], caseName: "Case A", onChange: () => {}, persistent: true, storageBlocked: false, onCopy: () => {}, onClear: () => {}, copyMessage: "" };
  expect(renderToStaticMarkup(<NotesPanel {...base} notes={{ other: "다른 선례 메모" }} />)).toMatch(/<button[^>]*disabled[^>]*>Copy all notes/);
  expect(renderToStaticMarkup(<NotesPanel {...base} notes={{ [cards[0].campno]: "이 선례 메모" }} />)).not.toMatch(/<button[^>]*disabled[^>]*>Copy all notes/);
});

it("연결된 NHTSA 결함 조사는 번호·말한 주체·개시/종결일·요약 원문을 접지 않고 보인다", () => {
  const withInv = cards.filter((c) => c.investigations.length > 0);
  expect(withInv.length).toBeGreaterThan(0);
  for (const card of withInv) {
    const markup = renderToStaticMarkup(<CaseDetail card={card} response={response} onRemove={() => {}} />);
    for (const inv of card.investigations) {
      for (const text of [inv.action, inv.speaker, inv.subject, inv.summary]) expect(markup).toContain(escaped(text));
      expect(markup).toContain(`opened ${fmtDate(inv.open_date)}`);
      expect(markup).toContain(inv.close_date ? `closed ${fmtDate(inv.close_date)}` : "closed no record");
    }
    expect(markup).toContain("NHTSA defect investigation");
    expect(markup).not.toContain("<details");
  }
  const none = cards.find((c) => c.investigations.length === 0)!;
  expect(renderToStaticMarkup(<CaseDetail card={none} response={response} onRemove={() => {}} />)).not.toContain("NHTSA defect investigation");
});
it("확인 항목: 생산 기간(생략 건수 포함)과 공급사를 출처와 함께 그린다", () => {
  const source = { campaign: "X", file: "odi/rcl/2026/RCLRPT-X.pdf", pdf_sha256: "c".repeat(64), submission_date: "20260710" };
  const supplier = { item: "supplier" as const, label: "공급사", evidence: [{ field: "573.supplier_names", text: "ACME Parts, Inc." }] };
  const production = { item: "production_period" as const, label: "생산 기간", evidence: [{ field: "573.production_dates", text: "Vehicle 1: 2015 | Apr 18, 2015 - Aug 24, 2015" }], omitted: 3, unread: 2, source };
  const card = { ...cards.find((c) => c.cause.status === "no_573_report")!, cause: { status: "cause_empty" as const, campaign: "X" }, checklist: [production, supplier] }; // 원인 칸이 비어도 생산 기간 근거는 되짚을 수 있다(server/rag/checks.py)
  const markup = renderToStaticMarkup(<CaseDetail card={card} response={response} onRemove={() => {}} />);
  expect(markup).toContain("Production period");
  expect(markup).toContain("Vehicle 1: 2015");
  expect(markup).toContain("3 more block(s) are not shown");
  expect(markup).toContain("2 block(s) without a readable date");
  expect(markup).toContain(source.file);
  expect(markup).toContain(source.pdf_sha256);
  expect(markup).toContain("ACME Parts, Inc.");
  expect((markup.match(/pdf_sha256/g) ?? []).length).toBe(2); // 생산 기간 출처와 공급사 출처가 각각 그려진다
});
it("조사 개시일·종결일이 비어 있으면 점 두 개 대신 no record를 보인다", () => {
  const base = cards.find((c) => c.investigations.length > 0)!;
  const card = { ...base, investigations: [{ ...base.investigations[0], open_date: "", close_date: "" }] };
  const markup = renderToStaticMarkup(<CaseDetail card={card} response={response} onRemove={() => {}} />);
  expect(markup).toContain("opened no record");
  expect(markup).toContain("closed no record");
  expect(markup).not.toContain("opened ..");
});
