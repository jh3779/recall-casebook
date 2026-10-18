import { expect, it } from "vitest";
import fixture from "../search/__fixtures__/search_airbag.json";
import { hasCauseText, type SearchResponse } from "../search/types";
import { evidenceBlock, isoDate, missingReason } from "./evidenceText";

const response = fixture as SearchResponse;
const cards = [...response.customer_precedents, ...response.precedents];

// 선례 내용은 D4(타사 원인 원문)에만 넣는다(DEC-076) — 옛 D2·D3·D5 블록과 D7 검색 결과 표는 없앴다
it.each(cards)("$campno: 원인 원문이 있을 때만 만들고 한 글자도 바꾸지 않으며 머리줄·말한 주체·출처 파일·sha256을 붙인다", (card) => {
  const d4 = evidenceBlock(card);
  if (!hasCauseText(card.cause)) { expect(d4).toBeNull(); return; }
  expect(d4!.split("\n")[0]).toBe(`[타사 선례 ${card.campno} · ${card.maker} · 접수 ${isoDate(card.received_date)}]`);
  expect(d4).toContain(`(원인 원문) "${card.cause.text}"`);
  expect(d4).toContain(`— 말한 주체: ${card.cause.speaker}`);
  expect(d4).toContain(card.cause.source.file);
  expect(d4).toContain(card.cause.source.pdf_sha256.slice(0, 12));
  expect(d4!.includes("원인을 모른다는 뜻으로 단정하지 않음")).toBe(card.cause.status === "stated_unknown");
});
it("본문에 넣을 글이 없는 이유는 서버가 준 원인 상태 문장을 그대로 쓴다", () => {
  const none = cards.find((c) => c.cause.status === "no_573_report")!;
  expect(missingReason(none)).toContain("접수일이 2014-08-20 이전이라 Part 573 원문 수집 범위 밖입니다");
  expect(missingReason(none)).toContain("원인 원문 없음");
});
it("판정 문구를 만들지 않는다", () => {
  for (const c of cards) expect(evidenceBlock(c) ?? "").not.toMatch(/리콜 대상입니다|원인은 이것입니다|해당합니다/); // principle-ok: 판정 문구가 본문에 들어가지 않는지 확인하는 부정 단언
});
