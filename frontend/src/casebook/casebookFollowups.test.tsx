import { renderToStaticMarkup } from "react-dom/server";
import { expect, it } from "vitest";
import health from "../search/__fixtures__/health.json";
import fixture from "../search/__fixtures__/search_airbag.json";
import { hasCauseText, type Card, type HealthResponse, type SearchResponse } from "../search/types";
import { CaseDetail } from "./CaseDetail";
import { CaseList } from "./CaseList";
import { Intro } from "./Intro";
import { OverlayFailed, OverlayLoading } from "./OverlayBoundary";
import { QUESTION_POOL } from "./questions";
import { Results } from "./Results";
import { supplierView } from "./sources";

// 이슈 #159·#165 후속: 마크업으로 지킬 수 있는 것들(상태가 필요한 연결은 *.dom.test.tsx)
const response = fixture as SearchResponse;
const cards = [...response.customer_precedents, ...response.precedents];
const serverHealth = health as HealthResponse;

it("3D 로딩 창은 aria-busy 없이 열리고, 로딩·실패 안내창은 뜻에 맞는 같은 클래스(cb-3d-notice)를 쓴다 (#159)", () => {
  const loading = renderToStaticMarkup(<OverlayLoading onClose={() => {}} opener={null} />);
  const failed = renderToStaticMarkup(<OverlayFailed onClose={() => {}} opener={null} />);
  expect(loading).not.toContain("aria-busy"); // 낭독기에서 창 안내를 늦추고 aria-label·role=status와 겹친다
  for (const html of [loading, failed]) {
    expect(html).toContain("cb-3d-notice");
    expect(html).not.toContain("cb-3d-failed"); // 실패 전용 이름이 로딩 창에도 붙어 있던 것을 바로잡았다
  }
});

it("검색 전 안내의 데이터 판본에도 묶음 sha256 전체를 펼쳐 볼 수 있고, 묶음이 없으면 펼침이 없다 (#165)", () => {
  expect(serverHealth.bundle_sha256).toHaveLength(64);
  const markup = renderToStaticMarkup(<Intro health={serverHealth} onExample={() => {}} />);
  expect(markup).toMatch(new RegExp("<details[^>]*>[\\s\\S]*Full version[\\s\\S]*" + serverHealth.bundle_sha256 + "[\\s\\S]*</details>"));
  expect(markup).toContain(`bundle ${serverHealth.bundle_sha256!.slice(0, 12)}…`); // 요약 줄은 그대로
  expect(renderToStaticMarkup(<Intro health={{ ...serverHealth, bundle_sha256: null }} onExample={() => {}} />)).not.toContain("Full version");
  expect(renderToStaticMarkup(<Intro health="loading" onExample={() => {}} />)).not.toContain("Full version");
});

const resultsProps = { response, checked: [] as Card[], checkedKey: "", onToggle: () => {}, on3d: () => {}, notes: {}, onNoteChange: () => {}, caseName: "", persistent: false, storageBlocked: false, onCopy: () => {}, onClear: () => {}, copyMessage: "", storeMessage: "", onGroupPicked: () => {}, picked: [] as string[] };

it("결과가 나오면 낭독기용 건수 알림이 붙고, 두 목록이 모두 비면 다시 써 보라는 안내가 나온다 (#165 사라진 안내)", () => {
  const markup = renderToStaticMarkup(<Results {...resultsProps} />);
  const found = response.customer_precedents.length + response.precedents.length;
  expect(markup).toContain(`<p class="sr-only" role="status">Found ${found} precedents: ${response.customer_precedents.length} Hyundai / Kia, ${response.precedents.length} other manufacturers.</p>`);
  expect(markup).not.toContain("No precedents found");

  const one = renderToStaticMarkup(<Results {...resultsProps} response={{ ...response, customer_precedents: [], precedents: response.precedents.slice(0, 1) }} />);
  expect(one).toContain("Found 1 precedent: 0 Hyundai / Kia, 1 other manufacturers.");

  const empty = renderToStaticMarkup(<CaseList response={{ ...response, customer_precedents: [], precedents: [] }} checked={[]} onToggle={() => {}} />);
  expect(empty).toContain("No precedents found. Try changing the part name or how the failure appears.");
  expect(renderToStaticMarkup(<CaseList response={response} checked={[]} onToggle={() => {}} />)).not.toContain("No precedents found");
});

it("결과 화면은 묶기 구역을 그리고 체크한 선례에 원인 글이 있을 때만 묶기 단추를 켠다 (#165 Results→GroupPanel)", () => {
  const withText = cards.find((c) => hasCauseText(c.cause))!;
  const groupButton = (checked: Card[]) => renderToStaticMarkup(<Results {...resultsProps} checked={checked} checkedKey={checked.map((c) => c.campno).join(",")} />).match(/<button[^>]*>Group the checked causes<\/button>/)![0];
  expect(renderToStaticMarkup(<Results {...resultsProps} />)).toContain('aria-label="Group similar causes"');
  expect(groupButton([])).toContain("disabled");
  expect(groupButton([withText])).not.toContain("disabled");
});

it("결과 화면은 모델이 고른 확인 질문 번호를 D4 구역에 풀의 고정 문장으로 넘기고, 응답 출처 푸터를 붙인다 (#165 picked·Provenance)", () => {
  const markup = renderToStaticMarkup(<Results {...resultsProps} checked={cards.slice(0, 1)} picked={["P3"]} />);
  expect(markup).toContain("Picked by the model");
  expect(markup).toContain(QUESTION_POOL.P3.replace(/&/g, "&amp;").slice(0, 30));
  expect(renderToStaticMarkup(<Results {...resultsProps} checked={cards.slice(0, 1)} />)).not.toContain("Picked by the model");
  expect(markup).toContain('<footer class="cb-response-prov" aria-label="Response source">');
});

it("공급사 근거의 칸 이름은 서버가 준 field를 따른다 — 상수로 붙이지 않는다 (#165)", () => {
  const source = { campaign: "X", file: "odi/rcl/2026/RCLRPT-X.pdf", pdf_sha256: "c".repeat(64), submission_date: "20260710" };
  const base = cards.find((c) => c.cause.status === "no_573_report")!;
  const card = (field: string) => ({ ...base, cause: { status: "cause_empty" as const, campaign: "X" }, checklist: [
    { item: "production_period" as const, label: "생산 기간", evidence: [{ field: "573.production_dates", text: "Vehicle 1: 2015" }], omitted: 0, unread: 0, source },
    { item: "supplier" as const, label: "공급사", evidence: [{ field, text: "ACME Parts, Inc." }] },
  ] });
  expect(supplierView(card("573.supplier_names"))?.evidence).toEqual([{ field: "573.supplier_names", text: "ACME Parts, Inc." }]);
  expect(renderToStaticMarkup(<CaseDetail card={card("573.supplier_names")} response={response} onRemove={() => {}} />)).toContain("Part 573 supplier names · </span>ACME Parts, Inc.");
  // 서버가 다른 칸을 더하면 그 칸 이름이 따라온다(이름표가 없는 칸은 키 그대로)
  expect(renderToStaticMarkup(<CaseDetail card={card("573.other_party")} response={response} onRemove={() => {}} />)).toContain("573.other_party · </span>ACME Parts, Inc.");
});
