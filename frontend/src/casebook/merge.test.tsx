import { isValidElement, type ReactElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { expect, it } from "vitest";
import health from "../search/__fixtures__/health.json";
import synthetic from "../search/__fixtures__/cause_statuses_synthetic.json";
import fixture from "../search/__fixtures__/search_airbag.json";
import type { Card, HealthResponse, SearchResponse } from "../search/types";
import EightdView from "../eightd/EightdView";
import { adoptDraft } from "./adoptDraft";
import { CaseDetail } from "./CaseDetail";
import { CaseList } from "./CaseList";
import CasebookView from "./CasebookView";
import { EXAMPLES } from "./examples";
import { Intro } from "./Intro";
import { Provenance } from "./Provenance";
import { Results } from "./Results";
import { Write8dBar, Write8dPlain } from "./Write8dBar";

// 선례 검색 화면을 케이스북에 합친 부분(DEC-075)
const response = fixture as SearchResponse;
const cards = [...response.customer_precedents, ...response.precedents];
const escaped = (text: string) => renderToStaticMarkup(<span>{text}</span>).slice(6, -7);

it("검색 전 안내에 예시 질문 4개·하는 일/하지 않는 일·데이터 판본이 있다", () => {
  const markup = renderToStaticMarkup(<Intro health={health as HealthResponse} onExample={() => {}} />);
  expect(EXAMPLES).toHaveLength(4);
  for (const q of EXAMPLES) expect(markup).toMatch(new RegExp(`<button[^>]*>${q}</button>`));
  expect(markup).toContain("What this tool does");
  expect(markup).toContain("What it does not do");
  for (const line of ["What it does not do", "It does not decide whether a recall is needed, or what the cause is.", "It does not translate or summarize the originals.", "It does not guess a cause or a supplier that is not in the source."]) expect(markup).toContain(line);
  expect(markup).toContain(`build ${health.build_id}`);
  expect(markup).toContain(`snapshot ${health.snapshot_date}`);
});
it("서버 판본을 아직 못 받았으면 데이터 판본 자리에 그 상태를 밝힌다", () => {
  expect(renderToStaticMarkup(<Intro health="loading" onExample={() => {}} />)).toContain("Checking server…");
  expect(renderToStaticMarkup(<Intro health="error" onExample={() => {}} />)).toContain("Server version unavailable");
});
it("케이스북 첫 화면에 안내가 나오고, 3D 쇼룸이 넘긴 질문이 입력창에 채워진다", () => {
  expect(renderToStaticMarkup(<CasebookView health="loading" />)).toContain("Example questions");
  const withDraft = renderToStaticMarkup(<CasebookView health="loading" draft={{ question: "steering rack noise", key: 1 }} />);
  expect(withDraft).toContain('value="steering rack noise"');
});
it("선례 없이 8D 작성 버튼은 8D로 넘길 수 있을 때만 있다", () => {
  expect(renderToStaticMarkup(<CasebookView health="loading" onWrite8d={() => {}} />)).toContain("Write 8D without precedents");
  expect(renderToStaticMarkup(<CasebookView health="loading" />)).not.toContain("Write 8D");
});
it("체크한 선례가 있을 때만 8D 작성 줄이 나오고, 누르면 체크한 선례와 검색 결과를 넘긴다", () => {
  const seen: unknown[] = [];
  expect(Write8dBar({ checked: [], response, onWrite8d: () => {} })).toBeNull();
  const bar = Write8dBar({ checked: cards.slice(0, 2), response, onWrite8d: (...args) => { seen.push(args); } }) as ReactElement<{ children: ReactElement<{ onClick: () => void }>[] }>;
  expect(isValidElement(bar)).toBe(true);
  bar.props.children[0].props.onClick();
  expect(seen).toEqual([[cards.slice(0, 2), response]]);
  expect(renderToStaticMarkup(bar)).toContain("Write 8D from checked (2)");
});
it("HTML과 U+0092도 텍스트 노드로 보존한다", () => {
  const text = '<script>alert("test")</script> GM\u0092s';
  const markup = renderToStaticMarkup(<CaseDetail card={{ ...response.precedents[0], defect: text }} response={response} onRemove={() => {}} />);
  expect(markup).toContain(escaped(text));
  expect(markup).not.toContain("<script>");
});
it("응답 출처에 묶음 sha256 64자 전체와 질문이 있고, 묶음이 없으면 그렇게 밝힌다", () => {
  expect(response.bundle_sha256).toHaveLength(64);
  const markup = renderToStaticMarkup(<Provenance data={response} />);
  expect(markup).toMatch(new RegExp("<details[^>]*>[\\s\\S]*Full version[\\s\\S]*" + response.bundle_sha256 + "[\\s\\S]*</details>"));
  expect(markup).toContain(`build ${response.build_id}`);
  expect(markup).toContain(escaped(response.question));
  expect(renderToStaticMarkup(<Provenance data={{ ...response, bundle_sha256: null }} />)).toContain("no bundle (server started from local files)");
});
it("8D 화면의 돌아가기 단추는 케이스북을 가리킨다", () => {
  const markup = renderToStaticMarkup(<EightdView cards={[]} response={null} onBack={() => {}} />);
  expect(markup).toContain("← 케이스북으로");
  expect(markup).not.toContain("선례 찾기로");
});
it("이미 떠 있는 케이스북은 새 draft가 올 때만 질문을 채우고, 쓰던 질문은 그대로 둔다", () => {
  expect(adoptDraft(0, { question: "brake hose leak", key: 1 }, "typed by user")).toEqual({ key: 1, question: "brake hose leak" });
  expect(adoptDraft(1, { question: "brake hose leak", key: 1 }, "typed after")).toEqual({ key: 1, question: "typed after" });
  expect(adoptDraft(0, null, "typed")).toEqual({ key: 0, question: "typed" });
});
it.each(synthetic)("합성 원인 상태 $status도 빈 블록으로 남지 않고 상태를 말한다", (cause) => {
  const markup = renderToStaticMarkup(<CaseDetail card={{ ...response.precedents[0], cause } as unknown as Card} response={response} onRemove={() => {}} />);
  expect(markup).toMatch(/<p class="cb-status">[^<]+<\/p>/);
});
it("고객사 결과가 없더라도 구역과 안내를 남긴다", () => {
  const markup = renderToStaticMarkup(<CaseList response={{ ...response, customer_precedents: [] }} checked={[]} onToggle={() => {}} />);
  expect(markup).toContain("Customer precedents · Hyundai / Kia");
  expect(markup).toContain("No Hyundai / Kia recall in the top 100.");
});

const resultsProps = { response, checked: [] as Card[], checkedKey: "", onToggle: () => {}, on3d: () => {}, notes: {}, onNoteChange: () => {}, caseName: "", persistent: false, storageBlocked: null as never, onCopy: () => {}, onClear: () => {}, copyMessage: "", storeMessage: "", onGroupPicked: () => {}, picked: [] as string[] };
it("결과 화면에는 응답 출처(묶음 sha 전체)가 항상 붙고, 8D 줄은 체크한 선례가 있고 넘길 수 있을 때만 붙는다", () => {
  const none = renderToStaticMarkup(<Results {...resultsProps} />);
  expect(none).toContain(response.bundle_sha256);
  expect(none).not.toContain("Write 8D");
  const withChecked = renderToStaticMarkup(<Results {...resultsProps} checked={cards.slice(0, 2)} onWrite8d={() => {}} />);
  expect(withChecked).toContain("Write 8D from checked (2)");
  expect(withChecked).toContain(response.bundle_sha256);
  expect(renderToStaticMarkup(<Results {...resultsProps} checked={cards.slice(0, 2)} />)).not.toContain("Write 8D");
  expect(renderToStaticMarkup(<Results {...resultsProps} onWrite8d={() => {}} />)).not.toContain("Write 8D");
});
it("선례 없이 8D 단추는 체크한 선례를 넘기지 않고 입력창의 질문을 새 질문으로 넘긴다", () => {
  const seen: unknown[] = [];
  const el = Write8dPlain({ question: "my question", response, onWrite8d: (...args) => { seen.push(args); } }) as ReactElement<{ onClick: () => void }>;
  el.props.onClick();
  expect(seen).toEqual([[[], response, { question: "my question" }]]);
});
it("싣지 못한 생산 기간 블록이 0이면 안내를 그리지 않는다", () => {
  const source = { campaign: "X", file: "odi/rcl/2026/RCLRPT-X.pdf", pdf_sha256: "c".repeat(64), submission_date: "20260710" };
  const production = { item: "production_period" as const, label: "생산 기간", evidence: [{ field: "573.production_dates", text: "Vehicle 1: 2015" }], omitted: 0, unread: 0, source };
  const card = { ...cards.find((c) => c.cause.status === "no_573_report")!, cause: { status: "cause_empty" as const, campaign: "X" }, checklist: [production] };
  const markup = renderToStaticMarkup(<CaseDetail card={card} response={response} onRemove={() => {}} />);
  expect(markup).toContain("Production period");
  expect(markup).not.toContain("not shown");
  expect(markup).not.toContain("without a readable date");
});
